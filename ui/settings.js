// Settings: staff key, service status, recent questions and browser-only housekeeping.

const note = (text, tone = "") => {
  $("key-note").textContent = text;
  $("key-note").className = `form-note ${tone}`.trim();
};

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

async function loadAudit() {
  if (!adminKey.get()) {
    $("audit-note").textContent = "Unlock staff access to see the last 20 questions and how each was answered.";
    $("audit-card").hidden = true;
    return null;
  }
  setBusy("#load-audit", true);
  $("audit-note").textContent = "Loading…";
  const reply = await call("/api/audit?limit=20", { headers: adminHeaders() });
  const rows = reply.ok ? reply.body : [];
  $("audit").replaceChildren(...rows.map(auditRow));
  $("audit-card").hidden = rows.length === 0;
  $("audit-note").textContent = reply.ok ? (rows.length ? `Showing the last ${plural(rows.length, "question")}, newest first.` : "No questions have been asked yet.") : problem(reply);
  setBusy("#load-audit", false);
  return reply;
}

function showStaff(reply) {
  const states = { ok: ["ok", "Unlocked"], none: ["", "Locked: no key saved"], off: ["bad", "Switched off on the server"], bad: ["bad", "Key not accepted"], down: ["bad", "Could not reach the server"] };
  const key = !reply ? "none" : reply.ok ? "ok" : reply.status === 403 ? "off" : reply.status === 401 ? "bad" : "down";
  $("staff-dot").className = `status-dot ${states[key][0]}`;
  $("staff-text").textContent = states[key][1];
  return key;
}

async function refresh() {
  showStaff(await loadAudit());
}

$("key-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  adminKey.set($("key").value.trim());
  note("Checking the key…");
  const reply = await loadAudit();
  const state = showStaff(reply);
  note(
    state === "ok" ? "The key works. Staff tools are unlocked for this tab." : reply ? problem(reply) : "",
    state === "ok" ? "good" : "bad",
  );
  if (state !== "ok") adminKey.clear();
  $("key").value = "";
});

$("forget").addEventListener("click", () => {
  adminKey.clear();
  $("key").value = "";
  note("The key was removed from this tab.");
  refresh();
});
$("load-audit").addEventListener("click", () => !isBusy("#load-audit") && refresh());

function counts() {
  $("upload-count").textContent = `${plural(docsStore.all().filter((d) => d.status === "ready").length, "document")} added from this browser`;
  $("chat-count").textContent = `${plural(load("rag.threads", []).length, "saved conversation")}`;
}
$("clear-chats").addEventListener("click", () => {
  if (!confirm("Delete all saved conversations from this browser?")) return;
  localStorage.removeItem("rag.threads");
  counts();
});
$("clear-uploads").addEventListener("click", () => {
  if (!confirm("Clear the list of uploaded documents? Documents already in the knowledge base are not deleted.")) return;
  localStorage.removeItem(DOCS_KEY);
  counts();
});

checkHealth().then((ok) => {
  $("svc-dot").className = `status-dot ${ok ? "ok" : "bad"}`;
  $("svc-text").textContent = ok ? "Online" : "Unreachable";
});
counts();
refresh();
