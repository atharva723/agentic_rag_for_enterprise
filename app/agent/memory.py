"""Short-term memory: the last few exchanges of ONE chat, cut short so a follow-up costs few extra tokens.

Nothing is stored here. The caller sends the chat's earlier exchanges with each question, and the agent forgets them as soon as the
answer is written. Two chats can never mix, because a chat only ever sends its own.
"""
from app.config import get_settings

MAX_CHARS = 300  # kept of each earlier question and each earlier answer: enough to know the topic, cheap to repeat


def _short(text: str) -> str:
    text = " ".join(text.split())  # one line: earlier messages are background, not layout
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rstrip() + "…"


def recent(history: list[dict] | None) -> list[dict]:
    """The last MEMORY_TURNS exchanges ({"question", "answer"}, oldest first), each cut short. Empty when memory is off."""
    turns = get_settings().memory_turns
    if turns <= 0 or not history:
        return []
    return [{"question": _short(h["question"]), "answer": _short(h["answer"])} for h in history[-turns:]]
