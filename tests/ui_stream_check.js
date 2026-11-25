// Checks the page's live-reply code (readEvents and stream() in ui/common.js) by running the real file under Node.
// Run by tests/test_ui_stream.py. Exits with an error message when a check fails.
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const sandbox = { console, Intl, TextDecoder, TextEncoder, ReadableStream, Response, Headers, AbortSignal, document: {}, setTimeout };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "ui", "common.js"), "utf8") + "\n;globalThis.api = { readEvents, parseEvent, stream };", sandbox);
const { readEvents, parseEvent, stream } = sandbox.api;

const enc = new TextEncoder();
const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
const START = event("step", { step: "retrieve_kb", status: "start", label: "Searching the company documents…" });
const DONE = event("step", { step: "retrieve_kb", status: "done", lines: ["Private KB retrieval → 4 chunks"] });
const ANSWER = event("answer", { answer: "Use the VPN → ok…", source_used: "private_kb" });
const TEXT = ": keep-alive\n\n" + START + DONE + ANSWER; // the arrow and the ellipsis are more than one byte each
const BYTES = enc.encode(TEXT);

const plain = (x) => JSON.parse(JSON.stringify(x ?? null)); // objects made in the sandbox have their own Object.prototype
const same = (actual, expected, message) => assert.deepStrictEqual(plain(actual), plain(expected), message);
const body = (...chunks) => new ReadableStream({ start: (c) => (chunks.forEach((x) => c.enqueue(x)), c.close()) });
const events = async (...chunks) => { const out = []; for await (const e of readEvents(body(...chunks))) out.push(e); return out; };
const reply = (...chunks) => async () => new Response(body(...chunks), { status: 200 });
// A real network drop hands over what already arrived and then fails. (controller.error() would throw the queued data away.)
const dropsAfter = (first) => { let n = 0; return new ReadableStream({ pull: (c) => (n++ === 0 ? c.enqueue(first) : c.error(new TypeError("network error"))) }); };

(async () => {
  const expected = await events(BYTES);
  same(expected.map((e) => [e.name, e.data.label ?? e.data.answer ?? e.data.lines]), [["step", "Searching the company documents…"], ["step", ["Private KB retrieval → 4 chunks"]], ["answer", "Use the VPN → ok…"]]);

  for (const [label, wire] of [["LF", BYTES], ["CRLF", enc.encode(TEXT.replace(/\n/g, "\r\n"))]]) {
    for (let i = 0; i <= wire.length; i++) same(await events(wire.slice(0, i), wire.slice(i)), expected, `${label}, cut after byte ${i}`);
  }
  same(await events(...Array.from(BYTES, (b) => Uint8Array.of(b))), expected, "one byte at a time");
  same((await events(enc.encode(START + 'event: step\ndata: {"half":'))).length, 1, "an event cut off before its blank line is not delivered");

  same(parseEvent('event: step\ndata: {"a":\ndata: 1}'), { name: "step", data: { a: 1 } });
  same(parseEvent('data:{"no_space":"a:b"}'), { name: "message", data: { no_space: "a:b" } });
  same(parseEvent("event: step\ndata: not json"), null);
  same(parseEvent(": keep-alive"), null);

  const shown = [];
  sandbox.fetch = reply(BYTES.slice(0, 30), BYTES.slice(30));
  same(await stream("/api/x", {}, (e) => shown.push(e.status)), { ok: true, status: 200, body: { answer: "Use the VPN → ok…", source_used: "private_kb" } });
  same(shown, ["start", "done"], "steps reach onStep in order");

  sandbox.fetch = reply(enc.encode(START + event("error", { status: 429, detail: "The AI service is busy." })));
  same(await stream("/api/x", {}, () => {}), { ok: false, status: 429, body: { detail: "The AI service is busy." } });
  sandbox.fetch = reply(enc.encode(START));
  same(await stream("/api/x", {}, () => {}), { ok: false, status: 0, body: {} }, "no answer and no error: status 0");
  for (const status of [401, 404, 429]) {
    sandbox.fetch = async () => new Response(JSON.stringify({ detail: "plain" }), { status, headers: { "content-type": "application/json" } });
    same(await stream("/api/x", {}, () => {}), { ok: false, status, body: { detail: "plain" } }, `${status} before the stream starts`);
  }

  sandbox.console = { error() {} };
  sandbox.fetch = reply(BYTES);
  same((await stream("/api/x", {}, () => { throw new Error("drawing bug"); })).ok, true, "a bug in the drawing code does not cost the answer");
  sandbox.fetch = async () => new Response(dropsAfter(BYTES), { status: 200 });
  same((await stream("/api/x", {}, () => {})).ok, true, "a drop after the answer keeps the answer");
  const got = [];
  sandbox.fetch = async () => new Response(dropsAfter(enc.encode(START)), { status: 200 });
  same(await stream("/api/x", {}, (e) => got.push(e.label)), { ok: false, status: 0, body: {} }, "a drop before the answer is status 0");
  same(got, ["Searching the company documents…"], "and the step that did arrive was shown");
  sandbox.fetch = async () => { throw new TypeError("Failed to fetch"); };
  same(await stream("/api/x", {}, () => {}), { ok: false, status: 0, body: {} }, "a failed fetch does not throw");

  // A step must be drawn the moment it arrives, not when the whole reply is in. If the reader waited for the end, this would never finish.
  let release;
  const gate = new Promise((resolve) => (release = resolve));
  let sent = 0;
  const slow = new ReadableStream({
    async pull(c) {
      if (sent++ === 0) c.enqueue(enc.encode(START));
      else if (sent === 2) (await gate, c.enqueue(enc.encode(ANSWER)));
      else c.close();
    },
  });
  sandbox.fetch = async () => new Response(slow, { status: 200 });
  let firstShown;
  const first = new Promise((resolve) => (firstShown = resolve));
  const finished = stream("/api/x", {}, () => firstShown());
  const timer = setTimeout(() => assert.fail("the first step was not drawn while the reply was still open"), 3000);
  await first;
  clearTimeout(timer);
  release();
  same((await finished).ok, true);
})().catch((error) => { console.error(error.message); process.exit(1); });
