// Knowledge Vault: upload documents through /api/ingest and keep a list of what was uploaded from this browser.
// The server has no "list documents" endpoint yet, so the list below is this browser's own upload history.

const MAX_BYTES = 10 * 1024 * 1024; // same limit the server enforces
const SUPPORTED = ["pdf", "md", "docx", "txt"];
const PAGE_SIZE = 8;
const KIND_LABEL = { pdf: "PDF", md: "Markdown", docx: "Word", txt: "Text" };
const KIND_BADGE = { pdf: "PDF", md: "MD", docx: "DOC", txt: "TXT" };

let entries = docsStore.all(); // newest first. Each: { id, name, kind, size, at, status, chunks?, error?, progress?, stage? }
const files = new Map(); // id -> File, kept in memory so a failed upload can be retried
const queue = [];
let active = null; // { id, xhr }
let pendingFiles = [];
let page = 1;
const selected = new Set();

const uid = () => crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const persist = () => docsStore.save(entries.filter((e) => e.status !== "processing"));

// ---- upload ----

function fail(entry, message) {
  entries.unshift({ ...entry, status: "failed", error: message });
  persist();
}

function enqueue(file) {
  const kind = formatKind(file.name);
  const entry = { id: uid(), name: file.name, kind, size: file.size, at: Date.now(), status: "processing", progress: 0, stage: "Waiting" };
  entries = entries.filter((e) => e.name !== file.name); // uploading a file again replaces it, as the server does
  if (!SUPPORTED.includes(kind)) return fail(entry, "Unsupported file type. Use PDF, DOCX, Markdown or TXT.");
  if (file.size > MAX_BYTES) return fail(entry, "This file is larger than 10 MB.");
  files.set(entry.id, file);
  entries.unshift(entry);
  queue.push(entry.id);
}

function addFiles(list) {
  const picked = [...list];
  if (!picked.length) return;
  if (!adminKey.get()) {
    pendingFiles = picked;
    openKeyDialog("Enter the admin key to upload documents.");
    return;
  }
  picked.forEach(enqueue);
  page = 1;
  render();
  pump();
}

function send(entry, file) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    active.xhr = xhr;
    xhr.open("POST", "/api/ingest");
    xhr.setRequestHeader("X-Admin-Key", adminKey.get());
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      entry.progress = Math.round((event.loaded / event.total) * 100);
      entry.stage = "Uploading";
      render();
    };
    xhr.upload.onload = () => {
      entry.progress = null; // the server is now reading and embedding: no percentage to show
      entry.stage = "Reading and embedding";
      render();
    };
    xhr.onload = () => {
      let body = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* a non-JSON error page */
      }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, body });
    };
    xhr.onerror = xhr.ontimeout = () => resolve({ ok: false, status: 0, body: {} });
    xhr.onabort = () => resolve({ aborted: true });
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

async function pump() {
  if (active || !queue.length) return;
  const id = queue.shift();
  const entry = entries.find((e) => e.id === id);
  if (!entry) return pump();
  active = { id: entry.id, xhr: null };
  entry.stage = "Uploading";
  render();

  const result = await send(entry, files.get(entry.id));
  if (result.aborted) {
    entries = entries.filter((e) => e.id !== entry.id);
  } else if (result.ok) {
    Object.assign(entry, { status: "ready", chunks: result.body.chunks, at: Date.now(), progress: 100 });
    $("status").textContent = `${entry.name} was added to the knowledge base.`;
  } else {
    Object.assign(entry, { status: "failed", error: problem(result) });
    $("status").textContent = `${entry.name} could not be added.`;
  }
  active = null;
  persist();
  render();
  pump();
}

// ---- list ----

function visibleEntries() {
  const text = $("search").value.trim().toLowerCase();
  const kind = $("format-filter").value;
  const status = $("status-filter").value;
  return entries.filter((e) => (!text || e.name.toLowerCase().includes(text)) && (kind === "all" || e.kind === kind) && (status === "all" || e.status === status));
}

function statusBadge(entry) {
  const text =
    entry.status === "ready" ? "Indexed / Ready" : entry.status === "failed" ? "Failed" : entry.progress != null && entry.stage === "Uploading" ? `Processing (${entry.progress}%)` : "Processing";
  const badge = el("span", "", { className: `status ${entry.status}` });
  badge.append(el("i"), text);
  return badge;
}

function detailLine(entry) {
  if (entry.status === "ready") return `${plural(entry.chunks ?? 0, "chunk")} indexed`;
  if (entry.status === "failed") return entry.error;
  return entry.stage;
}

function actionButtons(entry) {
  const box = el("div", "", { className: "actions" });
  const remove = (title, glyph, danger = true) => {
    const button = el("button", "", { type: "button", className: `icon-only${danger ? " danger" : ""}`, title });
    button.setAttribute("aria-label", `${title}: ${entry.name}`);
    button.append(icon(glyph, "ms-base"));
    return button;
  };
  if (entry.status === "processing") {
    const cancel = remove("Cancel upload", "close");
    cancel.addEventListener("click", () => cancelEntry(entry.id));
    box.append(cancel);
  } else {
    if (entry.status === "ready") {
      const ask = el("a", "Ask", { className: "mini-btn", href: `chat.html?q=${encodeURIComponent(`Summarize ${entry.name}`)}`, title: "Ask the assistant about this document" });
      box.append(ask);
    } else if (files.has(entry.id)) {
      const retry = el("button", "Retry", { type: "button", className: "mini-btn warn" });
      retry.addEventListener("click", () => {
        const file = files.get(entry.id);
        entries = entries.filter((e) => e.id !== entry.id);
        files.delete(entry.id);
        addFiles([file]);
      });
      box.append(retry);
    }
    const drop = remove("Remove from this list", "delete");
    drop.addEventListener("click", () => removeEntries([entry.id]));
    box.append(drop);
  }
  return box;
}

function row(entry) {
  const failed = entry.status === "failed";
  const tr = el("tr");
  const check = el("input", "", { type: "checkbox", checked: selected.has(entry.id) });
  check.setAttribute("aria-label", `Select ${entry.name}`);
  check.addEventListener("change", () => {
    check.checked ? selected.add(entry.id) : selected.delete(entry.id);
    renderSelection();
  });

  const badge = el("span", KIND_BADGE[entry.kind] ?? entry.kind.toUpperCase().slice(0, 4), { className: `doc-icon ${failed ? "failed" : entry.kind}` });
  const name = el("div", "", { className: `doc-name${failed ? " failed" : ""}` });
  name.append(el("strong", entry.name), el("small", detailLine(entry)));
  const cell = el("div", "", { className: "doc-cell" });
  cell.append(badge, name);

  const cells = [
    el("td"),
    el("td"),
    el("td", KIND_LABEL[entry.kind] ?? entry.kind.toUpperCase(), { className: "mono-cell" }),
    el("td", formatSize(entry.size), { className: "mono-cell" }),
    el("td", friendlyDate(entry.at), { className: "when" }),
    el("td"),
    el("td", "", { className: "right" }),
  ];
  cells[0].append(check);
  cells[1].append(cell);
  cells[5].append(statusBadge(entry));
  cells[6].append(actionButtons(entry));
  tr.append(...cells);
  return tr;
}

function pagerButtons(pages) {
  const make = (label, target, props = {}) => {
    const button = el("button", label, { type: "button", ...props });
    button.addEventListener("click", () => {
      page = target;
      render();
    });
    return button;
  };
  const numbers = [...new Set([1, 2, pages, page - 1, page, page + 1])].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const nodes = [make("Prev", page - 1, { disabled: page === 1 })];
  numbers.forEach((n, i) => {
    if (i && n - numbers[i - 1] > 1) nodes.push(el("span", "…", { className: "gap" }));
    const button = make(String(n), n);
    if (n === page) button.setAttribute("aria-current", "true");
    nodes.push(button);
  });
  nodes.push(make("Next", page + 1, { disabled: page === pages }));
  return nodes;
}

function renderSelection() {
  const rows = [...$("doc-rows").querySelectorAll("input[type=checkbox]")];
  $("select-all").checked = rows.length > 0 && rows.every((c) => c.checked);
  $("remove-selected").setAttribute("aria-disabled", String(selected.size === 0));
}

function renderProgress() {
  const entry = entries.find((e) => e.id === active?.id);
  const text = $("progress-text");
  $("progress-ctrl").hidden = !entry;
  $("progress-dot").className = `status-dot${entry ? " busy" : ""}`;
  if (!entry) {
    text.replaceChildren("No uploads in progress. Added documents are available to the assistant right away.");
    return;
  }
  const waiting = queue.length ? ` · ${plural(queue.length, "more file")} waiting` : "";
  text.replaceChildren(
    el("b", "Currently indexing: "),
    el("span", entry.name, { className: "name" }),
    el("span", `(Stage: ${entry.stage}${entry.progress != null ? ` • ${entry.progress}%` : ""})${waiting}`, { className: "stage" }),
  );
  const bar = $("progress-bar");
  bar.classList.toggle("indeterminate", entry.progress == null);
  bar.firstElementChild.style.width = `${entry.progress ?? 40}%`;
}

function render() {
  const list = visibleEntries();
  const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  page = Math.min(Math.max(page, 1), pages);
  const slice = list.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  $("doc-rows").replaceChildren(...slice.map(row));
  $("empty").hidden = list.length > 0;
  if (!list.length) {
    const filtering = entries.length > 0;
    $("empty-title").textContent = filtering ? "No matching documents" : "No documents yet";
    $("empty-text").textContent = filtering
      ? "Try a different search or clear the filters."
      : "Upload a PDF, Word, Markdown or text file and it will appear here once it is indexed.";
  }

  const from = list.length ? (page - 1) * PAGE_SIZE + 1 : 0;
  const showing = $("showing");
  showing.replaceChildren(...(list.length ? ["Showing ", el("b", `${from} to ${from + slice.length - 1}`), " of ", el("b", String(list.length)), ` ${list.length === 1 ? "document" : "documents"}`] : ["Showing 0 documents"]));
  $("pager").replaceChildren(...(list.length > PAGE_SIZE ? pagerButtons(pages) : []));

  const ready = entries.filter((e) => e.status === "ready").length;
  $("doc-summary").textContent = `${plural(ready, "document")} added from this browser`;
  renderProgress();
  renderSelection();
}

function removeEntries(ids) {
  entries = entries.filter((e) => !ids.includes(e.id) || e.status === "processing");
  ids.forEach((id) => {
    selected.delete(id);
    files.delete(id);
  });
  persist();
  render();
}

function cancelEntry(id) {
  if (active?.id === id) return active.xhr?.abort();
  const at = queue.indexOf(id);
  if (at >= 0) queue.splice(at, 1);
  entries = entries.filter((e) => e.id !== id);
  files.delete(id);
  render();
}

// ---- staff access dialog ----

const dialog = $("key-dialog");
function openKeyDialog(note = "") {
  $("key-input").value = adminKey.get();
  $("key-note").className = "form-note";
  $("key-note").textContent = note || (adminKey.get() ? "A key is saved for this tab." : "");
  dialog.showModal();
  $("key-input").focus();
}
$("key-btn").addEventListener("click", () => openKeyDialog());
$("key-close").addEventListener("click", () => dialog.close());
$("key-forget").addEventListener("click", () => {
  adminKey.clear();
  $("key-input").value = "";
  $("key-note").className = "form-note";
  $("key-note").textContent = "The key was removed from this tab.";
});
$("key-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const value = $("key-input").value.trim();
  if (!value) return;
  adminKey.set(value);
  dialog.close();
  if (pendingFiles.length) {
    const toSend = pendingFiles;
    pendingFiles = [];
    addFiles(toSend);
  }
});
dialog.addEventListener("close", () => (pendingFiles = adminKey.get() ? pendingFiles : []));

// ---- wiring ----

const input = $("file-input");
const chooseFiles = () => input.click();
$("browse-btn").addEventListener("click", chooseFiles);
$("header-upload-btn").addEventListener("click", chooseFiles);
input.addEventListener("change", () => {
  addFiles(input.files);
  input.value = "";
});

const zone = $("dropzone");
["dragenter", "dragover"].forEach((type) =>
  zone.addEventListener(type, (event) => {
    event.preventDefault();
    zone.classList.add("over");
  }),
);
["dragleave", "drop"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("over")));
zone.addEventListener("drop", (event) => {
  event.preventDefault();
  addFiles(event.dataTransfer.files);
});

$("cancel-btn").addEventListener("click", () => active && cancelEntry(active.id));
["search", "format-filter", "status-filter"].forEach((id) =>
  $(id).addEventListener("input", () => {
    page = 1;
    render();
  }),
);
$("select-all").addEventListener("change", (event) => {
  $("doc-rows").querySelectorAll("input[type=checkbox]").forEach((box) => (box.checked = event.target.checked));
  visibleEntries()
    .slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
    .forEach((e) => (event.target.checked ? selected.add(e.id) : selected.delete(e.id)));
  renderSelection();
});
$("remove-selected").addEventListener("click", () => {
  if (isBusy("#remove-selected") || !selected.size) return;
  if (confirm(`Remove ${plural(selected.size, "entry")} from this list? Documents already in the knowledge base are not deleted.`)) removeEntries([...selected]);
});

render();
