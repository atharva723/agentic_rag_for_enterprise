// Decision Path Viewer: steps through three example questions that follow the agent's real paths.

const FLOWS = [
  {
    status: "AGENT_STATUS: GRADING",
    question: "How do I connect to the company VPN from home?",
    steps: [
      "✓ Router: IT question, search company documents",
      "✓ Knowledge base: relevant sections found",
      "✓ Grader: the evidence is good",
    ],
    title: "Answered from: company knowledge base",
    text: "The reply cites the VPN guide, and lists it as a source.",
    foot: "Company documents first",
  },
  {
    status: "AGENT_STATUS: WEB SEARCH",
    question: "What is the latest Microsoft Teams outage guidance?",
    steps: [
      "✓ Router: public topic, the web is allowed",
      "✗ Knowledge base: nothing relevant",
      "✓ Web search: pages found and graded",
    ],
    title: "Answered from: public web search",
    text: "The reply starts with a notice that it is not from company documents.",
    foot: "Public topics only",
  },
  {
    status: "AGENT_STATUS: FALLBACK",
    question: "What is the admin password for the office router?",
    steps: [
      "✓ Router: company-only, the web is blocked",
      "✗ Knowledge base: evidence is weak",
      "✓ Rewrite once, search again: still weak",
    ],
    title: "Not confirmed",
    text: "The reply says what could not be confirmed. Passwords are never written out.",
    foot: "No guessing, no credentials",
  },
];

let index = 0;
const $ = (id) => document.getElementById(id);

// ---- hero preview: a question is typed, the steps tick by, and a cited answer appears ----

const EXAMPLES = [
  {
    q: "How do I connect to the company VPN from home?",
    steps: ["✓ Router: IT question, search company documents", "✓ Knowledge base: relevant sections found", "✓ Grader: the evidence is good"],
    a: "Open the pre-installed NovaConnect VPN client on your company laptop, sign in, and approve the MFA request.",
    src: "📄 NovaConnect VPN Remote Access for Windows 11",
  },
  {
    q: "What is the latest Microsoft Teams outage guidance?",
    steps: ["✓ Router: public topic, the web is allowed", "✗ Knowledge base: nothing relevant", "✓ Web search: pages found and graded"],
    a: "No company document answers this. Here is what public pages say, with links to each one.",
    src: "🌐 Public web pages",
  },
  {
    q: "What is the admin password for the office router?",
    steps: ["✓ Router: company-only, the web is blocked", "✗ Knowledge base: evidence is weak", "✓ Rewrote once, searched again: still weak"],
    a: "I could not confirm this from the company documents, so treat this as general guidance only. Please contact the IT Service Desk.",
    src: "",
  },
];
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let heroRun = 0;
let heroIndex = 0;

function paintHero(example, full) {
  $("hp-q").textContent = example.q;
  $("hp-steps").replaceChildren(...example.steps.map((s) => stepLine(s)));
  $("hp-a").textContent = example.a;
  $("hp-src").textContent = example.src;
  if (full) document.querySelector(".win .you").classList.add("done");
}

function stepLine(text) {
  const li = document.createElement("li");
  li.textContent = text;
  if (text.startsWith("✗")) li.className = "bad";
  return li;
}

async function playHero(i) {
  const run = ++heroRun;
  heroIndex = i;
  const example = EXAMPLES[i];
  document.querySelectorAll("#hp-dots button").forEach((b, n) => b.setAttribute("aria-current", String(n === i)));
  if (reduceMotion) return paintHero(example, true);

  const row = document.querySelector(".win .you");
  row.classList.remove("done");
  $("hp-q").textContent = "";
  $("hp-steps").replaceChildren();
  $("hp-a").textContent = "";
  $("hp-src").textContent = "";
  for (let n = 1; n <= example.q.length; n++) {
    if (run !== heroRun) return;
    $("hp-q").textContent = example.q.slice(0, n);
    await wait(28);
  }
  row.classList.add("done");
  for (const line of example.steps) {
    await wait(450);
    if (run !== heroRun) return;
    $("hp-steps").append(stepLine(line));
  }
  await wait(450);
  if (run !== heroRun) return;
  $("hp-a").textContent = example.a;
  $("hp-src").textContent = example.src;
  await wait(4200);
  if (run === heroRun) playHero((i + 1) % EXAMPLES.length);
}

EXAMPLES.forEach((example, n) => {
  const dot = document.createElement("button");
  dot.type = "button";
  dot.setAttribute("aria-label", `Show example ${n + 1} of ${EXAMPLES.length}`);
  dot.addEventListener("click", () => playHero(n));
  $("hp-dots").append(dot);
});
playHero(0);

function show() {
  const flow = FLOWS[index];
  $("lcd-status").textContent = flow.status;
  $("lcd-question").textContent = `"${flow.question}"`;
  $("lcd-steps").replaceChildren(
    ...flow.steps.map((line, i) => {
      const p = document.createElement("p");
      p.textContent = line;
      p.style.animationDelay = `${i * 0.2}s`;
      return p;
    }),
  );
  $("lcd-result-title").textContent = flow.title;
  $("lcd-result-text").textContent = flow.text;
  $("lcd-foot").textContent = flow.foot;
}

const step = (by) => {
  index = (index + by + FLOWS.length) % FLOWS.length;
  show();
};
$("prev-flow").addEventListener("click", () => step(-1));
$("next-flow").addEventListener("click", () => step(1));
show();
