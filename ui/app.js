// Chat workspace: sidebar of saved chats, new-chat view and the active thread.
// Chats are saved on the server for the signed-in person (/api/conversations). The server remembers each chat's earlier
// messages by itself, so a follow-up only needs the new question.

const TRACE_KEY = "rag.showTrace";
const JSON_HEADERS = { "Content-Type": "application/json" };
const VERDICTS = {
  private_kb: (n) => ["verified", `Grounded in ${plural(n, "company document")}`],
  web_search: (n) => ["language", `From ${plural(n, "web page")}, not company documents`],
  fallback: () => ["help", "Could not confirm this from the available sources"],
  direct: () => ["chat_bubble", "Chat reply, no search needed"],
};

let threads = []; // this person's chats, newest first: { id, title, updated, messages }. messages stays null until the chat is opened
let currentId = null; // null means the new-chat view
let lastId = null;
let busy = false; // a request that changes things is running
let pending = null; // the chat whose question is being answered
let listError = ""; // why the list of chats could not be loaded

const isMac = /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);
$("shortcut").textContent = isMac ? "⌘K" : "Ctrl K";

const current = () => threads.find((t) => t.id === currentId);
const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
const latency = (ms) => (ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

// What the server sends, in the shapes this page draws.
const toThread = (chat) => ({ id: chat.id, title: chat.title, updated: Date.parse(chat.updated_at), messages: null });
const toMessage = (m) =>
  m.role === "user"
    ? { role: "user", text: m.content, at: Date.parse(m.created_at) }
    : { role: "ai", ms: m.latency_ms, text: m.content, source_used: m.source_used, citations: m.citations ?? [], trace: m.trace ?? [] };

function showNewNote(text) {
  $("new-note").textContent = text;
  $("new-note").hidden = !text;
}

// ---- sidebar ----

function threadButton(thread) {
  const button = el("button", "", { type: "button", className: "thread-item" });
  button.append(el("span", thread.title, { className: "t-title" }), el("span", friendlyDate(thread.updated), { className: "t-meta" }));
  button.setAttribute("aria-current", String(thread.id === currentId));
  button.addEventListener("click", () => openThread(thread.id));
  return button;
}

function listNote() {
  if (!listError) return el("p", "Your chats will appear here.", { className: "history-empty" });
  const box = el("div", "", { className: "history-empty" });
  const retry = el("button", "", { type: "button", className: "link-btn" });
  retry.append(icon("refresh", "ms-xs"), " Try again");
  retry.addEventListener("click", loadThreads);
  box.append(el("p", `Could not load your chats. ${listError}`), retry);
  return box;
}

function renderHistory() {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const week = startOfToday - 6 * 86_400_000;
  const groups = [
    ["Recent Chats", threads.filter((t) => t.updated >= startOfToday)],
    ["Previous 7 Days", threads.filter((t) => t.updated < startOfToday && t.updated >= week)],
    ["Older", threads.filter((t) => t.updated < week)],
  ];
  const nodes = groups.flatMap(([label, items]) => (items.length ? [el("span", label, { className: "history-label" }), ...items.map(threadButton)] : []));
  $("history").replaceChildren(...(nodes.length ? nodes : [listNote()]));
  $("view-thread-btn").disabled = threads.length === 0;
}

async function loadThreads() {
  const reply = await call("/api/conversations?limit=50");
  listError = reply.ok ? "" : problem(reply);
  if (reply.ok) threads = reply.body.map(toThread);
  lastId = threads[0]?.id ?? null;
  renderHistory();
}

// ---- views ----

function setView(view) {
  const inThread = view === "thread";
  $("view-new").hidden = inThread;
  $("view-thread").hidden = !inThread;
  $("view-new-btn").setAttribute("aria-pressed", String(!inThread));
  $("view-thread-btn").setAttribute("aria-pressed", String(inThread));
  if (!inThread) $("question").focus({ preventScroll: true });
}

function showNew() {
  currentId = null;
  setView("new");
  renderHistory();
  closeSidebarOnMobile();
}

// A chat's messages are fetched the first time it is opened.
async function loadMessages(thread) {
  thread.loadError = "";
  const reply = await call(`/api/conversations/${thread.id}/messages`);
  if (reply.status === 404) return gone(thread);
  if (reply.ok) thread.messages = reply.body.map(toMessage);
  else thread.loadError = problem(reply);
}

async function openThread(id) {
  const thread = threads.find((t) => t.id === id);
  if (!thread) return;
  currentId = lastId = id;
  setView("thread");
  renderHistory();
  closeSidebarOnMobile();
  if (!thread.messages) {
    renderThread();
    await loadMessages(thread);
  }
  if (currentId !== id) return; // the person opened something else while this loaded
  renderThread();
  $("follow-up-input").focus({ preventScroll: true });
}

function removeThread(thread) {
  threads = threads.filter((t) => t !== thread);
  if (lastId === thread.id) lastId = threads[0]?.id ?? null;
  if (currentId === thread.id) showNew();
  else renderHistory();
}

// The server says this chat does not exist (deleted on another device, for example).
function gone(thread) {
  removeThread(thread);
  showNewNote("That chat no longer exists. It was probably deleted on another device.");
}

function userBubble(message) {
  const bubble = el("div", "", { className: "bubble-user" });
  const head = el("header");
  head.append(el("b", "You"), el("time", clock(message.at)));
  bubble.append(head, el("p", message.text));
  const row = el("div", "", { className: "msg-user" });
  const avatar = el("span", "", { className: "avatar" });
  avatar.append(el("img", "", { src: "assets/astronaut.png", alt: "" }));
  row.append(bubble, avatar);
  return row;
}

function sourceCard(citation, web) {
  const card = el("div", "", { className: "source-card" });
  const host = web ? new URL(citation.source).hostname.replace(/^www\./, "") : "";
  const top = el("div", "", { className: "top" });
  top.append(el("b", citation.title || host || citation.source), el("em", web ? "WEB" : "KB"));
  const foot = el("div", "", { className: "foot" });
  if (web) {
    foot.append(el("span", "Public web page"), el("a", "Open page ↗", { href: citation.source, target: "_blank", rel: "noopener noreferrer" }));
  } else {
    foot.append(el("span", "Company document"), el("span", "IT knowledge base"));
  }
  card.append(top, el("div", web ? host : citation.source, { className: "name" }), foot);
  return card;
}

function sourcesBlock(message) {
  const citations = (message.citations ?? []).filter((c) => c.source);
  if (!citations.length) return null;
  const web = message.source_used === "web_search";
  const block = el("div", "", { className: "sources" });
  const head = el("div", "", { className: "sources-head" });
  head.append(el("b", web ? "Web Sources" : "Verified Document Sources"), el("span", plural(citations.length, "source")));
  const grid = el("div", "", { className: "source-grid" });
  grid.append(...citations.filter((c) => !web || /^https?:\/\//i.test(c.source)).map((c) => sourceCard(c, web)));
  block.append(head, grid);
  return block;
}

function copyButton(text) {
  const button = el("button", "", { type: "button", className: "link-btn" });
  button.append(icon("content_copy", "ms-xs"), " Copy");
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.lastChild.textContent = " Copied";
      setTimeout(() => (button.lastChild.textContent = " Copy"), 1500);
    } catch {
      button.lastChild.textContent = " Copy unavailable";
    }
  });
  return button;
}

function aiCard(message, isLast) {
  const card = el("div", "", { className: `card-ai${message.error ? " is-error" : ""}` });
  const head = el("div", "", { className: "card-head" });
  const [glyph, label] = message.error ? ["error", "This question could not be answered"] : VERDICTS[message.source_used]?.(message.citations?.length ?? 0) ?? ["verified", "Answered"];
  const verdict = el("div", "", { className: "verdict" });
  verdict.dataset.path = message.source_used ?? "";
  verdict.append(icon(glyph), el("span", label));
  head.append(verdict);
  if (message.ms) head.append(el("span", `Latency: ${latency(message.ms)}`, { className: "latency" }));
  card.append(head, el("p", message.text, { className: "answer" }));
  (message.warnings ?? []).forEach((warning) => card.append(el("p", warning, { className: "card-note" })));

  const sources = sourcesBlock(message);
  if (sources) card.append(sources);

  if (message.trace?.length) {
    const trace = el("details", "", { className: "trace", open: true });
    const steps = el("ol");
    steps.append(...message.trace.map((line) => el("li", line)));
    trace.append(el("summary", "Decision Path"), steps);
    card.append(trace);
  }

  const foot = el("div", "", { className: "card-foot" });
  const actions = el("div");
  if (message.error && isLast && message.question) {
    const retry = el("button", "", { type: "button", className: "link-btn" });
    retry.append(icon("refresh", "ms-xs"), " Try again");
    retry.addEventListener("click", () => retryLast());
    actions.append(retry);
  } else if (!message.error) {
    actions.append(copyButton(message.text));
  }
  foot.append(actions, el("span", message.error ? "" : `Answered from: ${PATHS[message.source_used] ?? message.source_used}`, { className: "path" }));
  card.append(foot);

  const row = el("div", "", { className: "msg-ai" });
  row.append(el("div", "AI", { className: "ai-mark" }), card);
  return row;
}

function thinkingCard() {
  const card = el("div", "", { className: "card-ai", id: "pending" });
  const line = el("div", "", { className: "thinking" });
  const dots = el("span", "", { className: "dots" });
  dots.append(el("i"), el("i"), el("i"));
  line.append(dots, el("span", "Searching company documents…"));
  card.append(line);
  const row = el("div", "", { className: "msg-ai" });
  row.append(el("div", "AI", { className: "ai-mark" }), card);
  return row;
}

// The message shown in place of a chat's messages while they load, or when they could not be loaded.
function loadingCard(thread) {
  if (!thread.loadError) return el("p", "Loading this chat…", { className: "history-empty" });
  const card = el("div", "", { className: "card-ai is-error" });
  const retry = el("button", "", { type: "button", className: "link-btn" });
  retry.append(icon("refresh", "ms-xs"), " Try again");
  retry.addEventListener("click", () => openThread(thread.id));
  card.append(el("p", `This chat could not be loaded. ${thread.loadError}`, { className: "answer" }), retry);
  return card;
}

function renderThread() {
  const thread = current();
  if (!thread) return;
  const questions = thread.messages?.filter((m) => m.role === "user").length ?? 0;
  $("session-tag").textContent = `THREAD #${String(threads.length - threads.indexOf(thread)).padStart(2, "0")}`;
  $("thread-title").textContent = thread.title;
  $("thread-count").textContent = thread.messages ? plural(questions, "question") : "";
  $("follow-up-input").disabled = !thread.messages;
  let nodes;
  if (thread.messages) {
    const last = thread.messages.length - 1;
    nodes = thread.messages.map((m, i) => (m.role === "user" ? userBubble(m) : aiCard(m, i === last)));
    if (pending === thread) nodes.push(thinkingCard());
    if (!nodes.length) nodes.push(el("p", "No questions in this chat yet. Ask the first one below.", { className: "history-empty" }));
  } else {
    nodes = [loadingCard(thread)];
  }
  $("messages").replaceChildren(...nodes);
  const scroller = $("view-thread");
  scroller.scrollTop = scroller.scrollHeight;
}

// ---- asking ----

function setSending(on) {
  busy = on;
  setBusy("#ask, #send, #rename-btn, #delete-btn", on);
  $("status").textContent = on ? "Thinking…" : "";
}

async function ask(question) {
  if (busy || question.length < 2) return;
  let thread = current();
  if (thread && !thread.messages) return; // this chat is still loading
  setSending(true);
  showNewNote("");
  if (!thread) {
    // A new chat has to exist on the server before it can hold a question. Until it does, the question stays in the box.
    const created = await call("/api/conversations", { method: "POST", headers: JSON_HEADERS, body: "{}" });
    if (!created.ok) {
      setSending(false);
      showNewNote(`Could not start a new chat. ${problem(created)}`);
      return;
    }
    thread = { ...toThread(created.body), messages: [] };
    threads.unshift(thread);
    currentId = lastId = thread.id;
  }
  thread.messages.push({ role: "user", text: question, at: Date.now() });
  pending = thread;
  $("question").value = "";
  $("follow-up-input").value = "";
  setView("thread");
  renderThread();
  renderHistory();

  const started = performance.now();
  const reply = await call(`/api/conversations/${thread.id}/messages`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ question }),
  });
  const ms = Math.round(performance.now() - started);
  pending = null;
  setSending(false);
  if (reply.status === 404) return gone(thread);

  if (reply.ok) {
    const { answer, source_used, citations, trace, warnings, title } = reply.body;
    thread.messages.push({ role: "ai", ms, text: answer, source_used, citations: citations ?? [], trace: trace ?? [], warnings: warnings ?? [] });
    thread.title = title ?? thread.title;
    thread.updated = Date.now();
    threads = [thread, ...threads.filter((t) => t !== thread)]; // the chat just used goes to the top
  } else {
    thread.messages.push({ role: "ai", ms, error: true, question, text: problem(reply) });
  }
  $("status").textContent = reply.ok ? `Answer ready. Answered from: ${PATHS[reply.body.source_used] ?? reply.body.source_used}.` : "The question could not be answered.";
  if (currentId === thread.id) renderThread();
  renderHistory();
}

function retryLast() {
  const thread = current();
  if (!thread || busy) return;
  const failed = thread.messages.pop();
  const asked = thread.messages.pop();
  ask(failed?.question ?? asked?.text ?? "");
}

// ---- wiring ----

$("chat").addEventListener("submit", (event) => {
  event.preventDefault();
  ask($("question").value.trim());
});
$("follow-up").addEventListener("submit", (event) => {
  event.preventDefault();
  ask($("follow-up-input").value.trim());
});
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("chat").requestSubmit();
  }
});

document.querySelectorAll(".suggestion").forEach((card) =>
  card.addEventListener("click", () => {
    $("question").value = card.dataset.prompt;
    $("question").focus();
  }),
);

$("new-thread").addEventListener("click", showNew);
$("view-new-btn").addEventListener("click", showNew);
$("view-thread-btn").addEventListener("click", () => openThread(lastId ?? threads[0]?.id));
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    showNew();
  }
});

const mobile = window.matchMedia("(max-width: 767px)");
function setSidebar(open) {
  $("sidebar").classList.toggle("collapsed", !open);
  $("sidebar-toggle").setAttribute("aria-expanded", String(open));
}
function closeSidebarOnMobile() {
  if (mobile.matches) setSidebar(false);
}
$("sidebar-toggle").addEventListener("click", () => setSidebar($("sidebar").classList.contains("collapsed")));
setSidebar(!mobile.matches);

function setTrace(show) {
  document.body.classList.toggle("hide-trace", !show);
  $("trace-toggle").setAttribute("aria-pressed", String(show));
  save(TRACE_KEY, show);
}
$("trace-toggle").addEventListener("click", () => setTrace(document.body.classList.contains("hide-trace")));
setTrace(load(TRACE_KEY, true));

// ---- rename and delete (the buttons in the chat's header) ----

const renameDialog = $("rename-dialog");
const deleteDialog = $("delete-dialog");
const dialogNote = (id, text, tone = "") => {
  $(id).textContent = text;
  $(id).className = `form-note ${tone}`.trim();
};

$("rename-btn").addEventListener("click", () => {
  const thread = current();
  if (!thread || busy) return;
  $("rename-input").value = thread.title;
  dialogNote("rename-note", "");
  renameDialog.showModal();
  $("rename-input").select();
});
$("rename-close").addEventListener("click", () => renameDialog.close());
$("rename-cancel").addEventListener("click", () => renameDialog.close());
$("rename-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const thread = current();
  const title = $("rename-input").value.trim();
  if (!thread || !title || isBusy("#rename-save")) return;
  if (title === thread.title) return renameDialog.close();
  setBusy("#rename-save", true);
  dialogNote("rename-note", "Saving…");
  const reply = await call(`/api/conversations/${thread.id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify({ title }) });
  setBusy("#rename-save", false);
  if (reply.status === 404) {
    renameDialog.close();
    return gone(thread);
  }
  if (!reply.ok) return dialogNote("rename-note", problem(reply), "bad");
  thread.title = reply.body.title;
  renameDialog.close();
  renderThread();
  renderHistory();
});

$("delete-btn").addEventListener("click", () => {
  const thread = current();
  if (!thread || busy) return;
  $("delete-text").textContent = `Delete “${thread.title}”? Its messages are removed for good.`;
  dialogNote("delete-note", "");
  deleteDialog.showModal();
  $("delete-cancel").focus(); // focus the safe choice, so a stray Enter does not delete the chat
});
$("delete-close").addEventListener("click", () => deleteDialog.close());
$("delete-cancel").addEventListener("click", () => deleteDialog.close());
$("delete-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const thread = current();
  if (!thread || isBusy("#delete-confirm")) return;
  setBusy("#delete-confirm", true);
  dialogNote("delete-note", "Deleting…");
  const reply = await call(`/api/conversations/${thread.id}`, { method: "DELETE" });
  setBusy("#delete-confirm", false);
  if (!reply.ok && reply.status !== 404) return dialogNote("delete-note", problem(reply), "bad");
  deleteDialog.close();
  removeThread(thread);
  $("status").textContent = "Chat deleted.";
});

$("sign-out").addEventListener("click", () => Auth.signOut());

// Vault count (documents uploaded from this browser) and service status
const readyDocs = docsStore.all().filter((d) => d.status === "ready").length;
if (readyDocs) {
  $("vault-count").textContent = readyDocs;
  $("vault-count").hidden = false;
  $("vault-docs").textContent = plural(readyDocs, "doc");
}
checkHealth().then((ok) => {
  $("service-dot").className = `status-dot ${ok ? "ok" : "bad"}`;
  $("service-text").textContent = ok ? "Service online" : "Service unreachable";
});

const prefill = new URLSearchParams(location.search).get("q");
if (prefill) $("question").value = prefill.slice(0, 3000);

// ---- start: nothing of the chat shows until we know who is signed in ----

$("gate-reload").addEventListener("click", () => location.reload());

(async function start() {
  const blocked = await Auth.init();
  if (blocked) {
    $("gate-title").textContent = blocked.title;
    $("gate-text").textContent = blocked.text;
    $("gate-actions").hidden = false;
    return;
  }
  const user = await Auth.user();
  if (!user) return Auth.toLogin();
  Auth.watch();
  $("account-email").textContent = user.email;
  document.body.classList.remove("gated");
  $("question").focus({ preventScroll: true });
  await loadThreads();
})();
