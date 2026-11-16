const $ = (id) => document.getElementById(id);

// Build list items with textContent (never innerHTML), so answers and web text can't inject HTML.
const items = (lines) => lines.map((text) => Object.assign(document.createElement("li"), { textContent: text }));

// Show a result. With no data it clears the old source, sources and path.
function render(answer, data = { source_used: "", citations: [], trace: [] }) {
  $("result").hidden = false;
  $("answer").textContent = answer;
  $("source").textContent = data.source_used;
  $("citations").replaceChildren(...items(data.citations.map((c) => c.source)));
  $("trace").replaceChildren(...items(data.trace));
}

$("chat").addEventListener("submit", async (event) => {
  event.preventDefault();
  render("Thinking...");
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: $("question").value }),
  }).catch(() => null);
  if (!res?.ok) {
    const detail = res && (await res.json().catch(() => ({}))).detail;
    return render(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
  }
  const data = await res.json();
  render(data.answer, data);
});

$("upload").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = new FormData();
  body.append("file", $("file").files[0]);
  const res = await fetch("/api/ingest", { method: "POST", headers: { "X-Admin-Key": $("key").value }, body }).catch(() => null);
  $("upload-status").textContent = res?.ok ? "Added." : "Failed. Check the admin key and file type.";
});
