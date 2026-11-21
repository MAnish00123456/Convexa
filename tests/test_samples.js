// Run with node tests/test_samples.js. Tests draft behavior without a browser.
const vm = require("node:vm");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const { File } = require("node:buffer");
let form,
  confirmed = true;
const context = vm.createContext({
  File,
  state: { file: null },
  document: { querySelector: () => form },
  confirm: () => confirmed,
  toast: () => {},
});
vm.runInContext(
  fs.readFileSync(require("node:path").join(__dirname, "../web/samples.js"), "utf8"),
  context
);
for (const kind of ["note", "youtube", "web", "chat", "file", "code", "voice"]) {
  const fields = Object.fromEntries(
    ["title", "tags", "body", "url", "transcript"].map((name) => [name, { value: "", focus() {} }])
  );
  const input = { value: "" },
    status = { textContent: "" };
  form = {
    dataset: { kind, id: "" },
    elements: { namedItem: (name) => fields[name] },
    querySelector: (selector) =>
      selector === "#capture-file"
        ? input
        : selector === "#sample-file-status"
          ? status
          : fields.title,
  };
  context.state.file = null;
  vm.runInContext("fillKnowledgeSample()", context);
  if (kind === "voice") {
    assert.equal(fields.title.value, "");
    continue;
  }
  assert.ok(fields.title.value);
  assert.ok(fields.body.value);
  if (kind === "youtube") {
    assert.ok(fields.url.value.includes("6Iu45VZGQDk"));
    assert.equal(fields.transcript.value, "");
  }
  if (kind === "file") {
    assert.equal(context.state.file.name, "dbms-sample-notes.txt");
    assert.ok(context.state.file.size > 100);
    assert.ok(status.textContent.includes(".txt"));
  }
  fields.title.value = "My draft";
  confirmed = false;
  vm.runInContext("fillKnowledgeSample()", context);
  assert.equal(fields.title.value, "My draft");
  confirmed = true;
  form.dataset.id = "existing";
  vm.runInContext("fillKnowledgeSample()", context);
  assert.equal(fields.title.value, "My draft");
}
console.log(
  "PASS: six sample types, file attachment fallback, YouTube URL, no fabricated transcript, voice excluded, draft cancellation and edit protection"
);
