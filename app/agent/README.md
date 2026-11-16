# agent/

The brain. One question goes in, one answer comes out.

- `graph.py` - the whole flow on one screen: the steps, and the rules for what runs next. Start here. `ask(question)` is the entry point. It also reports (and logs) the LLM tokens each question used.
- `state.py` - the shared notes every step reads and writes (question, evidence, grade, answer, decision path), and the shape of each LLM decision.
- `prompts.py` - every instruction we send to the LLM, and how evidence is shown to it.
- `llm.py` - the one place that creates the LLM (Groq). `get_llm()` gives the answer model, `get_llm(fast=True)` the fast one, and `decide()` asks a model for a small decision (the fast one unless told otherwise).
- `nodes/` - the steps themselves, one small file per job.

The flow: route the question, search the KB, grade the evidence. If it is weak, search the web and grade again. If it is still weak, rewrite the question once and retry. After that, give a fallback answer.

## Safety rules

- **Company-only questions never go to the web.** The router decides if public web pages could answer the question at all (`public`). Passwords, tickets, people and equipment are company-only. For those, a weak KB answer leads to one retry on the KB and then the fallback. This rule exists because a live test showed the web returning a stranger's default admin password for a look-alike product name. The grader alone cannot reliably tell look-alike names apart.
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
- To spend less on questions with no answer, set `MAX_RETRIES=0` in `.env`. The agent then skips the rewrite and the second search.
- If Groq's limit is reached, chat answers "The AI service is busy" instead of crashing. Waiting is enough: the per-minute limit refills within a minute.
