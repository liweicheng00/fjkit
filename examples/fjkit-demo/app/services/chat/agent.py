"""A stand-in for a model: a scripted answer, written a word at a time.

The demo has no API key, so the token source is a script. It behaves like the
real thing in the three ways the page has to survive: tokens arrive with a
delay between them, there is a long pause in the middle where a model would be
running a tool, and a question with "fail" in it stops halfway with an error.
Replacing this module with a real client changes nothing else.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator


class AgentError(Exception):
    """The model stopped producing tokens."""


def script(question: str) -> str:
    """The whole answer the script gives to `question`."""
    return (
        f"You asked: {question.strip()} — "
        "This reply is one response that the server keeps writing to. "
        "Each word is a server-sent event named token, which the bubble appends with beforeend. "
        "A moment ago the stream went quiet, the way it does while a model runs a tool. "
        "Reload the page now and the bubble reconnects: the first event it reads is a snapshot "
        "of everything written so far, so nothing is lost and nothing is repeated. "
        "When the reply is finished the server sends done, and the connection closes for good."
    )


#: The sentence after which the script pauses, as a model pauses for a tool call.
_PAUSE_AFTER = "beforeend. "


def _words(text: str) -> list[str]:
    """Split into tokens that keep their trailing space, as a model's tokens do."""
    return re.findall(r"\S+\s*", text)


async def answer(question: str, *, token_seconds: float, tool_seconds: float) -> AsyncIterator[str]:
    """Yield the scripted answer to `question` a word at a time."""
    fails = "fail" in question.lower()
    words = _words(script(question))
    for n, word in enumerate(words):
        await asyncio.sleep(token_seconds)
        if fails and n == len(words) // 2:
            raise AgentError("The model stopped responding halfway through the reply.")
        yield word
        if word.endswith(_PAUSE_AFTER):
            await asyncio.sleep(tool_seconds)
