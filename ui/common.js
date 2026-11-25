// Helpers shared by the chat, vault, settings and login pages.
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

// On a page with sign-in (auth.js), our own /api/ calls carry the person's token, and a 401 sends them back to sign in.
async function authedFetch(url, options, timeout) {
  const withAuth = typeof Auth !== "undefined" && url.startsWith("/api/");
  const headers = new Headers(options.headers);
  const token = withAuth ? await Auth.token() : "";
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url, { ...options, headers, signal: AbortSignal.timeout?.(timeout) });
  if (withAuth && res.status === 401) Auth.expired();
  return res;
}

// Talk to the server. It never throws: a failure comes back as { ok: false, status: 0 }.
async function call(url, options = {}, timeout = CHAT_TIMEOUT_MS) {
  try {
    const res = await authedFetch(url, options, timeout);
    return { ok: res.ok, status: res.status, body: await res.json().catch(() => ({})) };
  } catch {
    return { ok: false, status: 0, body: {} };
  }
}

// The same, for a reply that arrives as server-sent events. Each "step" event goes to onStep the moment it arrives. The closing
// "answer" or "error" event becomes the result, shaped like call()'s. An error before the stream starts (401, 404, 429) is a normal reply.
async function stream(url, options, onStep, timeout = CHAT_TIMEOUT_MS) {
  let result = { ok: false, status: 0, body: {} }; // what a connection that breaks before the end looks like
  try {
    const res = await authedFetch(url, options, timeout);
    if (!res.ok) return { ok: false, status: res.status, body: await res.json().catch(() => ({})) };
    for await (const { name, data } of readEvents(res.body)) {
      if (name === "step") {
        try {
          onStep(data);
        } catch (error) {
          console.error(error); // a drawing problem must not cost the answer
        }
      } else if (name === "answer") result = { ok: true, status: 200, body: data };
      else if (name === "error") result = { ok: false, status: data.status ?? 500, body: { detail: data.detail } };
    }
  } catch {
    /* the connection broke or ran out of time: whatever arrived before is the result */
  }
  return result;
}

// Server-sent events are text: an event is a few "field: value" lines ended by a blank line, and a line that starts with ":" is only a
// keep-alive. A chunk can end anywhere, even inside a character, so text waits in a buffer until a blank line completes an event.
async function* readEvents(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  try {
    for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
      text = (text + decoder.decode(chunk.value, { stream: true })).replace(/\r\n/g, "\n");
      for (let end = text.indexOf("\n\n"); end !== -1; end = text.indexOf("\n\n")) {
        const event = parseEvent(text.slice(0, end));
        text = text.slice(end + 2);
        if (event) yield event;
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

function parseEvent(block) {
  let name = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  try {
    return data.length ? { name, data: JSON.parse(data.join("\n")) } : null;
  } catch {
    return null;
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
