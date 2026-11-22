"""Tries the agent on tests/eval_questions.json with the REAL services (Groq, Pinecone, Tavily) and reports how it did.

    python -m tests.run_eval                   a sample of 10 questions that covers every path
    python -m tests.run_eval Q01 Q23           only these questions
    python -m tests.run_eval --all             all 33 questions (a big bite out of the free daily Groq budget)
    python -m tests.run_eval --followups       the follow-up questions in eval_followups.json, each with the earlier messages of its chat
    python -m tests.run_eval --budget 20000    stop before a question that could push any one model over this many tokens

It is not part of pytest: it needs your keys and spends Groq tokens and Tavily credits.
It stops at the first error, so a broken setup never burns tokens on the remaining questions.
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.agent.graph import ask

QUESTIONS = Path(__file__).with_name("eval_questions.json")
FOLLOW_UPS = Path(__file__).with_name("eval_followups.json")
SAMPLE = ["Q01", "Q02", "Q03", "Q04", "Q13", "Q22", "Q23", "Q25", "Q27", "Q31"]
TOKENS_PER_MINUTE = 6000  # Groq allows 8,000 per model per minute. Stay under it.
MOST_ONE_QUESTION_CAN_COST = 8000  # the slowest path: weak KB, weak web, rewrite, weak again, fallback
DAILY_TOKENS = 200_000  # Groq free plan, per model
SHOW_ANSWER = {"web", "no_answer", "direct", "followup"}  # a person should read these: no automatic check can judge them


def plain(text: str) -> str:
    """Lower-case, with fancy dashes and every kind of space made plain, so '14\u202fcharacters' still matches '14 characters'."""
    for fancy in ("\u2011", "\u2010", "\u2013", "\u2014"):
        text = text.replace(fancy, "-")
    return " ".join(text.split()).lower()


def judge(item: dict, result: dict) -> dict:
    cited = {c["source"] for c in result["citations"]}
    answer = plain(result["answer"])
    leaks = [m for m in item.get("must_not_mention", []) if plain(m) in answer]  # things that must NOT show up
    if item.get("no_web") and any(line.startswith("Web search") for line in result["trace"]):
        leaks.append("a web search")
    return {
        "path": result["source_used"] == item["expected_path"],
        "files": set(item["expected_files"]) <= cited,
        "missing": [m for m in item["must_mention"] if plain(m) not in answer],
        "leaks": leaks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Try the agent on the evaluation questions, using the real services.")
    parser.add_argument("ids", nargs="*", help="question ids, for example Q01 Q23 (default: a sample of 10)")
    parser.add_argument("--all", action="store_true", help="run all questions")
    parser.add_argument("--followups", action="store_true", help="run the follow-up questions (eval_followups.json) instead")
    parser.add_argument("--budget", type=int, default=40000, help="tokens one model may use in this run (default 40000)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # show each question as soon as it is done, even when piped

    items = {q["id"]: q for q in json.loads((FOLLOW_UPS if args.followups else QUESTIONS).read_text(encoding="utf-8"))}
    if args.followups:
        wanted = args.ids or list(items)
    else:
        wanted = list(items) if args.all else (args.ids or SAMPLE)
    unknown = [i for i in wanted if i not in items]
    if unknown:
        sys.exit(f"Unknown question ids: {', '.join(unknown)}")

    spent: dict[str, int] = defaultdict(int)
    ran, problems, notes = [], [], []
    for position, qid in enumerate(wanted):
        item = items[qid]
        if max(spent.values(), default=0) + MOST_ONE_QUESTION_CAN_COST > args.budget:
            print(f"\nStopped before {qid}: one more question could take a model over the {args.budget:,}-token budget.")
            print("Not run:", " ".join(wanted[position:]))
            break
        started = time.time()
        try:
            result = ask(item["question"], item.get("history"))
        except Exception as exc:  # stop at the first failure: do not spend tokens on a broken setup
            limit = " (the Groq limit was reached)" if getattr(exc, "status_code", None) == 429 else ""
            print(f"\n{qid} FAILED{limit}: {type(exc).__name__}: {str(exc)[:300]}")
            print("Stopped. Not run:", " ".join(wanted[position:]))
            problems.append(qid)
            break
        seconds = time.time() - started
        for model, tokens in result["tokens"].items():
            spent[model] += tokens
        verdict = judge(item, result)
        ok = verdict["path"] and verdict["files"] and not verdict["missing"] and not verdict["leaks"]
        if not ok:
            problems.append(qid)
        used = sum(result["tokens"].values())
        print(
            f"{qid} {item['category']:9} path {'ok' if verdict['path'] else 'NO'} ({result['source_used']:11}) "
            f"files {'ok' if verdict['files'] else 'NO'} facts {'ok' if not verdict['missing'] else 'NO'} "
            f"clean {'ok' if not verdict['leaks'] else 'NO'} {used:6,} tokens {seconds:5.1f}s"
        )
        if "history" in item:  # a follow-up: show what the router made of it
            print(f"      \"{item['question']}\"  ->  {result['trace'][0]}")
        ran.append((item, result, verdict, ok))
        if not ok or item["category"] in SHOW_ANSWER:
            notes.append((item, result, verdict))
        busiest = max(result["tokens"].values(), default=0)
        time.sleep(max(0.0, busiest * 60 / TOKENS_PER_MINUTE - seconds))  # stay under Groq's per-minute limit

    for item, result, verdict in notes:
        print(f"\n--- {item['id']} ({item['category']}, expected {item['expected_path']}) {item['question'][:110]}")
        for line in result["trace"]:
            print("   trace:", line)
        print("   cited:", [c["source"] for c in result["citations"]] or "nothing")
        if item["expected_files"]:
            print("   expected files:", item["expected_files"], "-> all cited" if verdict["files"] else "-> NOT all cited")
        if verdict["missing"]:
            print("   facts missing from the answer:", verdict["missing"])
        if verdict["leaks"]:
            print("   should NOT have appeared:", verdict["leaks"])
        print("   answer:", result["answer"][:900].replace("\n", "\n           "))

    print("\n=== summary ===")
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item, _, verdict, _ in ran:
        by_category[item["category"]][1] += 1
        by_category[item["category"]][0] += verdict["path"]
    print("right path:", " | ".join(f"{cat} {right}/{total}" for cat, (right, total) in by_category.items()) or "nothing ran")
    kb = [verdict for item, _, verdict, _ in ran if item["expected_files"]]
    if kb:
        print(f"KB answers: right files cited {sum(v['files'] for v in kb)}/{len(kb)} | expected facts present {sum(not v['missing'] for v in kb)}/{len(kb)}")
    for model, tokens in sorted(spent.items()):
        print(f"tokens used: {model:22} {tokens:7,}  ({tokens / DAILY_TOKENS:.0%} of one day's {DAILY_TOKENS:,})")
    if ran:
        print(f"average per question: {sum(spent.values()) / len(ran):,.0f} tokens")
    print("questions to look at:", " ".join(problems) or "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
