# agent/

The brain. One question goes in, one answer comes out.

- `graph.py` - the whole flow on one screen: the steps, and the rules for what runs next. Start here. `ask(question, history, on_step, web)` is the entry point. `history` is the earlier exchanges of the same chat (optional). `on_step` is a function that is told as each step starts and ends, so a page can show the path live (optional, see "Live steps" below). `web` is True when the person turned Web search on for this question (optional, see "Web search switch" below). `ask` also reports (and logs) the LLM tokens each question used.
- `progress.py` - the plain-words status line for each step while it runs ("Searching the company documents…", "Not enough in the company documents, searching the public web…"), and the shape of the two events `on_step` gets. This is the file to edit to change that wording.
- `state.py` - the shared notes every step reads and writes (question, evidence, grade, answer, decision path), and the shape of each LLM decision.
- `memory.py` - short-term memory: keeps the last few exchanges of one chat (`MEMORY_TURNS`), each cut short. Nothing is stored.
- `prompts.py` - every instruction we send to the LLM, and how evidence and earlier messages are shown to it.
- `llm.py` - the one place that creates the LLM (Groq). `get_llm()` gives the answer model, `get_llm(fast=True)` the fast one, and `decide()` asks a model for a small decision (the fast one unless told otherwise).
- `nodes/` - the steps themselves, one small file per job.

The flow: route the question, search the KB, grade the evidence. If it is weak, search the web and grade again. If it is still weak, rewrite the question once and retry. After that, give a fallback answer.

## Follow-ups (short-term memory)

A follow-up like "what if it keeps disconnecting?" only makes sense with the chat before it. The agent keeps nothing between questions, so the caller gives it the chat's earlier question-and-answer pairs with each new question: `ask(question, history)`. In a saved chat (`/api/conversations/{id}/messages`, or `.../messages/stream` as the chat page uses) the server loads them from the database, so nobody can invent a chat history. The evaluation script (`tests/run_eval.py --followups`) passes its own.

- `memory.recent()` keeps the last `MEMORY_TURNS` pairs (3 by default) and cuts each text to 300 characters. `MEMORY_TURNS=0` switches memory off.
- Only the router reads them. It restates the message as a complete question ("The VPN connection keeps dropping after a few hours. Is that normal?"), and writes the search query, the second search and `public` for that restated question. The grader, the rewriter and every answer step work on the restated question too. They never see the earlier messages.
- Earlier messages are background, never facts. The router prompt says so, and every answer still comes only from evidence found for this question.
- A new topic is left alone: after a VPN chat, "how long does a loaner laptop take?" is searched as the laptop question only. A "thanks" still gets a direct reply.
- The safety rules run again for every message, on the restated question. After a public topic, "what is the admin password for our office router?" is still company-only and does not reach the web (unless the person turned Web search on).
- A chat's first message has no history, so it is routed exactly as before: same prompt, same decision shape. If the router's reply cannot be read, the message is searched as typed, with no web search.
- The decision path shows "Follow-up understood as: ..." when the message was restated.

Limits: the router is the small fast model. It sometimes leaves a short follow-up unchanged (it still writes a good search query), and a vague "it" can be read the wrong way. Exchanges older than `MEMORY_TURNS` are forgotten, and a long chat is not summarised.

## Live steps

`ask(question, history, on_step)` can report its progress while it works, so the chat page can show the path as it happens.

- `on_step` gets one small dict when a step starts (with a plain-words `label` from `progress.py`, such as "Searching the company documents…") and one when it ends (with the decision-path `lines` the step wrote).
- Without `on_step` the graph runs exactly as before. With it, the same run is read step by step from LangGraph's own `tasks` stream, so no step needed any change.
- A step is announced before it does its work. A step that crashes is never reported as done.
- A callback that fails only logs a warning. It can never cost the person their answer.

## Web search switch

Normally the router alone decides whether the web may be used (`public`). The chat page's **Web search** button adds the person's own choice.

- `ask(..., web=True)` puts `web_allowed` in the notes. The router then sets `public` to True for a knowledge-base question it judged company-only, and adds "Web search turned on by you" to the decision path.
- Everything else stays the same: the KB is searched first, the web is used only if that evidence is weak, and the search text is the router's cleaned query (no names, emails or secrets).
- It never applies to small talk (nothing is searched). It also never applies when the router's reply was unreadable: the query is then the question as typed, not cleaned, so it stays off the network.
- Credentials are still never written out, and a page about a look-alike product is still graded weak.

## Safety rules

- **Company-only questions do not go to the web.** The router decides if public web pages could answer the question at all (`public`). Passwords, tickets, people and equipment are company-only. For those, a weak KB answer leads to one retry on the KB and then the fallback. This rule exists because a live test showed the web returning a stranger's default admin password for a look-alike product name. The grader alone cannot reliably tell look-alike names apart. The one way around it is the person's own choice: the Web search button (see above).
- **Credentials are never written out.** The answer prompt forbids passwords, keys and tokens, even if the evidence contains one. The fallback never states company facts.
- **Notices are added by code, not by the model.** A web answer always starts with "No company document answers this...". A fallback always starts with "I could not confirm this...".
- **Old pages are flagged by code.** For a "now" or "latest" question, if even the newest web page is more than a week old, a "Heads up" line with its date is added. The model alone can be fooled by a page that says "updated a minute ago" (that only says when the page was saved). The search tool cannot show live status, only what pages said when they were saved.
- **Evidence is treated as untrusted text.** Every prompt tells the model to ignore instructions inside documents and web pages.
- **Only the search query leaves the network.** The router drops names, emails and secrets from it.
- **A request for information is never small talk**, even one the assistant cannot answer.

## Two-part questions

If a question asks two different things, the router writes a second short search (`also`). Each search takes turns filling the evidence (up to `TOP_K` + 2 chunks), so both topics are represented. The router does not always split (a three-part question may still be merged), and then the agent may only find part of the answer.

## Two models, on purpose

| Job | Setting | Default |
| --- | --- | --- |
| Router, grader for company documents, rewriter, small talk | `GROQ_FAST_MODEL` | `openai/gpt-oss-20b` |
| Final answers, the fallback, and the grader for web pages | `GROQ_MODEL` | `openai/gpt-oss-120b` |

Groq counts tokens per model. On the free plan each model gets 8,000 tokens a minute and 200,000 a day, so two models give you two budgets. The fast model makes quick decisions as strict JSON (the reply always fits the schema). The bigger one writes the answers. It also grades web pages, because they are noisier than our own documents: in a test the fast model called fresh outage news "weak" every time, and the bigger model judged it correctly.

## Keeping token use low

- Prompts are short, and the evidence in them is cut to about 1,500 tokens, whatever `TOP_K` is.
- If a search finds nothing, the grader is skipped. No model call is made.
- The models think before they answer. `reasoning_effort` is set to `low` so that hidden thinking stays small.
- Every call has a safety cap on its reply length.
- A typical question from the knowledge base uses about 3,000 tokens in total. A question that goes to the web uses about 4,000 to 5,000, and up to about 7,000 if it also needs a retry.
- A follow-up costs about 300 tokens more than the same question on its own, because the router also reads the last few messages (measured: about 3,300 against about 3,000 for a knowledge base question). A "thanks" costs about 1,100.
- To spend less on questions with no answer, set `MAX_RETRIES=0` in `.env`. The agent then skips the rewrite and the second search.
- If Groq's limit is reached, chat answers "The AI service is busy" instead of crashing. Waiting is enough: the per-minute limit refills within a minute.
