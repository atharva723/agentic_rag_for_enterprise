// Chat workspace: sidebar history, new-chat view and the active thread.
// Conversations are kept in this browser only. Each question is sent with the earlier questions and answers of the SAME chat, so a follow-up works.

const THREADS_KEY = "rag.threads";
const TRACE_KEY = "rag.showTrace";
const MAX_THREADS = 30;
const HISTORY_SENT = 6; // earlier exchanges sent with a question. The server reads only the last few (MEMORY_TURNS, 3 by default)
const SHORT_PATHS = { private_kb: "Company KB", web_search: "Web search", fallback: "Not confirmed", direct: "Chat" };
const VERDICTS = {
  private_kb: (n) => ["verified", `Grounded in ${plural(n, "company document")}`],
  web_search: (n) => ["language", `From ${plural(n, "web page")}, not company documents`],
  fallback: () => ["help", "Could not confirm this from the available sources"],
  direct: () => ["chat_bubble", "Chat reply, no search needed"],
};

let threads = load(THREADS_KEY, []);
let currentId = null; // null means the new-chat view
let lastId = threads[0]?.id ?? null;
let busy = false;

const isMac = /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);
$("shortcut").textContent = isMac ? "⌘K" : "Ctrl K";

const current = () => threads.find((t) => t.id === currentId);
const persist = () => save(THREADS_KEY, threads.slice(0, MAX_THREADS));
const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
const latency = (ms) => (ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

function ago(ts) {
  const minutes = Math.max(0, Math.round((Date.now() - ts) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}h`;
  return `${Math.round(minutes / 1440)}d`;
}

// ---- sidebar ----

function threadButton(thread) {
  const reply = [...thread.messages].reverse().find((m) => m.role === "ai" && !m.error);
  const meta = reply
    ? `${SHORT_PATHS[reply.source_used] ?? "Answered"} · ${plural(reply.citations?.length ?? 0, "source")} · ${ago(thread.updated)}`
    : `${plural(thread.messages.filter((m) => m.role === "user").length, "question")} · ${ago(thread.updated)}`;
  const button = el("button", "", { type: "button", className: "thread-item" });
  button.append(el("span", thread.title, { className: "t-title" }), el("span", meta, { className: "t-meta" }));
  button.setAttribute("aria-current", String(thread.id === currentId));
  button.addEventListener("click", () => openThread(thread.id));
  return button;
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
  $("history").replaceChildren(...(nodes.length ? nodes : [el("p", "Your questions will appear here.", { className: "history-empty" })]));
  $("view-thread-btn").disabled = threads.length === 0;
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

function openThread(id) {
  if (!threads.some((t) => t.id === id)) return;
  currentId = lastId = id;
  setView("thread");
  renderThread();
  renderHistory();
  closeSidebarOnMobile();
  $("follow-up-input").focus({ preventScroll: true });
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

function renderThread() {
  const thread = current();
  if (!thread) return;
  const questions = thread.messages.filter((m) => m.role === "user").length;
  $("session-tag").textContent = `THREAD #${String(threads.length - threads.indexOf(thread)).padStart(2, "0")}`;
  $("thread-title").textContent = thread.title;
  $("thread-count").textContent = plural(questions, "question");
  const last = thread.messages.length - 1;
  const nodes = thread.messages.map((m, i) => (m.role === "user" ? userBubble(m) : aiCard(m, i === last)));
  if (busy) nodes.push(thinkingCard());
  $("messages").replaceChildren(...nodes);
  const scroller = $("view-thread");
  scroller.scrollTop = scroller.scrollHeight;
}

// ---- asking ----

// The earlier question-and-answer pairs of THIS chat, oldest first, so a follow-up can be understood.
// Failed replies are skipped, and no other chat is ever included: a new chat starts with nothing.
function historyOf(thread) {
  const pairs = [];
  thread.messages.forEach((message, i) => {
    const asked = thread.messages[i - 1];
    if (message.role === "ai" && !message.error && asked?.role === "user") pairs.push({ question: asked.text, answer: message.text });
  });
  return pairs.slice(-HISTORY_SENT);
}

function setSending(on) {
  busy = on;
  setBusy("#ask, #send", on);
  $("status").textContent = on ? "Thinking…" : "";
}

async function ask(question) {
  if (busy) return;
  if (question.length < 2) return;
  let thread = current();
  if (!thread) {
    thread = { id: crypto.randomUUID?.() ?? String(Date.now()), title: question.length > 52 ? `${question.slice(0, 50)}…` : question, updated: Date.now(), messages: [] };
    threads.unshift(thread);
    currentId = lastId = thread.id;
  }
  const history = historyOf(thread); // taken before the new question is added
  thread.messages.push({ role: "user", text: question, at: Date.now() });
  thread.updated = Date.now();
  $("question").value = "";
  $("follow-up-input").value = "";
  setSending(true);
  setView("thread");
  renderThread();
  renderHistory();

  const started = performance.now();
  const reply = await call("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  const ms = Math.round(performance.now() - started);

  thread.messages.push(
    reply.ok
      ? { role: "ai", ms, text: reply.body.answer, source_used: reply.body.source_used, citations: reply.body.citations ?? [], trace: reply.body.trace ?? [] }
      : { role: "ai", ms, error: true, question, text: problem(reply) },
  );
  thread.updated = Date.now();
  persist();
  setSending(false);
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

renderHistory();
const prefill = new URLSearchParams(location.search).get("q");
if (prefill) $("question").value = prefill.slice(0, 3000);
$("question").focus({ preventScroll: true });
