"use strict";
const state = {
  user: null,
  csrf: "",
  view: "all",
  items: [],
  collections: [],
  reminders: [],
  focus: [],
  chats: [],
  capabilities: null,
  query: "",
  kind: "",
  collection: "",
  lastAnswer: null,
  editing: null,
  recorded: null,
  file: null,
  recorder: null,
  stream: null,
  recognizer: null,
  clock: {
    remaining: 25 * 60,
    total: 25 * 60,
    running: false,
    last: 0,
    handle: null,
  },
};
const app = document.querySelector("#app");
const modal = document.querySelector("#modal-root");
const esc = (v) =>
  String(v == null ? "" : v).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
const urlSafe = (u) => {
  try {
    const p = new URL(u);
    return ["http:", "https:"].includes(p.protocol) ? p.href : null;
  } catch {
    return null;
  }
};
const eattr = esc;
const ago = (n) => {
  if (!n) return "";
  let d = Math.max(0, Math.floor(Date.now() / 1000 - n));
  return d < 60
    ? "just now"
    : d < 3600
      ? `${Math.floor(d / 60)}m ago`
      : d < 86400
        ? `${Math.floor(d / 3600)}h ago`
        : `${Math.floor(d / 86400)}d ago`;
};
const icon = (k) =>
  ({
    note: "NT",
    youtube: "YT",
    web: "URL",
    github: "GH",
    file: "DOC",
    voice: "REC",
    chat: "CH",
    code: "</>",
    image: "IMG",
  })[k] || "NT";
const statusOf = (x) => {
  const s = x.status || "searchable";
  const bad = [
    "metadata_only",
    "audio_saved_no_transcript",
    "file_saved_no_text",
    "fetching_captions",
    "fetching_webpage",
    "transcription_pending",
    "processing",
  ].includes(s);
  const label =
    {
      searchable: "Indexed",
      metadata_only: "Metadata only",
      audio_saved_no_transcript: "Transcript needed",
      file_saved_no_text: "Text unavailable",
      fetching_captions: "Importing captions",
      fetching_webpage: "Reading link",
      transcription_pending: "Checking speech",
      processing: "Processing",
      saved_without_text: "No searchable text",
    }[s] || s.replace(/_/g, " ");
  return `<span class="status${bad ? " warn" : ""}" title="${esc(x.meta?.processing_error || "")}">${esc(label)}</span>`;
};
const brand = () =>
  `<a class="brand" href="/" data-command="home"><span class="brandmark">C</span><span>convexa</span></a>`;
let toastTimer;
function toast(message, error = false) {
  const t = document.querySelector("#toast");
  t.textContent = message;
  t.className = "toast show" + (error ? " error-text" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 4500);
}
async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = { ...(options.headers || {}) };
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = state.csrf;
  if (
    options.body != null &&
    !(options.body instanceof Blob) &&
    !(options.body instanceof ArrayBuffer)
  )
    headers["Content-Type"] = "application/json";
  let body = options.body;
  if (body != null && headers["Content-Type"] === "application/json" && typeof body !== "string")
    body = JSON.stringify(body);
  const r = await fetch(path, {
    credentials: "same-origin",
    ...options,
    method,
    headers,
    body,
  });
  let data;
  try {
    data = await r.json();
  } catch {
    data = { error: "Unexpected server response" };
  }
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}
function navigate(path) {
  history.pushState({}, "", path);
  renderRoute();
}
function renderRoute() {
  if (location.pathname === "/app") {
    if (state.user) renderWorkspace();
    else renderAuth(false);
  } else if (location.pathname === "/login") {
    renderAuth(false);
  } else renderLanding();
}
window.addEventListener("popstate", renderRoute);
async function boot() {
  try {
    const me = await api("/api/me");
    state.user = me.user;
    state.csrf = me.csrf;
    await refreshAll();
  } catch {}
  renderRoute();
}
async function refreshAll() {
  if (!state.user) return;
  try {
    const [items, collections, reminders, focus, chats, caps] = await Promise.all([
      api("/api/items"),
      api("/api/collections"),
      api("/api/reminders"),
      api("/api/focus"),
      api("/api/chat/history"),
      api("/api/capabilities"),
    ]);
    state.items = items.results.map((r) => r.item);
    state.collections = collections.collections;
    state.reminders = reminders.reminders;
    state.focus = focus.sessions;
    state.chats = chats.messages;
    state.capabilities = caps;
  } catch (e) {
    toast(e.message, true);
  }
}
async function refreshItems() {
  if (!state.user) return;
  const data = await api("/api/items");
  state.items = data.results.map((r) => r.item);
}
function renderLanding() {
  app.innerHTML = `<div class="landing"><header class="topnav wide">${brand()}<nav class="navlinks"><a href="#features">Why Convexa</a><a href="#how">How it works</a><button class="btn small primary" data-command="get-started">${state.user ? "Open workspace" : "Get started"} &nbsp;→</button></nav></header>
<main><section class="wide hero"><div><span class="eyebrow">A place for everything worth keeping</span><h1>Good ideas shouldn't<br><em>get lost.</em></h1><p>Your videos, voice memos, documents, conversations and notes deserve more than scattered folders. Bring them together, and find what matters again.</p><div class="hero-actions"><button class="btn primary" data-command="get-started">Start your second brain →</button><a class="btn" href="#how">See how it works</a></div><div class="fineprint">Private by default · Runs on your computer · No subscription</div></div>
<div class="mock-window" aria-label="Illustration of the Convexa knowledge search"><div class="mock-top"><span>◉ &nbsp; My knowledge space</span><span>Local workspace &nbsp; •</span></div><div class="mock-content"><div class="mock-heading">Everything connects.</div><div class="mock-search">⌕ &nbsp; how do we avoid duplicate data?</div><div class="mock-card"><span class="icon-sq youtube">YT</span><span><b>Database design · lecture</b><small>Saved video · searchable captions</small></span></div><div class="mock-card"><span class="icon-sq file">PDF</span><span><b>DBMS revision notes</b><small>Document · extracted text</small></span></div><div class="mock-card"><span class="icon-sq chat">CH</span><span><b>Discussion on normalization</b><small>Saved conversation</small></span></div><div class="mock-answer"><strong>Found in your knowledge</strong><div style="margin-top:6px">Related passages from notes, a lecture and a saved chat, all in one search.</div></div></div></div></section>
<section class="features-section" id="features"><div class="wide"><div class="section-heading"><div><div class="eyebrow">Built for the way you think</div><h2>Not another folder.<br>A connected knowledge base.</h2></div><p>Save different kinds of information in one place, turn accessible content into searchable text, and return to the right source when you need it.</p></div><div class="features-grid">${[
    [
      "01",
      "One home, many formats",
      "Store notes, articles, PDFs, code, YouTube links, conversation excerpts and recordings.",
    ],
    [
      "02",
      "Search inside, not just by title",
      "Search extracted document text and available transcripts. Optional cloud embeddings add meaning-based retrieval.",
    ],
    [
      "03",
      "Every answer traces back",
      "Ask questions over saved passages and open the original item or a timestamped video moment.",
    ],
    [
      "04",
      "Make it your own",
      "Create collections, tag material and pin useful knowledge. No rigid folder hierarchy.",
    ],
    [
      "05",
      "Keep moving",
      "Set reminders, plan focused sessions and spend more time working than searching.",
    ],
    [
      "06",
      "Your data stays yours",
      "Run locally or connect persistent cloud storage for a hosted workspace.",
    ],
  ]
    .map(
      (x) =>
        `<article class="feature"><span class="number">${x[0]}</span><h3>${x[1]}</h3><p>${x[2]}</p></article>`
    )
    .join("")}</div></div></section>
<section class="wide how" id="how"><div class="how-grid"><div><div class="eyebrow">Simple by intention</div><h2>Capture it today.<br>Understand it tomorrow.</h2><p>Designed as a practical personal knowledge system. Capture information, revisit trusted sources, and make connections between the things you have learned.</p><button class="btn primary" data-command="get-started">Build your space →</button></div><div class="steps"><div class="step"><strong>Capture</strong><p>Drop a document, paste a chat, record a voice memo or add a YouTube link.</p></div><div class="step"><strong>Process</strong><p>Readable document text and accessible captions are indexed. Missing transcripts are clearly marked.</p></div><div class="step"><strong>Rediscover</strong><p>Search for relevant passages or ask a source-grounded question and follow its references.</p></div><div class="step"><strong>Move forward</strong><p>Organize notes and keep your next action close with reminders and a focus timer.</p></div></div></div></section></main><footer class="wide land-footer"><span>© Convexa · A personal knowledge & productivity platform</span><span>Self-hosted. Open-source components. Built for real work.</span></footer></div>`;
}
function renderAuth(register = false) {
  app.innerHTML = `<div class="auth-wrap"><aside class="auth-side">${brand()}<div><div class="eyebrow" style="color:#b8c9b8">A quieter place to think</div><h2>Your knowledge,<br>your space.</h2><p>One private workspace for the information you collect and the ideas you want to remember.</p></div><div class="tiny">Your saved knowledge, organized in one workspace.</div></aside><main class="auth-form"><div class="auth-panel"><button class="btn small ghost" data-command="home">← Back to home</button><div class="eyebrow" style="margin-top:25px">${register ? "Welcome to Convexa" : "Welcome back"}</div><h2>${register ? "Create your space" : "Sign in to your space"}</h2><p>${register ? "Your account keeps your knowledge organized in this workspace." : "Your private knowledge is ready when you are."}</p><form id="auth-form" data-register="${register ? "1" : "0"}"><label for="email">Email</label><input class="field" name="email" id="email" type="email" placeholder="you@example.com" autocomplete="email" required maxlength="180"><label for="password">Password</label><input class="field" name="password" id="password" type="password" placeholder="At least 8 characters" autocomplete="${register ? "new-password" : "current-password"}" minlength="8" required>${register ? '<label for="invite_code">Invitation code (if required)</label><input class="field" id="invite_code" name="invite_code" autocomplete="off">' : ""}<button class="btn primary" type="submit">${register ? "Create account" : "Sign in"} →</button></form><div class="auth-switch tiny">${register ? "Already have an account?" : "New to Convexa?"} <button class="link-button" data-command="auth-mode" data-value="${register ? "login" : "register"}">${register ? "Sign in" : "Create an account"}</button></div><p class="tiny muted">Nothing here requires Google login, a credit card, or a paid API.</p></div></main></div>`;
}
const navEntries = [
  ["all", "▦", "All knowledge"],
  ["favorites", "☆", "Favourites"],
  ["archived", "▤", "Archive"],
  ["ask", "✳", "ARIA assistant"],
  ["reminders", "◷", "Reminders"],
  ["focus", "◉", "Focus timer"],
  ["settings", "⚙", "Settings"],
];
function sidebar() {
  return `<aside class="sidebar"><div class="sidebar-brand">${brand()}<div class="brandsub" style="margin:5px 0 0 44px">YOUR SECOND BRAIN</div></div><div class="sidebar-nav">${navEntries.map(([id, ic, label]) => `<button class="nav-item ${state.view === id ? "active" : ""}" data-command="view" data-value="${id}"><span class="nav-left"><span class="nav-icon">${ic}</span>${label}</span>${id === "all" ? `<span class="nav-count">${state.items.filter((x) => !x.archived).length}</span>` : ""}</button>`).join("")}</div><div class="collection-links"><div class="sidebar-label">Collections <button class="icon-button" style="float:right;margin-top:-8px" title="Add collection" data-command="add-collection">＋</button></div><div class="sidebar-nav">${state.collections.map((c) => `<button class="nav-item ${state.view === "collection" && state.collection === c.id ? "active" : ""}" data-command="collection" data-id="${esc(c.id)}"><span class="nav-left"><span class="nav-icon">▥</span>${esc(c.name)}</span><span class="nav-count">${c.item_count}</span></button>`).join("")}</div></div><div class="sidebar-bottom"><div class="tiny muted">Signed in</div><div class="tiny" style="margin:3px 0 13px">${esc(state.user.email)}</div><button class="btn small" data-command="logout">Sign out</button></div></aside>`;
}
function renderWorkspace() {
  const content =
    state.view === "ask"
      ? renderAsk()
      : state.view === "reminders"
        ? renderReminders()
        : state.view === "focus"
          ? renderFocus()
          : state.view === "settings"
            ? renderSettings()
            : state.view === "detail"
              ? renderDetail()
              : renderKnowledge();
  app.innerHTML = `<div class="workspace">${sidebar()}<div class="main-shell"><header class="app-topbar"><form id="global-search-form" class="search-wrap"><span aria-hidden="true">⌕</span><input id="global-search" aria-label="Search your knowledge" placeholder="Search across your knowledge…" value="${esc(state.query)}" autocomplete="off"><span class="kbd">Enter ↵</span></form><button class="btn primary" data-command="capture">＋ <span class="mobile-hide">Add knowledge</span></button></header><main class="main-area">${content}</main></div></div>`;
  if (state.view === "ask") {
    const t = document.querySelector(".chat-thread");
    if (t) t.scrollTop = t.scrollHeight;
  }
}
function renderKnowledge() {
  const itemViews = {
    all: ["Your knowledge", "A home for the things you want to keep."],
    search: ["Search results", `Search your saved information for “${state.query}”.`],
    favorites: ["Favourites", "A shorter path back to your best resources."],
    archived: ["Archive", "Out of sight, but never lost."],
    collection: ["Collection", "Everything you have gathered here."],
  };
  const [title, description] = itemViews[state.view] || itemViews.all;
  let shown = state.items.filter((x) => (state.view === "archived" ? x.archived : !x.archived));
  if (state.view === "favorites") shown = shown.filter((x) => x.favorite);
  if (state.view === "collection")
    shown = shown.filter((x) => x.collection_id === state.collection);
  if (state.kind) shown = shown.filter((x) => x.kind === state.kind);
  if (state.view === "search") {
    shown = state.searchResults || [];
  }
  const titleHere =
    state.view === "collection"
      ? state.collections.find((c) => c.id === state.collection)?.name || "Collection"
      : title;
  const total = state.items.filter((x) => !x.archived).length;
  let stats =
    state.view === "all"
      ? `<div class="stats"><div class="stat"><b>${total}</b><span>Items saved</span></div><div class="stat"><b>${state.collections.length}</b><span>Collections</span></div><div class="stat"><b>${state.items.filter((x) => !x.archived && x.kind === "youtube").length}</b><span>Video sources</span></div><div class="stat"><b>${state.items.filter((x) => !x.archived && x.transcript).length}</b><span>Transcripts</span></div></div>`
      : "";
  return `<div class="page-heading"><div><div class="eyebrow">YOUR WORKSPACE</div><h1 class="page-title">${esc(titleHere)}</h1>${state.view === "collection" ? `<button class="btn small" data-command="rename-collection">Rename collection</button> <button class="btn small danger" data-command="delete-collection">Delete collection</button>` : ""}<p class="page-intro">${esc(description)}${state.view === "search" ? ` <span class="tiny">${esc(state.searchMode || "")}</span>` : ""}</p></div></div>${stats}
<div class="toolbar"><div class="pill-group">${[
    ["", "All types"],
    ["note", "Notes"],
    ["youtube", "YouTube"],
    ["voice", "Voice"],
    ["file", "Files"],
    ["chat", "Chats"],
    ["web", "Links"],
    ["code", "Code"],
  ]
    .map(
      ([k, label]) =>
        `<button class="pill ${state.kind === k ? "active" : ""}" data-command="filter" data-value="${k}">${label}</button>`
    )
    .join(
      ""
    )}</div><span class="tiny muted">${shown.length} item${shown.length !== 1 ? "s" : ""}</span></div>
${shown.length ? `<div class="entry-list">${shown.map(renderEntry).join("")}</div>` : `<div class="empty"><div class="empty-icon">✳</div><h3>${state.view === "search" ? "Nothing matched your search" : "A little space for something new"}</h3><p>${state.view === "search" ? "Try a related phrase, search an indexed transcript, or add more content." : "Start with a note, PDF, saved conversation or YouTube link. Your knowledge grows from there."}</p><button class="btn primary" data-command="capture">＋ Add your first item</button></div>`}`;
}
function renderEntry(item) {
  const match = item._match;
  const preview =
    match?.excerpt ||
    item.body ||
    item.extracted_text ||
    item.transcript ||
    item.url ||
    "Saved to your knowledge";
  const stamp = match?.start_seconds;
  return `<article class="entry"><span class="icon-sq ${esc(item.kind)}">${esc(icon(item.kind))}</span><div class="entry-main" role="button" tabindex="0" data-command="open-item" data-id="${esc(item.id)}"><div class="entry-title">${esc(item.title)}</div><div class="entry-preview">${esc(preview.slice(0, 250))}</div><div class="entry-meta"><span>${esc(item.kind.toUpperCase())}</span><span>${ago(item.updated_at)}</span>${statusOf(item)}${item.tags.length ? `<span class="entry-tags">${esc(item.tags.map((x) => "#" + x).join(" "))}</span>` : ""}${stamp ? `<span>${Math.floor(stamp / 60)}:${String(Math.floor(stamp % 60)).padStart(2, "0")}</span>` : ""}</div></div>${match?.video_url && urlSafe(match.video_url) ? `<a class="btn small" target="_blank" rel="noopener noreferrer" href="${esc(urlSafe(match.video_url))}">▶ ${Math.floor(stamp / 60)}:${String(Math.floor(stamp % 60)).padStart(2, "0")}</a>` : ""}<div class="entry-actions"><button class="icon-button ${item.favorite ? "on" : ""}" data-command="favorite" data-id="${esc(item.id)}" title="${item.favorite ? "Remove favourite" : "Add favourite"}">${item.favorite ? "★" : "☆"}</button><button class="icon-button" data-command="edit-item" data-id="${esc(item.id)}" title="Edit">✎</button></div></article>`;
}
function renderAsk() {
  const entries = state.chats
    .slice(-30)
    .map(
      (c) =>
        `<div class="chat-message user"><div class="text">${esc(c.question)}</div></div><div class="chat-message assistant"><div class="text">${esc(c.answer)}</div><button class="btn small" style="margin-top:10px" data-command="save-chat" data-id="${esc(c.id)}">Save conversation as knowledge</button>${(c.sources || []).map((s, i) => `<button class="chat-source" data-command="open-item" data-id="${esc(s.id)}">[${i + 1}] ${esc(s.label)}</button>`).join("")}</div>`
    )
    .join("");
  return `<div class="chat-box"><div class="eyebrow">FROM YOUR OWN KNOWLEDGE</div><h1 class="page-title">Ask ARIA</h1><p class="page-intro">Answers point back to saved evidence. With a configured cloud AI provider, ARIA can synthesize passages into cited answers. Your saved sources remain searchable offline.</p><div class="chat-thread" id="chat-thread">${entries || `<div class="empty" style="border:0"><div class="empty-icon">✳</div><h3>Start with what you know.</h3><p>“What did I save about database normalization?”<br>“Which lecture covers React hooks?”</p></div>`}</div><form id="ask-form" class="chat-ask"><textarea class="field" name="question" required placeholder="Ask something about your saved knowledge…" rows="2" maxlength="700"></textarea><button class="btn primary" type="submit">Ask →</button></form><div class="helper" style="text-align:right">${state.capabilities?.ai?.chat && state.capabilities.ai.chat !== "offline" ? "AI provider: " + esc(state.capabilities.ai.chat) : "Offline evidence retrieval active"}</div></div>`;
}
function renderReminders() {
  return `<div class="page-heading"><div><div class="eyebrow">YOUR NEXT STEPS</div><h1 class="page-title">Reminders</h1><p class="page-intro">Track the small things that help the big ideas move forward.</p></div></div><div class="two-col"><section class="panel"><h3>Upcoming & saved</h3>${state.reminders.length ? state.reminders.map((r) => `<div class="reminder-row ${r.done ? "done" : ""}"><input aria-label="Mark complete" type="checkbox" data-reminder-check="${esc(r.id)}" ${r.done ? "checked" : ""}><div><b>${esc(r.title)}</b><div class="tiny muted">${esc(new Date(r.due_at).toLocaleString())}</div></div><button class="icon-button" title="Delete reminder" data-command="delete-reminder" data-id="${esc(r.id)}">×</button></div>`).join("") : "<p>No reminders yet. Create your first one.</p>"}</section><section class="panel"><h3>Add a reminder</h3><form id="reminder-form"><label class="form-label">What do you need to do?</label><input class="field" name="title" required maxlength="220" placeholder="Review data mining notes"><label class="form-label">When?</label><input class="field" name="due_at" type="datetime-local" required><button class="btn primary" type="submit" style="margin-top:18px">Add reminder →</button></form><p class="helper" style="margin-top:22px">Reminders are saved to your workspace. On-page alerts work while Convexa is open; background system notifications are not guaranteed while the browser is closed.</p></section></div>`;
}
const fmtClock = (sec) =>
  `${String(Math.floor(Math.max(0, sec) / 60)).padStart(2, "0")}:${String(Math.floor(Math.max(0, sec) % 60)).padStart(2, "0")}`;
function renderFocus() {
  return `<div class="eyebrow">TIME WITH INTENTION</div><h1 class="page-title">Focus timer</h1><p class="page-intro">One task, one stretch of undivided attention.</p><div class="two-col"><section class="panel" style="text-align:center"><div class="tiny muted">YOUR FOCUS SESSION</div><div class="timer-dial" id="timer-face">${fmtClock(state.clock.remaining)}</div><div class="timer-controls"><button class="btn primary" data-command="timer-toggle">${state.clock.running ? "Pause" : "Start focus"}</button><button class="btn" data-command="timer-reset">Reset</button></div><div class="timer-minutes">${[15, 25, 45, 60].map((m) => `<button class="pill ${state.clock.total === m * 60 ? "active" : ""}" data-command="timer-set" data-value="${m}">${m} min</button>`).join("")}</div></section><section class="panel"><h3>Your sessions</h3><p>Sessions finished: <strong>${state.focus.length}</strong></p><p>Total focused: <strong>${state.focus.reduce((sum, r) => sum + r.minutes, 0)} minutes</strong></p>${state.focus
    .slice(0, 9)
    .map(
      (r) =>
        `<div class="reminder-row"><div><b>${r.minutes} minutes</b><div class="tiny muted">${new Date(r.created_at * 1000).toLocaleString()}</div></div><span class="status">Completed</span></div>`
    )
    .join(
      ""
    )}<p class="helper">Finished sessions are saved to your workspace.</p></section></div>`;
}

function renderSettings() {
  const c = state.capabilities || {},
    ai = c.ai || {};
  const row = (name, ready, detail) =>
    `<div class="reminder-row"><div><b>${name}</b><div class="tiny muted">${esc(detail)}</div></div><span class="status ${ready ? "" : "warn"}">${ready ? (/ARIA|embeddings|Voice transcription/.test(name) ? "Configured" : "Ready") : "Optional"}</span></div>`;
  return `<div class="eyebrow">YOUR SETUP</div><h1 class="page-title">Settings & capabilities</h1><p class="page-intro">Storage, login and text search run on this computer. Optional AI providers process selected passages remotely and require an internet connection.</p><div class="two-col"><section class="panel"><h3>System status</h3>${row("Local database", true, "SQLite, stored on this computer")}${row("PDF extraction", c.pdf, "Install free pypdf if missing")}${row("YouTube caption importer", c.youtube_captions, "Needs accessible published captions")}${row("Voice transcription", !!c.voice_auto, ai.voice || "Enter transcript manually")}${row("ARIA AI answers", ai.chat && ai.chat !== "offline", ai.chat || "Offline evidence retrieval")}${row("Semantic embeddings", ai.embeddings && ai.embeddings !== "none", ai.embeddings || "Keyword search fallback")}<div class="helper">${Number(c.vector_chunks || 0)} of ${Number(c.total_chunks || 0)} passages have stored embeddings. Rebuild the index after adding knowledge.</div><button class="btn primary" style="margin-top:10px" data-command="reindex">Build semantic index</button><button class="btn" style="margin-top:10px" data-command="refresh-settings">Refresh status</button><button class="btn" style="margin-top:10px" data-command="test-ai">Test cloud connections</button><p class="helper">Testing sends small synthetic text requests and may consume quota or incur API charges; voice needs a separate real recording.</p></section><section class="panel"><h3>AI connections</h3><p>Connect an AI provider in Settings to personalize your Convexa experience.</p><label class="form-label">For free-tier AI chat + transcription</label><code>GROQ_API_KEY=your_key</code><label class="form-label">For free-tier neural semantic search</label><code>GEMINI_API_KEY=your_key</code><label class="form-label">Optional paid OpenAI API</label><code>CONVEXA_AI_PROVIDER=openai</code><code>OPENAI_API_KEY=your_key</code><p class="helper">Cloud providers may have usage limits, changing pricing and data processing policies. OpenAI usage may incur charges. Without keys, knowledge storage and extractive search still work.</p><p class="helper">See CLOUD_AI_SETUP.md for key setup, provider selection, privacy and troubleshooting.</p></section></div>`;
}

function renderDetail() {
  let item = state.detail;
  if (!item) return renderKnowledge();
  const videoId = (() => {
    try {
      const u = new URL(item.url);
      if (u.hostname.includes("youtu.be")) return u.pathname.split("/")[1];
      return u.searchParams.get("v") || u.pathname.split("/").pop();
    } catch {
      return null;
    }
  })();
  const goodVideo = videoId && /^[\w-]{11}$/.test(videoId);
  const safe = urlSafe(item.url);
  return `<button class="btn small ghost" data-command="back">← Back to knowledge</button><div class="detail-header" style="margin-top:25px"><span class="icon-sq ${esc(item.kind)}">${esc(icon(item.kind))}</span><div><div class="eyebrow">${esc(item.kind)} · ${ago(item.updated_at)}</div><h1 class="page-title" style="margin-top:5px">${esc(item.title)}</h1></div></div><div class="detail-footer">${statusOf(item)}${item.tags.map((x) => `<span class="status">#${esc(x)}</span>`).join("")}<button class="btn small" data-command="edit-item" data-id="${esc(item.id)}">Edit item</button><button class="btn small" data-command="favorite" data-id="${esc(item.id)}">${item.favorite ? "★ Favourited" : "☆ Favourite"}</button><button class="btn small" data-command="archive" data-id="${esc(item.id)}">${item.archived ? "Restore" : "Archive"}</button><button class="btn small danger" data-command="delete-item" data-id="${esc(item.id)}">Delete</button>${["youtube", "web", "github", "voice"].includes(item.kind) ? `<button class="btn small" data-command="refresh-source" data-id="${esc(item.id)}">Retry import</button>` : ""}</div>${item.meta?.processing_error ? `<p class="helper-warning">${esc(item.meta.processing_error)}</p>` : ""}${safe ? `<p>Original source: <a class="detail-link" target="_blank" rel="noopener noreferrer" href="${eattr(safe)}">${esc(safe)}</a></p>` : ""}${item.has_file ? `<div class="panel" style="margin-bottom:20px"><h3>Attached file</h3><a class="btn small" href="/api/items/${esc(item.id)}/file" download="${esc(item.filename)}">↓ ${esc(item.filename || "Download file")}</a>${item.kind === "voice" ? `<audio controls preload="metadata" src="/api/items/${esc(item.id)}/file" style="width:100%;margin-top:15px"></audio>` : ""}${item.kind === "image" ? `<img style="max-width:100%;max-height:400px;display:block;margin-top:12px" alt="Uploaded image" src="/api/items/${esc(item.id)}/file">` : ""}</div>` : ""}${item.kind === "youtube" && goodVideo ? `<iframe class="yt-frame" title="Saved YouTube video" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen src="https://www.youtube.com/embed/${esc(videoId)}"></iframe>` : ""}${item.extracted_text ? `<h3 style="margin-top:27px">Extracted document text</h3><div class="detail-content">${esc(item.extracted_text)}</div>` : ""}${item.body ? `<h3 style="margin-top:27px">Saved content</h3><div class="detail-content">${esc(item.body)}</div>` : ""}${item.transcript ? `<h3 style="margin-top:28px">Transcript</h3><div class="detail-content">${esc(item.transcript)}</div>` : ""}${!item.body && !item.transcript && !item.extracted_text ? "<p>No extracted source text is available yet. You can add a description or transcript using Edit.</p>" : ""}`;
}
async function showItem(id) {
  try {
    const r = await api("/api/items/" + id);
    state.detail = r.item;
    state.view = "detail";
    renderWorkspace();
  } catch (e) {
    toast(e.message, true);
  }
}
function captureModal(kind = "note", item = null, prefill = null) {
  state.editing = item;
  state.file = null;
  state.recorded = null;
  const tabs = ["note", "youtube", "web", "chat", "voice", "file", "code"];
  const names = {
    note: "Note",
    youtube: "YouTube",
    web: "Web link",
    chat: "Chat",
    voice: "Voice",
    file: "File",
    code: "Code",
  };
  const title = item ? "Edit knowledge" : "Add knowledge";
  const label =
    kind === "youtube"
      ? "YouTube title"
      : kind === "voice"
        ? "Voice note title"
        : kind === "chat"
          ? "Conversation title"
          : "Title";
  let extra = "";
  const v = (k) => esc((item || prefill)?.[k] || "");
  if (["youtube", "web"].includes(kind))
    extra += `<label class="form-label">${kind === "youtube" ? "YouTube video link" : "Website URL"}</label><input class="field" name="url" type="url" placeholder="${kind === "youtube" ? "https://www.youtube.com/watch?v=…" : "https://example.com/article"}" value="${v("url")}" required>`;
  if (kind === "voice")
    extra += `<div class="panel" style="padding:17px;margin:17px 0;background:#f4f6f1"><strong>Record in your browser</strong><p class="helper">Allow microphone access on HTTPS or localhost. Browser speech recognition works where supported; Convexa can use a connected transcription provider; you can also paste a transcript yourself.</p><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn small" type="button" data-command="record-start">● Record</button><button class="btn small" type="button" data-command="record-stop">■ Stop</button></div><p class="helper" id="record-status">Not recording</p></div>`;
  if (["file", "voice"].includes(kind))
    extra += `<label class="form-label">${kind === "voice" ? "Audio file (or record above)" : "Upload document, image, or file"}</label><input class="field" id="capture-file" type="file" ${kind === "voice" ? 'accept="audio/*"' : ""}><div id="sample-file-status" class="helper" role="status"></div><div class="helper">Documents are indexed if readable. Audio stays attached even without a transcript. Max ${((state.capabilities?.max_upload_bytes || 4000000) / 1000000).toFixed(1)} MB.</div>`;
  if (kind === "youtube" || kind === "voice")
    extra += `<label class="form-label">Transcript ${kind === "youtube" ? "(optional if published captions are available)" : "(recommended)"}</label><textarea class="field" name="transcript" rows="5" placeholder="Paste spoken content here. Optional timestamps: 01:25 explanation…">${v("transcript")}</textarea><div class="helper">Timestamped lines make it possible to jump to the relevant part of a saved YouTube lecture.</div>`;
  extra += `<label class="form-label">${kind === "chat" ? "Conversation text" : kind === "code" ? "Code / explanation" : kind === "web" ? "Article excerpt (automatic extraction also attempted)" : "Notes or content"}</label><textarea class="field" name="body" rows="${kind === "chat" ? 7 : 4}" placeholder="${kind === "chat" ? "Paste the chat exchange to make it searchable…" : "Save your thoughts, context, or supporting text…"}">${v("body")}</textarea>`;
  modal.innerHTML = `<div class="modal-layer" id="modal-layer"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="capture-heading"><div class="modal-header"><div><div class="eyebrow">CAPTURE & CONNECT</div><h2 id="capture-heading">${title}</h2></div><button class="icon-button" type="button" data-command="close-modal" aria-label="Close dialog">✕</button></div>${item ? "" : `<div class="capture-tabs">${tabs.map((k) => `<button type="button" class="capture-tab ${kind === k ? "active" : ""}" data-command="capture-tab" data-value="${k}">${names[k]}</button>`).join("")}</div>`}<form id="capture-form" data-kind="${kind}" data-id="${item?.id || ""}">${!item && knowledgeSamples[kind] ? `<div class="sample-guide"><div><strong>Try a DBMS example</strong><p class="helper">Fill an editable sample to explore this knowledge type. Save when you are ready.${kind === "youtube" ? " Captions depend on availability; you can also paste a transcript." : ""}</p></div><button class="btn small" type="button" data-command="capture-sample">Use sample</button></div>` : ""}<label class="form-label">${label}</label><input class="field" name="title" required maxlength="220" value="${v("title")}" placeholder="A name you will remember"><div class="form-grid"><div><label class="form-label">Collection</label><select class="field" name="collection"><option value="">No collection</option>${state.collections.map((c) => `<option value="${esc(c.id)}" ${item?.collection_id === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div><div><label class="form-label">Tags</label><input class="field" name="tags" value="${esc((item?.tags || []).join(", "))}" placeholder="college, research, dbms"></div></div>${extra}<div class="form-actions"><button class="btn" type="button" data-command="close-modal">Cancel</button><button class="btn primary" type="submit" id="capture-submit">${item ? "Save changes" : "Save to knowledge"} →</button></div></form></div></div>`;
  document.querySelector("#capture-form [name=title]")?.focus();
}
async function closeModal() {
  if (state.recorder && state.recorder.state === "recording") state.recorder.stop();
  if (state.recognizer)
    try {
      state.recognizer.stop();
    } catch {}
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
  state.recorder = null;
  state.stream = null;
  state.recognizer = null;
  state.file = null;
  state.recorded = null;
  modal.innerHTML = "";
}
async function recordStart() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    toast(
      "Microphone recording is unavailable in this browser. Upload an audio file instead.",
      true
    );
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.stream = stream;
    const parts = [];
    const options = {};
    if (MediaRecorder.isTypeSupported("audio/webm")) options.mimeType = "audio/webm";
    else if (MediaRecorder.isTypeSupported("audio/ogg")) options.mimeType = "audio/ogg";
    const recorder = new MediaRecorder(stream, options);
    state.recorder = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size) parts.push(e.data);
    };
    recorder.onstop = () => {
      state.recorded = new File(
        parts,
        `voice-${Date.now()}.${(recorder.mimeType || "audio/webm").includes("ogg") ? "ogg" : "webm"}`,
        { type: recorder.mimeType || "audio/webm" }
      );
      const display = document.querySelector("#record-status");
      if (display)
        display.textContent = `Recording ready (${Math.round(state.recorded.size / 1024)} KB). Save to attach it.`;
      stream.getTracks().forEach((t) => t.stop());
    };
    recorder.start(600);
    let msg = "Recording… browser speech-to-text not available; add a manual transcript.";
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (Recognition) {
      try {
        const speech = new Recognition();
        speech.continuous = true;
        speech.interimResults = false;
        speech.lang = "en-US";
        speech.onresult = (e) => {
          const box = document.querySelector("#capture-form [name=transcript]");
          if (!box) return;
          for (let i = e.resultIndex; i < e.results.length; i++)
            if (e.results[i].isFinal) {
              box.value += (box.value ? "\n" : "") + e.results[i][0].transcript.trim();
            }
        };
        speech.onerror = () => {
          const status = document.querySelector("#record-status");
          if (status)
            status.textContent =
              "Recording… automatic speech transcription unavailable. You can type a transcript.";
        };
        speech.start();
        state.recognizer = speech;
        msg =
          "Recording… speech recognition requested; results will appear in the transcript field.";
      } catch {}
    }
    document.querySelector("#record-status").textContent = msg;
  } catch (e) {
    toast("Could not access microphone: " + e.message, true);
  }
}
function recordStop() {
  if (state.recorder?.state === "recording") state.recorder.stop();
  if (state.recognizer)
    try {
      state.recognizer.stop();
    } catch {}
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
}
async function submitCapture(form) {
  const kind = form.dataset.kind;
  const id = form.dataset.id;
  const val = (name) => String(form.elements.namedItem(name)?.value || "");
  const body = {
    kind,
    title: val("title"),
    body: val("body"),
    transcript: val("transcript"),
    url: val("url"),
    tags: val("tags").split(","),
    collection_id: val("collection") || null,
  };
  const file = state.file || state.recorded;
  const limit = state.capabilities?.max_upload_bytes || 4000000;
  if (file && file.size > limit) throw Error(`File exceeds the ${(limit / 1000000).toFixed(1)} MB upload limit.`);
  if ((kind === "file" || kind === "voice") && !id && !file) {
    toast("Please select or record a file before saving.", true);
    return;
  }
  const button = document.querySelector("#capture-submit");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const response = id
      ? await api("/api/items/" + id, { method: "PATCH", body })
      : await api("/api/items", { method: "POST", body });
    const saved = response.item;
    if (file) {
      const url = "/api/items/" + saved.id + "/file?filename=" + encodeURIComponent(file.name);
      await api(url, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
    }
    await closeModal();
    state.query = "";
    state.kind = "";
    state.view = "all";
    await refreshAll();
    renderWorkspace();
    toast(
      "Saved to your knowledge. " +
        (kind === "youtube"
          ? "Caption import runs when available."
          : "You can find it using search.")
    );
  } catch (e) {
    toast("Could not save: " + e.message, true);
    button.disabled = false;
    button.textContent = "Try again";
  }
}
async function doSearch() {
  const term = state.query.trim();
  state.view = term ? "search" : "all";
  if (!term) {
    state.searchResults = [];
    renderWorkspace();
    return;
  }
  try {
    const q = new URLSearchParams({ q: term, semantic: "1" });
    if (state.kind) q.set("kind", state.kind);
    const data = await api("/api/items?" + q);
    state.searchResults = data.results.map((hit) => ({
      ...hit.item,
      _match: hit.match,
    }));
    state.searchMode = data.mode;
    renderWorkspace();
  } catch (e) {
    toast(e.message, true);
  }
}
async function savePatch(id, body, rerender = true) {
  await api("/api/items/" + id, { method: "PATCH", body });
  await refreshAll();
  if (state.view === "detail" && state.detail?.id === id) {
    const r = await api("/api/items/" + id);
    state.detail = r.item;
  }
  if (rerender) {
    if (state.view === "search") await doSearch();
    else renderWorkspace();
  }
}
async function handleCommand(cmd, el) {
  const id = el.dataset.id;
  switch (cmd) {
    case "home":
      navigate("/");
      break;
    case "get-started":
      navigate(state.user ? "/app" : "/login");
      break;
    case "auth-mode":
      renderAuth(el.dataset.value === "register");
      break;
    case "logout":
      await api("/api/logout", { method: "POST" });
      state.user = null;
      state.csrf = "";
      state.view = "all";
      navigate("/");
      break;
    case "view":
      state.view = el.dataset.value;
      state.kind = "";
      state.query = "";
      renderWorkspace();
      break;
    case "collection":
      state.view = "collection";
      state.collection = id;
      state.kind = "";
      renderWorkspace();
      break;
    case "filter":
      state.kind = el.dataset.value;
      if (state.view === "search") await doSearch();
      else renderWorkspace();
      break;
    case "capture":
      captureModal();
      break;
    case "save-chat": {
      const conversation = state.chats.find((c) => c.id === id);
      if (conversation)
        captureModal("chat", null, {
          title: "ARIA discussion — " + conversation.question.slice(0, 120),
          body:
            "QUESTION\n" +
            conversation.question +
            "\n\nARIA RESPONSE\n" +
            conversation.answer +
            "\n\nSOURCES\n" +
            conversation.sources.map((s) => s.label + (s.url ? " — " + s.url : "")).join("\n"),
          tags: ["aria", "conversation"],
        });
      break;
    }
    case "capture-sample":
      fillKnowledgeSample();
      break;
    case "capture-tab":
      captureModal(el.dataset.value);
      break;
    case "close-modal":
      await closeModal();
      break;
    case "open-item":
      await showItem(id);
      break;
    case "back":
      state.view = "all";
      renderWorkspace();
      break;
    case "edit-item": {
      const r = await api("/api/items/" + id);
      captureModal(r.item.kind, r.item);
      break;
    }
    case "favorite": {
      const item = state.items.find((x) => x.id === id) || state.detail;
      await savePatch(id, { favorite: !item.favorite });
      break;
    }
    case "archive":
      await savePatch(id, { archived: !state.detail.archived });
      break;
    case "delete-item":
      if (confirm("Delete this item and its attached file permanently?")) {
        await api("/api/items/" + id, { method: "DELETE" });
        state.view = "all";
        await refreshAll();
        renderWorkspace();
        toast("Item deleted");
      }
      break;
    case "delete-reminder":
      await api("/api/reminders/" + id, { method: "DELETE" });
      await refreshAll();
      renderWorkspace();
      break;
    case "rename-collection": {
      const current = state.collections.find((c) => c.id === state.collection);
      if (!current) break;
      const name = prompt("Rename collection", current.name);
      if (name?.trim()) {
        await api("/api/collections/" + current.id, {
          method: "PATCH",
          body: { name: name.trim() },
        });
        await refreshAll();
        renderWorkspace();
      }
      break;
    }
    case "delete-collection":
      if (confirm("Delete this collection? Saved knowledge will remain available.")) {
        await api("/api/collections/" + state.collection, { method: "DELETE" });
        state.view = "all";
        state.collection = "";
        await refreshAll();
        renderWorkspace();
        toast("Collection removed; notes are safe");
      }
      break;
    case "add-collection": {
      const name = prompt("Name your collection");
      if (name?.trim()) {
        await api("/api/collections", {
          method: "POST",
          body: { name: name.trim() },
        });
        await refreshAll();
        renderWorkspace();
        toast("Collection created");
      }
      break;
    }
    case "record-start":
      await recordStart();
      break;
    case "record-stop":
      recordStop();
      break;
    case "refresh-source":
      await api("/api/items/" + id + "/refresh", { method: "POST" });
      toast("Source import started. Refresh the item to check its status.");
      break;
    case "refresh-settings":
      state.capabilities = await api("/api/capabilities");
      renderWorkspace();
      toast("System status updated");
      break;
    case "test-ai": {
      if (
        !confirm(
          "Send small test prompts to the configured AI providers? Free quotas or API charges may apply. No private notes are sent."
        )
      )
        break;
      const r = await api("/api/ai/test", { method: "POST", body: {} });
      state.aiTestResults = r.results;
      renderWorkspace();
      const x = r.results;
      alert(
        "Chat (" +
          x.chat.provider +
          "): " +
          x.chat.status +
          "\nEmbeddings (" +
          x.embeddings.provider +
          "): " +
          x.embeddings.status +
          "\nVoice (" +
          x.voice.provider +
          "): " +
          x.voice.status
      );
      break;
    }
    case "reindex": {
      toast("Indexing saved passages using your configured embedding provider…");
      let r, total = 0;
      do {
        r = await api("/api/semantic/reindex", {method: "POST", body: {}});
        total += r.indexed_chunks;
        toast(`${total} passages indexed; ${r.remaining || 0} remaining…`);
      } while (r.remaining > 0 && r.indexed_chunks > 0);
      state.capabilities = await api("/api/capabilities");
      renderWorkspace();
      toast(`${total} passages indexed`);
      break;
    }
    case "timer-toggle":
      toggleTimer();
      break;
    case "timer-reset":
      resetTimer();
      break;
    case "timer-set":
      setTimer(Number(el.dataset.value));
      break;
    default:
      break;
  }
}
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-command]");
  if (!btn) return;
  e.preventDefault();
  try {
    await handleCommand(btn.dataset.command, btn);
  } catch (err) {
    toast(err.message, true);
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && modal.innerHTML) closeModal();
  if ((e.key === "Enter" || e.key === " ") && e.target.matches('[role="button"][data-command]')) {
    e.preventDefault();
    e.target.click();
  }
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "capture-file") {
    state.file = e.target.files?.[0] || null;
    const status = document.querySelector("#sample-file-status");
    if (status) status.textContent = "";
  }
  if (e.target.dataset.reminderCheck) {
    try {
      await api("/api/reminders/" + e.target.dataset.reminderCheck, {
        method: "PATCH",
        body: { done: e.target.checked },
      });
      await refreshAll();
      renderWorkspace();
    } catch (err) {
      toast(err.message, true);
    }
  }
});
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const form = e.target;
    if (form.id === "auth-form") {
      const r = await api(form.dataset.register === "1" ? "/api/register" : "/api/login", {
        method: "POST",
        body: {
          email: form.elements.namedItem("email").value,
          password: form.elements.namedItem("password").value,
          invite_code: form.elements.namedItem("invite_code")?.value || "",
        },
      });
      state.user = r.user;
      state.csrf = r.csrf;
      await refreshAll();
      state.view = "all";
      navigate("/app");
      toast("Welcome to your workspace");
    } else if (form.id === "global-search-form") {
      state.query = document.querySelector("#global-search").value;
      await doSearch();
    } else if (form.id === "capture-form") {
      await submitCapture(form);
    } else if (form.id === "reminder-form") {
      await api("/api/reminders", {
        method: "POST",
        body: {
          title: form.elements.namedItem("title").value,
          due_at: new Date(form.elements.namedItem("due_at").value).toISOString(),
        },
      });
      await refreshAll();
      renderWorkspace();
      toast("Reminder added");
    } else if (form.id === "ask-form") {
      const question = form.elements.namedItem("question").value.trim();
      if (!question) return;
      const submit = form.querySelector("[type=submit]");
      submit.disabled = true;
      submit.textContent = "Thinking…";
      try {
        const result = await api("/api/ask", {
          method: "POST",
          body: { question },
        });
        state.lastAnswer = result;
        const chats = await api("/api/chat/history");
        state.chats = chats.messages;
        renderWorkspace();
      } finally {
        submit.disabled = false;
      }
    }
  } catch (err) {
    toast(err.message, true);
  }
});
function setTimer(minutes) {
  state.clock.running = false;
  state.clock.total = minutes * 60;
  state.clock.remaining = minutes * 60;
  renderWorkspace();
}
function resetTimer() {
  state.clock.running = false;
  state.clock.remaining = state.clock.total;
  renderWorkspace();
}
function toggleTimer() {
  const t = state.clock;
  t.running = !t.running;
  t.last = Date.now();
  renderWorkspace();
}
setInterval(async () => {
  const t = state.clock;
  if (!t.running) return;
  const now = Date.now();
  const elapsed = (now - t.last) / 1000;
  t.last = now;
  t.remaining = Math.max(0, t.remaining - elapsed);
  const face = document.querySelector("#timer-face");
  if (face) face.textContent = fmtClock(t.remaining);
  if (t.remaining <= 0) {
    t.running = false;
    const minutes = Math.max(1, Math.round(t.total / 60));
    try {
      await api("/api/focus", { method: "POST", body: { minutes } });
      await refreshAll();
      if (state.view === "focus") renderWorkspace();
    } catch (e) {
      toast("Timer finished but session could not be saved: " + e.message, true);
    }
    toast("Focus session complete. Nice work.");
    if ("Notification" in window && Notification.permission === "granted")
      new Notification("Convexa — Focus complete");
  }
}, 300);
async function refreshProcessingItems() {
  const pending = x => x && ["fetching_captions", "fetching_webpage", "transcription_pending", "processing"].includes(x.status);
  if (!state.user || (!state.items.some(pending) && !pending(state.detail))) return;
  const detailId = state.view === "detail" && pending(state.detail) ? state.detail.id : null;
  try {
    await refreshItems();
    if (detailId) {
      const r = await api("/api/items/" + detailId);
      if (state.view === "detail" && state.detail?.id === detailId) {
        state.detail = r.item;
        // Do not reload the playing video for every poll.
        if (!pending(r.item)) renderWorkspace();
      }
    } else if (state.view === "all" && !document.querySelector("#capture-form")) renderWorkspace();
  } catch {}
}
setInterval(refreshProcessingItems, 3000);
const alreadyAlerted = new Set();
setInterval(() => {
  if (!state.user) return;
  const due = state.reminders.filter(
    (r) => !r.done && new Date(r.due_at).getTime() <= Date.now() && !alreadyAlerted.has(r.id)
  );
  for (const r of due) {
    alreadyAlerted.add(r.id);
    toast("Reminder due: " + r.title);
    if ("Notification" in window && Notification.permission === "granted")
      new Notification("Convexa reminder", { body: r.title });
  }
}, 30000);
// Convexa interface extensions are loaded after this file.
