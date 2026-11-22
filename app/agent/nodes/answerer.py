"""Final steps: write the reply. One function for each way the flow can end."""
import re
from datetime import date

from langchain_core.documents import Document

from app.agent import llm, prompts
from app.agent.state import AgentState, asked

WEB_NOTICE = "No company document answers this, so the answer below comes from public web sources. Please check it before acting on it."
FALLBACK_NOTICE = "I could not confirm this from the company documents or the web, so treat the answer below as general guidance only."
COMPANY_ONLY_NOTICE = "I could not confirm this from the company documents, so treat the answer below as general guidance only."
LIVE_WORDS = re.compile(r"\b(now|today|current|currently|latest|newest|recent|recently|this (?:week|month|year))\b", re.IGNORECASE)
STALE_AFTER_DAYS = 7

# The models like to write look-alike characters. They show up as odd gaps, and copying a file name or link from the page breaks.
LOOK_ALIKES = str.maketrans(
    {"\u2010": "-", "\u2011": "-", "\u00a0": " ", "\u2009": " ", "\u202f": " ", "\u200b": None}  # hyphens, no-break and thin spaces, zero-width space
)


def _age_warning(question: str, docs: list[Document]) -> str:
    """For a "now" or "latest" question, say so when even the newest page is old. Done in code because the model can be fooled
    by a page that says "updated a minute ago" (that only says when the page was saved)."""
    if not LIVE_WORDS.search(question):
        return ""
    dates = []
    for doc in docs:
        try:
            dates.append(date.fromisoformat(doc.metadata.get("published_date") or ""))
        except ValueError:  # no date, or an odd one
            pass
    if not dates:
        return ""
    newest = max(dates)
    days = (date.today() - newest).days
    if days <= STALE_AFTER_DAYS:
        return ""
    return f"Heads up: the newest page I found is dated {newest.isoformat()} ({days} days ago), so it may not show the situation today. For the live state, check the service's own official website."


def _plain(text: str) -> str:
    """The chat page shows plain text. Drop the markdown symbols the model sometimes adds anyway, and make look-alike characters plain."""
    text = text.translate(LOOK_ALIKES)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?=\S)([^*\n]+?)(?<=\S)\*(?!\*)", r"\1", text)  # *italic*, but not "* bullet" lines
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text.replace("`", "")


def _reply(prompt: str, *, fast: bool = False) -> str:
    text = _plain(str(llm.get_llm(fast=fast).invoke(prompt).content).strip())
    return text or "The assistant sent an empty reply. Please ask again."


def _citations(docs: list[Document], kind: str) -> list[dict]:
    """One entry per source (a file name or a web address), in the order the evidence was found."""
    found: dict[str, dict] = {}
    for doc in docs:
        meta = doc.metadata
        found.setdefault(meta["source"], {"source": meta["source"], "type": kind, "title": meta.get("title", "")})
    return list(found.values())


def generate_answer(state: AgentState) -> dict:
    """Reads: question (restated, for a follow-up), docs, source_used. Writes: answer, citations, trace.

    Answers ONLY from the evidence. A web answer always starts with a notice that it is not from company documents.
    """
    question = asked(state)
    web = state["source_used"] == "web_search"
    extra = prompts.WEB_RULE.format(today=date.today().isoformat()) if web else ""  # the model cannot know the date, so a stale page would look current
    prompt = prompts.ANSWER.format(question=question, evidence=prompts.format_evidence(state["docs"]), extra=extra)
    answer = _reply(prompt)
    if web:
        notices = [WEB_NOTICE, _age_warning(question, state["docs"])]
        answer = "\n\n".join([n for n in notices if n] + [answer])
    return {
        "answer": answer,
        "citations": _citations(state["docs"], "web" if web else "kb"),
        "trace": [f"Answer generated from {'WEB SEARCH' if web else 'PRIVATE KB'}"],
    }


def answer_direct(state: AgentState) -> dict:
    """Reads: question (restated, for a follow-up). Writes: answer, source_used="direct", trace. Plain chat, no search."""
    return {
        "answer": _reply(prompts.DIRECT.format(question=asked(state)), fast=True),
        "source_used": "direct",
        "trace": ["Direct answer (no search)"],
    }


def fallback_answer(state: AgentState) -> dict:
    """Reads: question (restated, for a follow-up), public. Writes: answer, source_used="fallback", citations, trace.

    Best-effort reply that always starts with a notice that the evidence was too weak. No sources are cited.
    The notice only mentions the web if the web could have helped (and was searched).
    """
    body = _reply(prompts.FALLBACK.format(question=asked(state)))
    notice = FALLBACK_NOTICE if state["public"] else COMPANY_ONLY_NOTICE
    return {
        "answer": f"{notice}\n\n{body}",
        "source_used": "fallback",
        "citations": [],
        "trace": ["Fallback answer: not enough evidence"],
    }
