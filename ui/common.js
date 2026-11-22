// Helpers shared by the chat, vault and settings pages.
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
const icon = (name, size = "") => {
  const glyph = el("span", name, { className: `ms ${size}`.trim() });
  glyph.setAttribute("aria-hidden", "true");
  return glyph;
};

// While a request runs, its buttons stay focusable (keyboard focus is not lost) but ignore clicks.
const setBusy = (selector, busy) => document.querySelectorAll(selector).forEach((b) => b.setAttribute("aria-disabled", String(busy)));
const isBusy = (selector) => document.querySelector(selector)?.getAttribute("aria-disabled") === "true";

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

// ---- storage (this browser only) ----

function load(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}
const save = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: the page still works, it just won't remember */
  }
};

// The admin key lives only in this tab's session storage and is sent only to our own server.
const adminKey = {
  get: () => sessionStorage.getItem("rag.adminKey") || "",
  set: (value) => sessionStorage.setItem("rag.adminKey", value),
  clear: () => sessionStorage.removeItem("rag.adminKey"),
};
const adminHeaders = () => ({ "X-Admin-Key": adminKey.get() });

// Documents uploaded from this browser (the vault list and the count badge in the chat header).
const DOCS_KEY = "rag.docs";
const docsStore = { all: () => load(DOCS_KEY, []), save: (docs) => save(DOCS_KEY, docs) };

const formatSize = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);
const formatKind = (name) => ((name.split(".").pop() || "").toLowerCase());

// "Today, 14:22" / "Yesterday, 09:15" / "Oct 24, 18:30"
function friendlyDate(ts) {
  const d = new Date(ts);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(ts).setHours(0, 0, 0, 0)) / 86_400_000);
  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  return `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${time}`;
}

// A server health dot used by the chat sidebar and the settings page.
async function checkHealth() {
  const reply = await call("/api/health", {}, 8000);
  return reply.ok && reply.body.status === "ok";
}
