"use strict";
/* Convexa product surfaces. Runs after core code, before boot(), and reuses its API/auth flow. */
state.aiSettings = null;
state.mapData = { nodes: [], edges: [] };
state.mapScale = 1;
state.mapShowSuggestions = false;
state.aiTestResults = null;
state.mapLinkSource = null;
state.mobileNavOpen = false;
navEntries.splice(4, 0, ["map", "◌", "Knowledge map"]);
navEntries.splice(navEntries.length - 1, 0, ["why", "◎", "Why Convexa"]);

const baseRenderRoute = renderRoute;
renderRoute = function () {
  if (location.pathname === "/why-convexa") {
    renderPublicWhy();
    return;
  }
  baseRenderRoute();
};
const baseRenderLanding = renderLanding;
renderLanding = function () {
  baseRenderLanding();
  const link = app.querySelector('.topnav .navlinks a[href="#features"]');
  if (link) {
    link.href = "/why-convexa";
    link.dataset.command = "why-public";
    link.textContent = "Why Convexa";
  }
};
const baseRefreshAll = refreshAll;
refreshAll = async function () {
  await baseRefreshAll();
  if (state.user) {
    try {
      const r = await api("/api/ai/settings");
      state.aiSettings = r.settings;
    } catch {
      state.aiSettings = null;
    }
  }
};

sidebar = function () {
  return `<aside class="sidebar ${state.mobileNavOpen ? "open" : ""}" aria-label="Workspace navigation">
  <div class="sidebar-brand">${brand()}<div class="brandsub" style="margin:5px 0 0 44px">YOUR SECOND BRAIN</div></div>
  <nav class="sidebar-nav" aria-label="Convexa sections">${navEntries
    .map(
      ([
        id,
        ic,
        label,
      ]) => `<button class="nav-item ${state.view === id ? "active" : ""}" data-command="view" data-value="${id}" ${state.view === id ? 'aria-current="page"' : ""}>
    <span class="nav-left"><span class="nav-icon" aria-hidden="true">${ic}</span><span class="label-text">${esc(label)}</span></span>${id === "all" ? `<span class="nav-count">${state.items.filter((x) => !x.archived).length}</span>` : ""}</button>`
    )
    .join("")}</nav>
  <div class="collection-links"><div class="sidebar-label">Collections <button class="icon-button" style="float:right;margin-top:-8px" title="Add collection" data-command="add-collection" aria-label="Add collection">＋</button></div>
    <nav class="sidebar-nav">${state.collections.map((c) => `<button class="nav-item ${state.view === "collection" && state.collection === c.id ? "active" : ""}" data-command="collection" data-id="${esc(c.id)}"><span class="nav-left"><span class="nav-icon">▥</span><span class="label-text">${esc(c.name)}</span></span><span class="nav-count">${c.item_count}</span></button>`).join("")}</nav></div>
  <div class="sidebar-bottom"><div class="tiny muted">Signed in</div><div class="tiny" style="margin:3px 0 13px">${esc(state.user.email)}</div><button class="btn small" data-command="logout">Sign out</button></div>
</aside>`;
};
renderWorkspace = function () {
  const views = {
    ask: renderAsk,
    reminders: renderReminders,
    focus: renderFocus,
    settings: renderSettings,
    detail: renderDetail,
    map: renderMap,
    why: renderWhy,
  };
  const content = views[state.view] ? views[state.view]() : renderKnowledge();
  app.innerHTML = `<div class="workspace">${sidebar()}<div class="workspace-backdrop ${state.mobileNavOpen ? "open" : ""}" data-command="menu-toggle" aria-hidden="true"></div>
    <div class="main-shell"><header class="app-topbar"><button class="btn mobile-menu-btn" data-command="menu-toggle" aria-label="Open navigation" aria-expanded="${state.mobileNavOpen}">☰</button>
      <form id="global-search-form" class="search-wrap" role="search"><span aria-hidden="true">⌕</span><input id="global-search" aria-label="Search your knowledge" placeholder="Search across your knowledge…" value="${esc(state.query)}" autocomplete="off"><span class="kbd">Enter ↵</span></form>
      <button class="btn primary" data-command="capture">＋ <span class="mobile-hide">Add knowledge</span></button></header><main class="main-area">${content}</main></div></div>`;
  if (state.view === "ask") {
    const t = document.querySelector(".chat-thread");
    if (t) t.scrollTop = t.scrollHeight;
  }
  if (state.view === "map") {
    wireMap();
  }
};

const baseRenderDetail = renderDetail;
function parseTranscript(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => {
      const m = line.match(/^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(.+)$/);
      if (!m) return { time: null, text: line };
      let seconds = 0;
      for (const part of m[1].split(":")) seconds = seconds * 60 + Number(part);
      return { time: m[1], seconds, text: m[2] };
    })
    .filter((s) => s.text.trim());
}
renderDetail = function () {
  const item = state.detail;
  if (!item || item.kind !== "youtube") return baseRenderDetail();
  let videoId = null;
  try {
    const u = new URL(item.url);
    videoId = u.hostname.includes("youtu.be")
      ? u.pathname.split("/")[1]
      : u.searchParams.get("v") || u.pathname.split("/").pop();
  } catch {}
  const videoOk = videoId && /^[\w-]{11}$/.test(videoId);
  const source = urlSafe(item.url);
  const transcript = parseTranscript(item.transcript).slice(0, 1100);
  const transcriptHtml = transcript
    .map((seg) =>
      seg.time
        ? `<button type="button" class="transcript-segment" data-command="yt-seek" data-seconds="${seg.seconds}" title="Play from ${esc(seg.time)}"><span class="stamp">${esc(seg.time)}</span><span class="spoken">${esc(seg.text)}</span></button>`
        : `<div class="transcript-segment"><span></span><span class="spoken">${esc(seg.text)}</span></div>`
    )
    .join("");
  const footer = `${statusOf(item)}${item.tags.map((tag) => `<span class="status">#${esc(tag)}</span>`).join("")}<button class="btn small" data-command="edit-item" data-id="${esc(item.id)}">Edit</button><button class="btn small" data-command="favorite" data-id="${esc(item.id)}">${item.favorite ? "★ Favourited" : "☆ Favourite"}</button><button class="btn small" data-command="archive" data-id="${esc(item.id)}">${item.archived ? "Restore" : "Archive"}</button><button class="btn small" data-command="refresh-source" data-id="${esc(item.id)}">Retry captions</button><button class="btn small danger" data-command="delete-item" data-id="${esc(item.id)}">Delete</button>`;
  return `<section class="source-heading"><button class="btn small ghost" data-command="back">← Your knowledge</button><div class="detail-header"><span class="icon-sq youtube">YT</span><div><div class="eyebrow">YOUTUBE · ${ago(item.updated_at)}</div><h1 class="page-title">${esc(item.title)}</h1></div></div><div class="detail-footer">${footer}</div>
    ${source ? `<p class="source-original">Original video · <a class="detail-link" target="_blank" rel="noopener noreferrer" href="${esc(source)}">Open on YouTube ↗</a></p>` : ""}</section>
    ${item.meta?.processing_error ? `<p class="helper-warning">${esc(item.meta.processing_error)}</p>` : ""}
    <div class="source-grid"><section class="video-card"><div class="source-card-label">Saved video <span>Watch alongside your notes</span></div>
      ${videoOk ? `<iframe id="convexa-video" class="yt-frame" title="${esc(item.title)}" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen src="https://www.youtube.com/embed/${esc(videoId)}"></iframe>` : "<p>Video preview is unavailable for this link.</p>"}
      <p class="helper" style="margin:12px 3px 3px">Use transcript timestamps to return to a specific explanation.</p></section>
    <section class="transcript-card" aria-label="Video transcript"><div class="source-card-label">Transcript <span>${transcript.length ? transcript.length + " lines" : (item.status === "fetching_captions" ? "Importing captions…" : "No transcript saved")}</span></div>
      ${transcript.length ? `<input class="transcript-search" type="search" id="transcript-filter" placeholder="Find a phrase in this transcript…" aria-label="Find within transcript"><div class="transcript-list" id="transcript-list">${transcriptHtml}</div>` : `<div class="transcript-plain">${item.status === "fetching_captions" ? "Importing published captions. This panel updates automatically." : "Caption import is not running. Read the message above, then Retry captions, or use Edit to paste the actual transcript."}</div>`}
    </section></div>
    ${item.body ? `<section class="source-article"><h3>Saved notes</h3><div class="detail-content">${esc(item.body)}</div></section>` : ""}`;
};

renderAsk = function () {
  const entries = state.chats
    .slice(-40)
    .map(
      (c) => `<div class="chat-message user"><div class="text">${esc(c.question)}</div></div>
    <div class="chat-message assistant"><div class="text">${esc(c.answer)}</div><button class="btn small" style="margin-top:11px" data-command="save-chat" data-id="${esc(c.id)}">Save as knowledge</button>
    ${(c.sources || []).map((s, i) => `<button class="chat-source" data-command="open-item" data-id="${esc(s.id)}">[${i + 1}] ${esc(s.label)}</button>`).join("")}</div>`
    )
    .join("");
  return `<section class="aria-shell"><header class="aria-head"><div><div class="eyebrow">YOUR KNOWLEDGE ASSISTANT</div><h1 class="page-title">Ask ARIA</h1><p class="aria-sub">Ask across your saved notes, documents, conversations and transcripts. Answers can point you back to the source.</p></div><span class="aria-mode">${state.capabilities?.ai?.chat && state.capabilities.ai.chat !== "offline" ? esc(state.capabilities.ai.chat) + " configured" : "Source-backed retrieval"}</span></header>
    <div class="aria-live"><div class="chat-thread" id="chat-thread">${entries || `<div class="aria-empty"><div><div class="empty-icon">✳</div><h3>Start with what you know.</h3><p>Ask a question about anything you have saved to Convexa.</p><div class="aria-prompts"><button class="pill" data-command="aria-prompt" data-value="What did I save about database normalization?">Database normalization</button><button class="pill" data-command="aria-prompt" data-value="Which sources mention data structures?">Data structures</button></div></div></div>`}</div>
      <form id="ask-form" class="chat-ask"><textarea class="field" name="question" required maxlength="700" rows="2" placeholder="Ask a question about your knowledge…" aria-label="Question for ARIA"></textarea><button class="btn primary" type="submit">Ask →</button></form></div></section>`;
};

renderFocus = function () {
  return `<div class="eyebrow">TIME WITH INTENTION</div><h1 class="page-title">Focus timer</h1><p class="page-intro">Choose a session length that works for you.</p><div class="two-col"><section class="panel" style="text-align:center"><div class="tiny muted">YOUR FOCUS SESSION</div><div class="timer-dial" id="timer-face">${fmtClock(state.clock.remaining)}</div><div class="timer-controls"><button class="btn primary" data-command="timer-toggle">${state.clock.running ? "Pause" : "Start focus"}</button><button class="btn" data-command="timer-reset">Reset</button></div>
    <div class="timer-minutes">${[5, 15, 25, 45, 60].map((m) => `<button class="pill ${state.clock.total === m * 60 ? "active" : ""}" data-command="timer-set" data-value="${m}">${m} min</button>`).join("")}</div>
    <form id="custom-timer-form" style="display:flex;justify-content:center;align-items:end;gap:9px;margin:20px auto 0;flex-wrap:wrap"><div><label class="form-label" for="custom-timer" style="text-align:left">Custom duration</label><input id="custom-timer" class="field" name="minutes" type="number" min="1" max="240" value="${Math.round(state.clock.total / 60)}" style="width:110px" aria-label="Custom duration in minutes"></div><button class="btn" type="submit">Set minutes</button></form>
    <p class="helper">Choose between 1 and 240 minutes. Completed sessions are saved here.</p></section>
    <section class="panel"><h3>Your sessions</h3><p>Sessions finished: <strong>${state.focus.length}</strong></p><p>Total focused: <strong>${state.focus.reduce((sum, r) => sum + r.minutes, 0)} minutes</strong></p>${state.focus
      .slice(0, 9)
      .map(
        (r) =>
          `<div class="reminder-row"><div><b>${r.minutes} minutes</b><div class="tiny muted">${new Date(r.created_at * 1000).toLocaleString()}</div></div><span class="status">Completed</span></div>`
      )
      .join("")}</section></div>`;
};

function providerSelect(name, label, values, selected) {
  return `<div><label for="provider-${name}">${label}</label><select class="field" name="${name}" id="provider-${name}">${values.map(([k, v]) => `<option value="${k}" ${selected === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>`;
}
renderSettings = function () {
  const c = state.capabilities || {},
    ai = c.ai || {},
    settings = state.aiSettings || { providers: {}, keys: {} };
  const configured = settings.keys || {};
  const prefs = settings.providers || {};
  const statusRow = (label, ready, details) =>
    `<div class="reminder-row"><div><b>${label}</b><div class="tiny muted">${details}</div></div><span class="status ${ready ? "" : "warn"}">${ready ? (/^ARIA|^Speech|^Meaning/.test(label) ? "Configured" : "Ready") : (/^ARIA|^Speech|^Meaning/.test(label) ? "Not configured" : "Not installed")}</span></div>`;
  const secretRow = (name, label, description) =>
    `<div class="settings-connection"><div><label for="key-${name}">${label}</label><small>${description}</small><div class="settings-key-row"><input class="field" id="key-${name}" name="${name}" type="password" autocomplete="new-password" placeholder="${configured[name] ? "Key saved · enter to replace" : "Paste your API key"}" aria-label="${label} API key"><button class="btn small" type="button" data-command="toggle-key" data-name="${name}" aria-label="Show ${label} key">Show</button></div></div><div><span class="status ${configured[name] ? "" : "warn"}">${configured[name] ? "Saved" : "Not set"}</span>${configured[name] ? `<button class="btn small danger" type="button" style="display:block;margin-top:9px" data-command="remove-ai-key" data-name="${name}">Remove</button>` : ""}</div></div>`;
  return `<div class="eyebrow">YOUR PREFERENCES</div><h1 class="page-title">Settings</h1><p class="page-intro">Choose how Convexa understands your saved knowledge. Your core workspace remains available with no integrations configured.</p>
  <div class="settings-layout"><section class="settings-panel"><h3>Knowledge capabilities</h3><p>Check what is available in your workspace, then build your search index when you're ready.</p>
  ${statusRow("Local knowledge library", true, "Private SQLite storage and searchable notes")}${statusRow("Document text extraction", !!c.pdf, "PDF, DOCX and text documents")}${statusRow("Video transcripts", !!c.youtube_captions, "Captions for supported YouTube videos")}
  ${statusRow("Speech transcription", !!c.voice_auto, esc(ai.voice || "Manual transcript option"))}${statusRow("ARIA responses", ai.chat && ai.chat !== "offline", esc(ai.chat || "Source-backed retrieval"))}${statusRow("Meaning-based search", ai.embeddings && ai.embeddings !== "none", esc(ai.embeddings || "Local keyword search"))}
  <p class="helper" style="margin-top:13px">${Number(c.vector_chunks || 0)} of ${Number(c.total_chunks || 0)} passages indexed for semantic search.</p>
  <div class="settings-actions"><button class="btn primary" data-command="reindex">Build semantic index</button><button class="btn" data-command="refresh-settings">Refresh status</button><button class="btn" data-command="test-ai">Test connections</button></div>
  <p class="helper">Tests check the selected chat and search services with small sample requests. Voice must be verified by uploading a real recording. A saved key alone does not mean a connection works.</p></section>
  <section class="settings-panel"><h3>AI connections</h3>${state.aiTestResults ? `<div role="status"><h4>Last connection test</h4>${Object.entries(state.aiTestResults).map(([name, result]) => `<p><strong>${esc(name)} · ${esc(result.provider)}</strong><br>${esc(result.status)}</p>`).join("")}</div>` : ""}<p>Connect an AI provider to enable additional features inside Convexa. Save your keys directly here.</p>
   <form id="ai-settings-form" autocomplete="off">${secretRow("groq", "Groq", "ARIA conversations and audio transcription")}${secretRow("gemini", "Gemini", "Knowledge embeddings and optional ARIA responses")}${secretRow("openai", "OpenAI", "Optional chat and speech services; provider billing may apply")}
   <div class="settings-kicker">Preferred services</div><div class="settings-selects">
   ${providerSelect(
     "chat",
     "ARIA answers",
     [
       ["auto", "Automatic"],
       ["groq", "Groq"],
       ["gemini", "Gemini"],
       ["openai", "OpenAI"],
       ["offline", "Source-backed only"],
     ],
     prefs.chat || "auto"
   )}
   ${providerSelect(
     "embeddings",
     "Semantic search",
     [
       ["auto", "Automatic"],
       ["gemini", "Gemini"],
       ["none", "Keyword search only"],
     ],
     prefs.embeddings || "auto"
   )}
   ${providerSelect(
     "voice",
     "Voice transcription",
     [
       ["auto", "Automatic"],
       ["groq", "Groq"],
       ["openai", "OpenAI"],
       ["none", "Manual transcript"],
     ],
     prefs.voice || "auto"
   )}
   </div><button type="submit" class="btn primary">Save connections</button></form>
   <div class="settings-privacy">Keys are sent to the Convexa server and saved encrypted for your account. They are never returned to the browser after saving. AI requests send selected content to the configured provider. Only connect providers you trust with the selected content.</div></section></div>`;
};

function whyContent() {
  return `<div class="why-layout"><nav class="why-index" aria-label="On this page"><div class="sidebar-label">Explore Convexa</div>
  ${[
    ["idea", "The idea"],
    ["capture", "Capture anything"],
    ["retrieve", "Find the meaning"],
    ["connect", "See connections"],
    ["flow", "Stay in flow"],
    ["trust", "Your workspace"],
  ]
    .map(([id, label]) => `<a href="#${id}">${label}</a>`)
    .join("")}</nav>
  <div class="why-body"><div class="eyebrow">THE CONVEXA APPROACH</div><h1 class="page-title" style="font-size:clamp(2.5rem,4vw,4.2rem);margin:12px 0 18px">Why Convexa?</h1>
  <p class="why-lead">Your knowledge doesn't arrive in one format. Why should remembering it require five different places?</p>
  <section class="why-section" id="idea"><div class="eyebrow">01 · ONE PLACE</div><h2>A home for the things you learn</h2><p>Convexa is a personal knowledge and productivity platform for gathering ideas, source material and useful conversations into one searchable space. It helps you return to the information that matters without retracing how you found it.</p></section>
  <section class="why-section" id="capture"><div class="eyebrow">02 · CAPTURE</div><h2>Different formats. One knowledge base.</h2><p>Save notes, documents, YouTube lectures, web resources, voice recordings, code and conversations. Convexa stores the original source alongside extracted or supplied text so your library can grow across the ways you work.</p>
   <div class="why-examples"><div class="why-example"><strong>Lectures and videos</strong><p>Find a moment from saved captions, then jump back to the explanation.</p></div><div class="why-example"><strong>Documents and notes</strong><p>Search text inside a document, not only its filename.</p></div><div class="why-example"><strong>Voice and conversations</strong><p>Keep ideas you said or discussed alongside what you read.</p></div><div class="why-example"><strong>Projects and resources</strong><p>Organize related research with collections, tags and connections.</p></div></div></section>
  <section class="why-section" id="retrieve"><div class="eyebrow">03 · RETRIEVE</div><h2>Search for what you remember</h2><p>Convexa searches indexed content from your sources. When an embedding provider is connected, semantic search can also retrieve passages related to the meaning of your question. ARIA helps you explore saved evidence and can compose source-grounded answers with a configured provider.</p></section>
  <section class="why-section" id="connect"><div class="eyebrow">04 · EXPLORE</div><h2>Make connections visible</h2><p>The knowledge map turns saved items into movable cards. Items with shared collections or tags can be related automatically, and you can create links of your own. Arrange the map the way the ideas make sense to you; Convexa remembers the layout.</p></section>
  <section class="why-section" id="flow"><div class="eyebrow">05 · ACT</div><h2>From collecting to doing</h2><p>Use reminders to come back to something important and the focus timer to give it your attention. You can keep research, reflection and next steps together without losing the original context.</p></section>
  <section class="why-section" id="trust"><div class="eyebrow">06 · CONTROL</div><h2>Your library, your way</h2><p>Convexa supports local or hosted storage and lets you choose whether to connect AI services. Your sources remain retrievable even when AI services are not configured. You choose which knowledge is worth keeping, and how to organize it.</p>
  <button class="btn primary" data-command="get-started">${state.user ? "Explore my knowledge" : "Start with Convexa"} →</button></section></div></div>`;
}
function renderWhy() {
  return whyContent();
}
function renderPublicWhy() {
  app.innerHTML = `<div class="public-why"><header class="topnav wide">${brand()}<nav class="navlinks"><a href="/" data-command="home">Home</a><button class="btn small primary" data-command="get-started">${state.user ? "Open workspace" : "Get started"} →</button></nav></header><main class="wide">${whyContent()}</main><footer class="land-footer wide"><span>Convexa · Your knowledge, together</span><a href="/" data-command="home">Back to homepage</a></footer></div>`;
}

function mapDimensions() {
  const n = state.items.filter((i) => !i.archived).length;
  const rings = Math.max(1, Math.ceil(n / 8));
  return {
    w: 850 + Math.max(0, rings - 1) * 650,
    h: 650 + Math.max(0, rings - 1) * 450,
  };
}
function defaultMapPosition(index, total, dim) {
  const ring = Math.floor(index / 8),
    within = index % 8,
    count = Math.min(8, total - ring * 8);
  const angle = -Math.PI / 2 + ((within + 0.5) * 2 * Math.PI) / count;
  const rx = (total <= 3 ? 220 : 285) + ring * 275,
    ry = (total <= 3 ? 170 : 215) + ring * 230;
  return {
    x: Math.round(dim.w / 2 - 103 + Math.cos(angle) * rx),
    y: Math.round(dim.h / 2 - 55 + Math.sin(angle) * ry),
  };
}
function computedMapNodes(items, dim) {
  const saved = new Map((state.mapData.nodes || []).map((p) => [p.item_id, p]));
  return items.map((item, i) => ({
    item,
    ...(saved.get(item.id) || defaultMapPosition(i, items.length, dim)),
  }));
}
function inferredEdges(items) {
  const edges = [];
  for (let i = 0; i < items.length; i++)
    for (let j = i + 1; j < items.length; j++) {
      const a = items[i],
        b = items[j];
      const sameCollection = a.collection_id && a.collection_id === b.collection_id;
      const shared = (a.tags || []).some((t) => !["sample", "demo"].includes(t.toLowerCase()) && (b.tags || []).includes(t));
      if (sameCollection || shared) edges.push({ source_id: a.id, target_id: b.id, manual: false });
      if (edges.length >= 55) return edges;
    }
  return edges;
}
function renderMap() {
  const items = state.items.filter((i) => !i.archived).slice(0, 40),
    dim = mapDimensions();
  const nodes = computedMapNodes(items, dim);
  const nodeMap = new Map(nodes.map((n) => [n.item.id, n]));
  const allEdges = [
    ...(state.mapShowSuggestions ? inferredEdges(items).filter(e => !(state.mapData.edges || []).some(m => (m.source_id === e.source_id && m.target_id === e.target_id) || (m.source_id === e.target_id && m.target_id === e.source_id))) : []),
    ...(state.mapData.edges || []).map((e) => ({ ...e, manual: true })),
  ];
  const connections = (state.mapData.edges || [])
    .map((e) => ({
      e,
      from: nodeMap.get(e.source_id)?.item.title,
      to: nodeMap.get(e.target_id)?.item.title,
    }))
    .filter((e) => e.from && e.to);
  const scale = state.mapScale;
  return `<div class="map-intro"><div><div class="eyebrow">EXPLORE YOUR IDEAS</div><h1 class="page-title">Knowledge map</h1><p class="page-intro">Move your knowledge around, follow related topics and link ideas that belong together.</p></div>
   <div class="map-toolbar"><button class="btn small" data-command="map-zoom" data-value="-1" aria-label="Zoom out">−</button><span class="tiny muted">${Math.round(scale * 100)}%</span><button class="btn small" data-command="map-zoom" data-value="1" aria-label="Zoom in">＋</button><button class="btn small" data-command="map-reset">Arrange automatically</button></div></div>
   ${
     items.length
       ? `<div class="map-layout"><div><div class="map-viewport" id="map-viewport" aria-label="Interactive knowledge map"><div class="map-scene-size" style="width:${dim.w * scale}px;height:${dim.h * scale}px"><div class="map-scene" id="map-scene" style="width:${dim.w}px;height:${dim.h}px;transform:scale(${scale})">
    <svg class="map-lines" id="map-lines" width="${dim.w}" height="${dim.h}" viewBox="0 0 ${dim.w} ${dim.h}" aria-hidden="true">
     
     ${allEdges
       .filter((e) => nodeMap.has(e.source_id) && nodeMap.has(e.target_id))
       .map((e) => {
         const a = nodeMap.get(e.source_id),
           b = nodeMap.get(e.target_id);
         return `<line class="${e.manual ? "manual" : ""}" data-line-source="${esc(e.source_id)}" data-line-target="${esc(e.target_id)}" x1="${a.x + 103}" y1="${a.y + 55}" x2="${b.x + 103}" y2="${b.y + 55}"></line>`;
       })
       .join("")}
    </svg><div class="map-hub" style="left:${dim.w / 2 - 88}px;top:${dim.h / 2 - 36}px">Convexa<small>My knowledge</small></div>
    ${nodes.map((n) => `<article class="map-node ${state.mapLinkSource === n.item.id ? "selected" : ""}" data-map-id="${esc(n.item.id)}" data-x="${n.x}" data-y="${n.y}" style="left:${n.x}px;top:${n.y}px" tabindex="0" aria-label="${esc(n.item.title)}. Drag to rearrange"><div class="map-node-type">${esc(n.item.kind)} ${n.item.tags?.length ? "· " + esc(n.item.tags[0]) : ""}</div><div class="map-node-title">${esc(n.item.title)}</div><div class="map-node-actions"><button data-command="map-open" data-id="${esc(n.item.id)}">Open</button><button data-command="map-link" data-id="${esc(n.item.id)}">${state.mapLinkSource ? "Select" : "Connect"}</button></div></article>`).join("")}
    </div></div></div><div class="map-legend"><b class="manual">Saved connections</b>${state.mapShowSuggestions ? "<b>Suggestions (not saved links)</b>" : ""}</div></div>
    <aside class="map-side"><h3>Your connections</h3><p>${state.mapLinkSource ? "Select another card to connect it to your chosen item." : "Select Connect on any card, then choose another card. Drag cards to organize your thinking."}</p>
    ${state.mapLinkSource ? `<button class="btn small" data-command="map-cancel-link">Cancel connection</button>` : ""}
    <div class="settings-kicker">Saved links · ${connections.length}</div>
    ${connections.length ? connections.map(({ e, from, to }) => `<div class="map-connection"><span>${esc(from)}<br><span class="muted">↳ ${esc(to)}</span></span><button class="icon-button" data-command="map-unlink" data-id="${esc(e.id)}" title="Remove connection" aria-label="Remove connection">Disconnect</button></div>`).join("") : '<p class="tiny muted">No custom connections yet. Create one to see it here.</p>'}
    <button class="btn small" data-command="map-suggestions" aria-pressed="${state.mapShowSuggestions}">${state.mapShowSuggestions ? "Hide suggestions" : "Show suggestions"}</button><div class="settings-kicker">Discover</div><p class="tiny muted">Only your saved connections appear by default. Suggestions use shared tags or collections and are not saved links. To change a connection, disconnect it and connect the intended pair.</p></aside></div>`
       : `<div class="empty"><div class="empty-icon">◌</div><h3>Your ideas belong here.</h3><p>Save your first note, document or video to begin mapping your knowledge.</p><button class="btn primary" data-command="capture">Add knowledge</button></div>`
   }`;
}
function drawMapLines() {
  document.querySelectorAll("[data-line-hub]").forEach((line) => {
    const node = document.querySelector(
      `.map-node[data-map-id="${CSS.escape(line.dataset.lineHub)}"]`
    );
    if (!node) return;
    line.setAttribute("x2", Number(node.dataset.x) + 103);
    line.setAttribute("y2", Number(node.dataset.y) + 55);
  });
  document.querySelectorAll("[data-line-source]").forEach((line) => {
    const a = document.querySelector(
      `.map-node[data-map-id="${CSS.escape(line.dataset.lineSource)}"]`
    );
    const b = document.querySelector(
      `.map-node[data-map-id="${CSS.escape(line.dataset.lineTarget)}"]`
    );
    if (!a || !b) return;
    line.setAttribute("x1", Number(a.dataset.x) + 103);
    line.setAttribute("y1", Number(a.dataset.y) + 55);
    line.setAttribute("x2", Number(b.dataset.x) + 103);
    line.setAttribute("y2", Number(b.dataset.y) + 55);
  });
}
function wireMap() {
  const viewport = document.querySelector("#map-viewport");
  if (!viewport) return;
  viewport.scrollLeft = Math.max(0, (viewport.scrollWidth - viewport.clientWidth) / 2);
  viewport.scrollTop = Math.max(0, (viewport.scrollHeight - viewport.clientHeight) / 2);
  state.mapViewed = true;
  document.querySelectorAll(".map-node").forEach((node) => {
    let drag = null;
    node.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button")) return;
      drag = {
        px: e.clientX,
        py: e.clientY,
        x: Number(node.dataset.x),
        y: Number(node.dataset.y),
        moved: false,
        pointer: e.pointerId,
      };
      node.setPointerCapture(e.pointerId);
    });
    node.addEventListener("pointermove", (e) => {
      if (!drag || drag.pointer !== e.pointerId) return;
      const dx = (e.clientX - drag.px) / state.mapScale,
        dy = (e.clientY - drag.py) / state.mapScale;
      if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
      node.dataset.x = String(Math.max(0, Math.round(drag.x + dx)));
      node.dataset.y = String(Math.max(0, Math.round(drag.y + dy)));
      node.style.left = node.dataset.x + "px";
      node.style.top = node.dataset.y + "px";
      drawMapLines();
    });
    node.addEventListener("pointerup", async (e) => {
      if (!drag || drag.pointer !== e.pointerId) return;
      const moved = drag.moved;
      drag = null;
      if (!moved) return;
      const id = node.dataset.mapId,
        x = Number(node.dataset.x),
        y = Number(node.dataset.y);
      const existing = (state.mapData.nodes || []).find((n) => n.item_id === id);
      if (existing) {
        existing.x = x;
        existing.y = y;
      } else state.mapData.nodes.push({ item_id: id, x, y });
      try {
        await api("/api/mindmap/nodes/" + id, {
          method: "PATCH",
          body: { x, y },
        });
      } catch (err) {
        toast("Could not save map position: " + err.message, true);
      }
    });
  });
}

const baseHandleCommand = handleCommand;
handleCommand = async function (cmd, el) {
  const id = el.dataset.id;
  if (cmd === "view" || cmd === "collection") {
    state.mobileNavOpen = false;
    if (cmd === "view" && el.dataset.value === "map") {
      state.mapData = await api("/api/mindmap");
      state.mapViewed = false;
    }
  }
  if (cmd === "why-public") {
    navigate("/why-convexa");
    return;
  }
  if (cmd === "menu-toggle") {
    state.mobileNavOpen = !state.mobileNavOpen;
    renderWorkspace();
    return;
  }
  if (cmd === "aria-prompt") {
    const field = document.querySelector("#ask-form textarea");
    if (field) {
      field.value = el.dataset.value;
      field.focus();
    }
    return;
  }
  if (cmd === "toggle-key") {
    const inp = document.querySelector("#key-" + el.dataset.name);
    if (inp) {
      inp.type = inp.type === "password" ? "text" : "password";
      el.textContent = inp.type === "password" ? "Show" : "Hide";
    }
    return;
  }
  if (cmd === "remove-ai-key") {
    if (!confirm("Remove the saved " + el.dataset.name + " API key from this account?")) return;
    const data = await api("/api/ai/settings", {
      method: "POST",
      body: { remove_keys: [el.dataset.name] },
    });
    state.aiTestResults = null;
    state.aiSettings = data.settings;
    state.capabilities = await api("/api/capabilities");
    renderWorkspace();
    toast("Connection removed");
    return;
  }
  if (cmd === "yt-seek") {
    const frame = document.querySelector("#convexa-video");
    if (frame) {
      const url = new URL(frame.src);
      url.searchParams.set("start", String(Math.max(0, Number(el.dataset.seconds) || 0)));
      url.searchParams.set("autoplay", "1");
      frame.src = url.href;
    }
    return;
  }
  if (cmd === "map-suggestions") {
    state.mapShowSuggestions = !state.mapShowSuggestions;
    renderWorkspace();
    return;
  }
  if (cmd === "map-open") {
    await showItem(id);
    return;
  }
  if (cmd === "map-zoom") {
    state.mapScale = Math.max(
      0.65,
      Math.min(1.5, Math.round((state.mapScale + Number(el.dataset.value) * 0.15) * 100) / 100)
    );
    state.mapViewed = false;
    renderWorkspace();
    return;
  }
  if (cmd === "map-reset") {
    await api("/api/mindmap/layout", { method: "DELETE" });
    state.mapData.nodes = [];
    state.mapViewed = false;
    renderWorkspace();
    toast("Map layout arranged");
    return;
  }
  if (cmd === "map-cancel-link") {
    state.mapLinkSource = null;
    renderWorkspace();
    return;
  }
  if (cmd === "map-link") {
    if (!state.mapLinkSource) {
      state.mapLinkSource = id;
      renderWorkspace();
      return;
    }
    if (state.mapLinkSource === id) {
      state.mapLinkSource = null;
      renderWorkspace();
      return;
    }
    const r = await api("/api/mindmap/edge", {
      method: "POST",
      body: { source: state.mapLinkSource, target: id },
    });
    state.mapData.edges = state.mapData.edges.filter(e => e.id !== r.edge.id);
    state.mapData.edges.push(r.edge);
    state.mapLinkSource = null;
    renderWorkspace();
    toast("Knowledge connection created");
    return;
  }
  if (cmd === "map-unlink") {
    await api("/api/mindmap/edges/" + id, { method: "DELETE" });
    state.mapData.edges = state.mapData.edges.filter((e) => e.id !== id);
    renderWorkspace();
    toast("Connection removed");
    return;
  }
  return baseHandleCommand(cmd, el);
};

// Interactive forms and transcript filter share the existing delegated UI framework.
document.addEventListener(
  "submit",
  async (e) => {
    if (!["ai-settings-form", "custom-timer-form"].includes(e.target?.id)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    try {
      if (e.target.id === "custom-timer-form") {
        const mins = Number(e.target.elements.namedItem("minutes").value);
        if (!Number.isInteger(mins) || mins < 1 || mins > 240)
          throw Error("Enter a duration between 1 and 240 minutes");
        setTimer(mins);
        toast("Focus timer set for " + mins + " minutes");
        return;
      }
      const form = e.target;
      const keys = {};
      for (const name of ["groq", "gemini", "openai"]) {
        const value = form.elements.namedItem(name).value.trim();
        if (value) keys[name] = value;
      }
      const providers = {};
      for (const name of ["chat", "embeddings", "voice"])
        providers[name] = form.elements.namedItem(name).value;
      const saveButton = form.querySelector("[type=submit]");
      saveButton.disabled = true;
      saveButton.textContent = "Saving…";
      const data = await api("/api/ai/settings", {
        method: "POST",
        body: { providers, keys },
      });
      state.aiTestResults = null;
    state.aiSettings = data.settings;
      state.capabilities = await api("/api/capabilities");
      renderWorkspace();
      toast("AI connections saved to your workspace");
    } catch (err) {
      toast(err.message, true);
    }
  },
  true
);
document.addEventListener("input", (e) => {
  if (e.target?.id !== "transcript-filter") return;
  const q = e.target.value.toLowerCase().trim();
  document
    .querySelectorAll("#transcript-list .transcript-segment")
    .forEach((row) => (row.hidden = !!q && !row.textContent.toLowerCase().includes(q)));
});

boot();
