"""Steps 3 and 6: is the evidence good enough to answer? Used for both KB and web evidence."""
from app.agent import llm, prompts
from app.agent.state import AgentState, EvidenceGrade, asked


def grade_evidence(state: AgentState) -> dict:
    """Reads: question (restated, for a follow-up), docs, source_used, public. Writes: grade ("good" or "weak"), trace."""
    web = state["source_used"] == "web_search"
    notes = []
    if not state["docs"]:  # nothing to judge, so don't spend tokens
        grade = "weak"
        notes.append("nothing found")
    else:
        prompt = prompts.GRADER.format(
            question=asked(state),
            evidence=prompts.format_evidence(state["docs"]),
            extra=prompts.WEB_GRADER_RULE if web else prompts.KB_GRADER_RULE,  # each stage has its own extra rule: live/private data for documents, news for web pages
        )
        grade = llm.decide(EvidenceGrade, prompt, EvidenceGrade(grade="weak"), fast=not web).grade  # unsure: weak. Web pages are noisier than our own documents, so the bigger model judges them
    if grade == "weak" and not web and not state["public"]:
        notes.append("company-only question, so no web search")
    suffix = f" ({', '.join(notes)})" if notes else ""
    return {"grade": grade, "trace": [f"{'Web' if web else 'KB'} evidence grade → {grade.upper()}{suffix}"]}
