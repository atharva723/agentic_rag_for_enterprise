// "How a question travels": an animated map of the agent's real graph (app/agent/graph.py).
// A packet follows the real routes. Nodes light up as it arrives, and a caption explains each step.
// No libraries. Only transform and opacity are animated, and everything pauses when it is off screen.
(() => {
  const svg = document.getElementById("fl-svg");
  if (!svg) return;

  const NS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const make = (tag, attrs = {}, parent) => {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (parent) parent.append(node);
    return node;
  };
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  // Strong ease-in-out: the packet accelerates hard, then settles into the node.
  const ease = (p) => (p < 0.5 ? 16 * p ** 5 : 1 - (-2 * p + 2) ** 5 / 2);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- the map: node positions and routes, in a 1040 x 390 space ----

  const H = 48;
  const NODES = {
    q: { x: 54, y: 200, w: 84, label: "QUESTION", kind: "io" },
    router: { x: 200, y: 200, label: "ROUTER", fn: "route_question", kind: "decide" },
    kb: { x: 380, y: 200, label: "COMPANY KB", fn: "retrieve_kb" },
    grader: { x: 560, y: 200, label: "GRADER", fn: "grade_evidence", kind: "decide" },
    answer: { x: 770, y: 200, label: "ANSWER", fn: "generate_answer" },
    reply: { x: 976, y: 200, w: 84, label: "REPLY", kind: "io" },
    chat: { x: 380, y: 70, w: 128, label: "CHAT", fn: "answer_direct" },
    rewrite: { x: 380, y: 330, label: "REWRITE", fn: "rewrite_query" },
    web: { x: 560, y: 330, label: "WEB SEARCH", fn: "search_web" },
    fallback: { x: 770, y: 330, label: "FALLBACK", fn: "fallback_answer", kind: "fail" },
  };

  const EDGES = [
    { from: "q", to: "router", d: "M96 200H140", carry: "question" },
    { from: "router", to: "kb", d: "M260 200H320", carry: "clean query", label: { x: 290, y: 190, t: "IT topic" } },
    { from: "kb", to: "grader", d: "M440 200H500", carry: "top sections" },
    { from: "grader", to: "answer", d: "M620 200H710", carry: "evidence", label: { x: 665, y: 190, t: "good" } },
    { from: "answer", to: "reply", d: "M830 200H934", carry: "answer + sources" },
    { from: "router", to: "chat", d: "M200 176V70H316", carry: "message", label: { x: 210, y: 128, t: "small talk", anchor: "start" } },
    { from: "chat", to: "reply", d: "M444 70H976V176", carry: "chat reply", label: { x: 700, y: 60, t: "no search needed" } },
    { from: "grader", to: "web", d: "M560 224V306", bidi: true, carry: "clean query", carryBack: "web pages", label: { x: 572, y: 294, t: "weak, public topic", anchor: "start" } },
    { from: "grader", to: "rewrite", d: "M530 224V268H400V306", carry: "weak evidence", label: { x: 465, y: 260, t: "weak, retry" } },
    { from: "rewrite", to: "kb", d: "M360 306V224", carry: "new query", label: { x: 352, y: 272, t: "new query", anchor: "end" } },
    { from: "grader", to: "fallback", d: "M590 224V262H790V306", carry: "weak evidence", label: { x: 690, y: 254, t: "still weak" } },
    { from: "fallback", to: "reply", d: "M830 330H976V224", carry: "honest notice" },
  ];

  // ---- the four routes, written from what graph.py really does ----

  const Q = { n: "q", title: "A question arrives", text: "Typed in the chat and sent to the server, with the last few messages of that chat so a follow-up makes sense.", fn: "POST /api/chat" };
  const REPLY = (text) => ({ n: "reply", title: "Reply sent", text, fn: "write_audit" });
  const FAST = "fast model";
  const BIG = "answer model";

  const SCENARIOS = [
    {
      tab: "Company answer",
      tone: "good",
      question: "How do I connect to the company VPN from home?",
      steps: [
        Q,
        { n: "router", title: "Router: what kind of message is this?", text: "Decides IT question or small talk, and cleans the message into a short search query. Names, emails and secrets are dropped.", fn: "route_question", model: FAST },
        { n: "kb", title: "Search the company documents", text: "Finds the best matching sections of the IT guides by meaning, up to four at a time.", fn: "retrieve_kb", model: "no LLM" },
        { n: "grader", title: "Grader: is this evidence good enough?", text: "Reads those sections and answers one word: good or weak. Good evidence goes straight to the answer.", fn: "grade_evidence", model: FAST, verdict: "good" },
        { n: "answer", title: "Write the answer", text: "The answer model replies using only that evidence, and lists the documents it used.", fn: "generate_answer", model: BIG },
        REPLY("The chat shows the answer, its sources and this decision path. Staff can review the path in the audit log. Answered from: company knowledge base."),
      ],
    },
    {
      tab: "Web fallback",
      tone: "web",
      question: "What is the latest Microsoft Teams outage guidance?",
      steps: [
        Q,
        { n: "router", title: "Router: what kind of message is this?", text: "Marked as a public topic, so web pages could answer it. Company-only topics never get this flag.", fn: "route_question", model: FAST },
        { n: "kb", title: "Search the company documents", text: "The IT guides are always searched first. The matches are poor for this topic.", fn: "retrieve_kb", model: "no LLM" },
        { n: "grader", title: "Grader: is this evidence good enough?", text: "Weak. Because the topic is public, the agent is now allowed to try the web.", fn: "grade_evidence", model: FAST, verdict: "weak" },
        { n: "web", title: "Search the web", text: "Only the cleaned search query leaves the network. Names and secrets stay behind.", fn: "search_web", model: "no LLM" },
        { n: "grader", title: "Grader: judge the web pages", text: "Web pages are noisier, so the bigger model grades them. This time the evidence is good.", fn: "grade_evidence", model: BIG, verdict: "good" },
        { n: "answer", title: "Write the answer", text: "The reply starts with a notice that no company document answers this, then summarises the pages with links.", fn: "generate_answer", model: BIG },
        REPLY("Shown with the notice, the web links and this decision path. Answered from: public web search."),
      ],
    },
    {
      tab: "Not confirmed",
      tone: "bad",
      question: "What is the admin password for the office router?",
      steps: [
        Q,
        { n: "router", title: "Router: what kind of message is this?", text: "Marked company-only (passwords, tickets, people, equipment). The web is blocked for this question.", fn: "route_question", model: FAST },
        { n: "kb", title: "Search the company documents", text: "Looks through the IT guides. Nothing solid matches.", fn: "retrieve_kb", model: "no LLM" },
        { n: "grader", title: "Grader: is this evidence good enough?", text: "Weak. The web is blocked, but one retry is still allowed.", fn: "grade_evidence", model: FAST, verdict: "weak" },
        { n: "rewrite", title: "Rewrite the question", text: "Writes a better search query and counts the retry. Only one rewrite is ever allowed.", fn: "rewrite_query", model: FAST },
        { n: "kb", title: "Search again", text: "Runs the new query against the same company documents.", fn: "retrieve_kb", model: "no LLM" },
        { n: "grader", title: "Grader: is this evidence good enough?", text: "Still weak, and no retries are left. Time to be honest instead of guessing.", fn: "grade_evidence", model: FAST, verdict: "weak" },
        { n: "fallback", title: "Say what could not be confirmed", text: "Starts with \u201cI could not confirm this\u201d, gives general guidance and suggests the IT Service Desk. Never states company facts.", fn: "fallback_answer", model: BIG },
        REPLY("Shown with the honest notice and no invented sources. Answered from: not confirmed, general guidance only."),
      ],
    },
    {
      tab: "Just chat",
      tone: "chat",
      question: "Hello!",
      steps: [
        Q,
        { n: "router", title: "Router: what kind of message is this?", text: "Spots small talk, not an IT question, so it skips searching completely.", fn: "route_question", model: FAST },
        { n: "chat", title: "Reply directly", text: "A short friendly answer from the fast model. No documents, no web, no sources.", fn: "answer_direct", model: FAST },
        REPLY("A quick reply with no sources, because nothing was searched. Answered from: chat, no search."),
      ],
    },
  ];

  // ---- draw the map ----

  const defs = make("defs", {}, svg);
  for (const [name, color] of [["idle", "#5b6b9c"], ["lit", "#fde047"]]) {
    const marker = make(
      "marker",
      { id: `fl-arrow-${name}`, viewBox: "0 0 10 10", refX: "10", refY: "5", markerWidth: "11", markerHeight: "11", markerUnits: "userSpaceOnUse", orient: "auto-start-reverse" },
      defs,
    );
    make("path", { d: "M0 0 10 5 0 10z", fill: color }, marker);
  }
  const gEdges = make("g", {}, svg);
  const gLabels = make("g", {}, svg);
  const gNodes = make("g", {}, svg);
  const gBadge = make("g", {}, svg);
  const gBurst = make("g", {}, svg);
  const gPacket = make("g", { class: "gone" }, svg);

  const edges = EDGES.map((edge) => {
    const base = make("path", { d: edge.d, class: "fl-edge", "marker-end": "url(#fl-arrow-idle)" }, gEdges);
    if (edge.bidi) base.setAttribute("marker-start", "url(#fl-arrow-idle)");
    const trace = make("path", { d: edge.d, class: "fl-trace" }, gEdges);
    const len = base.getTotalLength();
    trace.style.strokeDasharray = `${len} ${len}`;
    trace.style.strokeDashoffset = String(len);
    let label = null;
    if (edge.label) {
      label = make("text", { x: edge.label.x, y: edge.label.y, class: "fl-label", "text-anchor": edge.label.anchor || "middle" }, gLabels);
      label.textContent = edge.label.t;
    }
    return { ...edge, base, trace, len, label, lit: false };
  });

  const nodes = {};
  for (const [id, n] of Object.entries(NODES)) {
    const w = n.w ?? 120;
    const g = make("g", { class: `fl-node k-${n.kind ?? "step"}`, transform: `translate(${n.x - w / 2} ${n.y - H / 2})` }, gNodes);
    make("rect", { class: "fl-shadow", x: 4, y: 4, width: w, height: H, rx: 3 }, g);
    const wrap = make("g", { class: "fl-wrap" }, g);
    make("rect", { class: "fl-body", width: w, height: H, rx: 3 }, wrap);
    make("text", { class: "fl-title", x: w / 2, y: n.fn ? 24 : 31, "text-anchor": "middle" }, wrap).textContent = n.label;
    if (n.fn) make("text", { class: "fl-fn", x: w / 2, y: 39, "text-anchor": "middle" }, wrap).textContent = n.fn;
    const ping = make("rect", { class: "fl-ping", width: w, height: H, rx: 3 }, g);
    nodes[id] = { g, wrap, ping, cx: n.x, cy: n.y };
  }

  const badge = make("g", { transform: `translate(${NODES.grader.x} ${NODES.grader.y - H / 2 - 16})` }, gBadge);
  const badgeIn = make("g", { class: "fl-badge" }, badge);
  make("rect", { x: -38, y: -10, width: 76, height: 20, rx: 3 }, badgeIn);
  const badgeText = make("text", { class: "fl-badge-text", y: 4.5, "text-anchor": "middle" }, badgeIn);

  const TRAIL_LAG = [36, 72, 108, 144, 180]; // how far (ms) each trail square lags behind the head
  const trail = TRAIL_LAG.map((_, i) => {
    const size = 9 - i;
    return make("rect", { class: "fl-trail", x: -size / 2, y: -size / 2, width: size, height: size, opacity: 0.6 - i * 0.1 }, gPacket);
  });
  const head = make("g", { class: "fl-head" }, gPacket);
  const headIn = make("g", { class: "fl-head-in" }, head);
  make("rect", { class: "fl-head-sq", x: -7, y: -7, width: 14, height: 14, transform: "rotate(45)" }, headIn);
  const carry = make("text", { class: "fl-carry", y: -33, "text-anchor": "middle" }, head);

  // ---- helpers ----

  const restart = (el, cls) => {
    el.classList.remove(cls);
    void el.getBoundingClientRect(); // force a reflow so the animation can run again
    el.classList.add(cls);
  };
  const pointOn = (edge, dir, p) => edge.base.getPointAtLength((dir > 0 ? p : 1 - p) * edge.len);
  const findEdge = (from, to) => {
    for (const edge of edges) {
      if (edge.from === from && edge.to === to) return { edge, dir: 1 };
      if (edge.bidi && edge.from === to && edge.to === from) return { edge, dir: -1 };
    }
    throw new Error(`No route from ${from} to ${to}`);
  };

  const cap = { box: $("fl-cap"), step: $("fl-step"), pips: $("fl-pips"), title: $("fl-title"), text: $("fl-text"), fn: $("fl-fn"), model: $("fl-model") };
  const scroller = $("fl-scroll");
  let userScrollUntil = 0;
  for (const type of ["pointerdown", "wheel", "touchstart"]) scroller.addEventListener(type, () => (userScrollUntil = Date.now() + 4000), { passive: true });

  // On a narrow screen the map scrolls sideways. Glide it so the packet stays in view.
  function follow(x) {
    if (scroller.scrollWidth <= scroller.clientWidth + 4 || Date.now() < userScrollUntil) return;
    const scale = svg.getBoundingClientRect().width / 1040;
    const target = clamp(x * scale - scroller.clientWidth / 2, 0, scroller.scrollWidth - scroller.clientWidth);
    scroller.scrollLeft += (target - scroller.scrollLeft) * 0.12;
  }

  // ---- the player ----

  let scenarioIndex = 0;
  let scenario = SCENARIOS[0];
  let segs = [];
  let segIndex = 0;
  let seg = null;
  let elapsed = 0;
  let playing = true; // the visitor's play / pause choice
  let onScreen = false;
  let cycle = true; // keep moving on to the next route until the visitor picks one
  let raf = 0;
  let last = 0;

  const buildSegments = (s) => {
    const out = [];
    s.steps.forEach((step, i) => {
      if (i > 0) {
        const { edge, dir } = findEdge(s.steps[i - 1].n, step.n);
        out.push({ type: "leg", edge, dir, dur: clamp(edge.len / 0.36, 520, 1300) });
      }
      out.push({ type: "dwell", step: i, node: step.n, dur: 700 + step.text.length * 7 });
    });
    out.push({ type: "hold", dur: 2400 });
    return out;
  };

  function reset() {
    for (const n of Object.values(nodes)) n.g.classList.remove("active", "done");
    for (const edge of edges) {
      edge.lit = false;
      edge.trace.style.strokeDashoffset = String(edge.len);
      edge.base.setAttribute("marker-end", "url(#fl-arrow-idle)");
      if (edge.bidi) edge.base.setAttribute("marker-start", "url(#fl-arrow-idle)");
      edge.label?.classList.remove("on");
    }
    badgeIn.classList.remove("show");
    badgeText.textContent = "";
    gPacket.classList.add("gone");
    scroller.scrollLeft = 0;
  }

  function showStep(i) {
    const step = scenario.steps[i];
    cap.step.textContent = `STEP ${i + 1} / ${scenario.steps.length}`;
    [...cap.pips.children].forEach((pip, n) => pip.classList.toggle("on", n <= i));
    cap.title.textContent = step.title;
    cap.text.textContent = step.text;
    cap.fn.textContent = !step.fn ? "" : /[ /]/.test(step.fn) ? step.fn : `${step.fn}()`;
    cap.model.textContent = step.model ?? "";
    cap.model.dataset.model = step.model ?? "";
    restart(cap.box, "swap");
  }

  function burst(color) {
    const { cx, cy } = nodes.reply;
    for (let i = 0; i < 8; i++) {
      const angle = (Math.PI * 2 * i) / 8;
      const dot = make("rect", { class: "fl-burst", x: cx - 3, y: cy - 3, width: 6, height: 6, fill: color }, gBurst);
      dot.style.setProperty("--dx", `${Math.cos(angle) * 46}px`);
      dot.style.setProperty("--dy", `${Math.sin(angle) * 36}px`);
      dot.addEventListener("animationend", () => dot.remove(), { once: true });
    }
  }

  function begin(s) {
    if (s.type === "leg") {
      gPacket.classList.remove("gone");
      carry.textContent = s.dir < 0 && s.edge.carryBack ? s.edge.carryBack : s.edge.carry;
      const start = pointOn(s.edge, s.dir, 0);
      for (const el of [head, ...trail]) el.setAttribute("transform", `translate(${start.x} ${start.y})`);
      s.edge.label?.classList.add("on");
    } else if (s.type === "dwell") {
      const step = scenario.steps[s.step];
      const node = nodes[step.n];
      gPacket.classList.add("gone");
      node.g.classList.add("active");
      restart(node.ping, "go");
      showStep(s.step);
      if (step.verdict) {
        badgeText.textContent = step.verdict === "good" ? "GOOD \u2713" : "WEAK \u2717";
        badgeIn.classList.remove("good", "bad");
        badgeIn.classList.add(step.verdict === "good" ? "good" : "bad");
        restart(badgeIn, "show");
        if (step.verdict === "weak") restart(node.wrap, "shake");
      }
      if (step.n === "reply") burst(scenario.tone === "bad" ? "#fca5a5" : "#fde047");
    }
  }

  function finish(s) {
    if (s.type === "leg") {
      s.edge.lit = true;
      s.edge.trace.style.strokeDashoffset = "0";
      s.edge.base.setAttribute("marker-end", "url(#fl-arrow-lit)");
      if (s.edge.bidi) s.edge.base.setAttribute("marker-start", "url(#fl-arrow-lit)");
    } else if (s.type === "dwell") {
      const g = nodes[s.node].g;
      g.classList.remove("active");
      g.classList.add("done");
    }
  }

  function tick(s, p) {
    if (s.type === "dwell") return follow(nodes[s.node].cx);
    if (s.type !== "leg") return;
    const q = ease(p);
    const pt = pointOn(s.edge, s.dir, q);
    head.setAttribute("transform", `translate(${pt.x} ${pt.y})`);
    trail.forEach((square, i) => {
      const lagged = pointOn(s.edge, s.dir, ease(clamp((elapsed - TRAIL_LAG[i]) / s.dur, 0, 1)));
      square.setAttribute("transform", `translate(${lagged.x} ${lagged.y})`);
    });
    if (!s.edge.lit) s.edge.trace.style.strokeDashoffset = String(s.dir > 0 ? s.edge.len * (1 - q) : -s.edge.len * (1 - q));
    follow(pt.x);
  }

  function advance() {
    while (seg && elapsed >= seg.dur) {
      const overflow = elapsed - seg.dur;
      finish(seg);
      segIndex += 1;
      if (segIndex >= segs.length) return loadScenario(cycle ? (scenarioIndex + 1) % SCENARIOS.length : scenarioIndex);
      seg = segs[segIndex];
      elapsed = overflow;
      begin(seg);
    }
    if (seg) tick(seg, clamp(elapsed / seg.dur, 0, 1));
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    elapsed += Math.min(now - last, 50); // a long gap (a busy tab) must not make the packet jump
    last = now;
    advance();
  }

  function sync() {
    const run = playing && onScreen && !document.hidden && !reduced;
    if (run && !raf) {
      last = performance.now();
      raf = requestAnimationFrame(frame);
    } else if (!run && raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  }

  // Reduced motion: no movement at all. Show the whole route lit, with every step written out.
  function renderStatic() {
    scenario.steps.forEach((step) => nodes[step.n].g.classList.add("done"));
    for (let i = 1; i < scenario.steps.length; i++) {
      const { edge } = findEdge(scenario.steps[i - 1].n, scenario.steps[i].n);
      edge.lit = true;
      edge.trace.style.strokeDashoffset = "0";
      edge.base.setAttribute("marker-end", "url(#fl-arrow-lit)");
      if (edge.bidi) edge.base.setAttribute("marker-start", "url(#fl-arrow-lit)");
    }
    cap.step.textContent = "THE WHOLE ROUTE";
    cap.pips.replaceChildren();
    cap.title.textContent = scenario.tab;
    cap.text.textContent = scenario.steps.map((step, i) => `${i + 1}. ${step.title}. ${step.text}`).join(" ");
    cap.fn.textContent = "";
    cap.model.textContent = "";
  }

  function loadScenario(i) {
    scenarioIndex = i;
    scenario = SCENARIOS[i];
    tabs.forEach((tab, n) => tab.setAttribute("aria-pressed", String(n === i)));
    $("fl-q").textContent = scenario.question;
    const names = scenario.steps.map((s) => NODES[s.n].label.toLowerCase() + (s.verdict ? ` (${s.verdict})` : ""));
    $("fl-sr").textContent = `Route: ${scenario.tab}. Path: ${names.join(", then ")}.`;
    reset();
    if (reduced) return renderStatic();
    cap.pips.replaceChildren(...scenario.steps.map(() => document.createElement("i")));
    segs = buildSegments(scenario);
    segIndex = 0;
    elapsed = 0;
    seg = segs[0];
    begin(seg);
    sync();
  }

  // ---- controls ----

  const playBtn = $("fl-play");
  const updatePlay = () => (playBtn.textContent = playing ? "\u275A\u275A Pause" : "\u25B6 Play");
  playBtn.addEventListener("click", () => {
    playing = !playing;
    updatePlay();
    sync();
  });
  if (reduced) playBtn.hidden = true;

  const tabs = SCENARIOS.map((s, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "fl-tab";
    button.dataset.tone = s.tone;
    button.append(document.createElement("i"), s.tab);
    // Picking a route interrupts whatever is playing and starts it from the top.
    button.addEventListener("click", () => {
      cycle = false;
      playing = true;
      updatePlay();
      loadScenario(i);
    });
    $("fl-tabs").append(button);
    return button;
  });

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      sync();
    }, { threshold: 0.3 }).observe($("fl-win"));
  } else {
    onScreen = true;
  }
  document.addEventListener("visibilitychange", sync);

  updatePlay();
  loadScenario(0);
})();
