const $ = (id) => document.getElementById(id);

// What each way of answering is called on the page.
const PATHS = {
  private_kb: "Company knowledge base",
  web_search: "Public web search",
  fallback: "Not confirmed, general guidance only",
  direct: "Chat, no search",
};
const CHAT_TIMEOUT_MS = 120_000; // the first question after a restart can be slow while the models load
const UPLOAD_TIMEOUT_MS = 600_000; // a big PDF can take minutes to read and store
const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// Build elements with textContent (never innerHTML), so answers and web text can't inject HTML.
const el = (tag, text = "", props = {}) => Object.assign(document.createElement(tag), { textContent: text, ...props });

// While a request runs, its buttons stay focusable (keyboard focus is not lost) but ignore clicks.
const setBusy = (selector, busy) => document.querySelectorAll(selector).forEach((b) => b.setAttribute("aria-disabled", String(busy)));
const isBusy = (selector) => document.querySelector(selector).getAttribute("aria-disabled") === "true";

// Talk to the server. It never throws: a failure comes back as { ok: false, status: 0 }.
async function call(url, options = {}, timeout = CHAT_TIMEOUT_MS) {
  try {
    const res = await fetch(url, { ...options, signal: AbortSignal.timeout?.(timeout) });
    return { ok: res.ok, status: res.status, body: await res.json().catch(() => ({})) };
  } catch {
    return { ok: false, status: 0, body: {} };
  }
}

// The server's own message when it sent one (it says what to fix), otherwise a general one with a next step.
function problem(reply) {
  if (typeof reply.body?.detail === "string") return reply.body.detail;
  if (reply.status === 0) return "No reply came back. Check your connection and try again.";
  return "Something went wrong on our side. Please try again in a moment.";
}

// ---- chat ----

function showSources(citations) {
  const items = citations.map((c) => {
    const item = document.createElement("li");
    if (/^https?:\/\//i.test(c.source)) {
      item.append(el("a", c.title || c.source, { href: c.source, target: "_blank", rel: "noopener noreferrer" }));
    } else {
      item.append(...(c.title ? [`${c.title} `, el("span", `(${c.source})`, { className: "muted" })] : [c.source]));
    }
    return item;
  });
  $("citations").replaceChildren(...items);
  $("sources").hidden = items.length === 0;
}

// Show an answer. With no data (thinking, or a problem) only the text shows, and the old path, sources and steps are cleared.
function show(text, data) {
  const trace = data?.trace ?? [];
  $("result").hidden = false;
  $("answer").textContent = text;
  $("source").textContent = PATHS[data?.source_used] ?? "";
  $("source").dataset.path = data?.source_used ?? "";
  $("path").hidden = !$("source").textContent;
  showSources(data?.citations ?? []);
  $("trace").replaceChildren(...trace.map((line) => el("li", line)));
  $("trace-box").hidden = trace.length === 0;
}

async function ask(question) {
  if (isBusy("#ask")) return;
  if (question.length < 2) return show("Please type a question with at least 2 characters.");
  setBusy("#ask, .example", true);
  $("chat").setAttribute("aria-busy", "true");
  $("status").textContent = "Thinking…";
  show("Thinking…");
  const reply = await call("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (reply.ok) {
    show(reply.body.answer, reply.body);
    $("status").textContent = `Answer ready. Answered from: ${PATHS[reply.body.source_used] ?? reply.body.source_used}.`;
  } else {
    show(problem(reply));
    $("status").textContent = "The question could not be answered.";
  }
  $("chat").setAttribute("aria-busy", "false");
  setBusy("#ask, .example", false);
}

$("chat").addEventListener("submit", (event) => {
  event.preventDefault();
  ask($("question").value.trim());
});

document.querySelectorAll(".example").forEach((button) =>
  button.addEventListener("click", () => {
    if (isBusy("#ask")) return;
    $("question").value = button.textContent;
    $("chat").requestSubmit();
  }),
);

// ---- staff tools: upload a document, see the audit log ----

const staffStatus = (text) => ($("staff-status").textContent = text);
const adminHeaders = () => ({ "X-Admin-Key": $("key").value });

$("staff-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isBusy("#staff-form button")) return;
  const body = new FormData();
  body.append("file", $("file").files[0]);
  setBusy("#staff-form button", true);
  staffStatus("Uploading… a large file can take a few minutes.");
  const reply = await call("/api/ingest", { method: "POST", headers: adminHeaders(), body }, UPLOAD_TIMEOUT_MS);
  staffStatus(reply.ok ? `Added ${reply.body.file} (${plural(reply.body.chunks, "chunk")}). Questions can use it right away.` : problem(reply));
  setBusy("#staff-form button", false);
});

function auditRow(entry) {
  const steps = el("ol");
  steps.append(...entry.trace.map((line) => el("li", line)));
  const path = el("details");
  path.append(el("summary", PATHS[entry.source_used] ?? entry.source_used), steps);
  const last = el("td");
  last.append(path);
  const row = el("tr");
  row.append(el("td", when.format(new Date(entry.created_at)), { className: "when" }), el("td", entry.question), last);
  return row;
}

$("load-audit").addEventListener("click", async () => {
  if (isBusy("#staff-form button")) return;
  if (!$("key").value) return staffStatus("Enter the admin key first.");
  setBusy("#staff-form button", true);
  staffStatus("Loading…");
  const reply = await call("/api/audit?limit=20", { headers: adminHeaders() });
  const rows = reply.ok ? reply.body : [];
  $("audit").replaceChildren(...rows.map(auditRow));
  $("audit-box").hidden = rows.length === 0;
  staffStatus(reply.ok ? (rows.length ? `Showing the last ${plural(rows.length, "question")}.` : "No questions have been asked yet.") : problem(reply));
  setBusy("#staff-form button", false);
});
