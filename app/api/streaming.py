"""Server-Sent Events for a slow job: the page sees progress as it happens, and the job finishes even if the page goes away.

How it works: the job runs in its own thread and reports through emit(). The response only reads those reports from a queue and writes
them to the page. So closing the tab, or losing the connection, never stops the job: it still saves its result, as it would without
streaming. Stopping the server is different. uvicorn ends the whole process right after the app's shut-down step (it raises the stop
signal again, with its default action), and that kills every thread, even one that is not a daemon. So the shut-down step calls
wait_for_jobs(), which lets the running jobs finish first. The page reads the events with fetch() (not EventSource, which cannot send
the sign-in header).
"""
import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from typing import Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

log = logging.getLogger(__name__)

KEEP_ALIVE_SECONDS = 15  # a comment line this often stops a proxy from closing a connection that is quiet while the AI thinks
STOP_WAIT_SECONDS = 30  # the longest a stopping server waits for answers that are still being made (a normal one takes 3 to 10)
HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}  # the page must get each event at once, not in one lump at the end
INTERNAL_ERROR = "Something went wrong on our side. Please try again in a moment."

Emit = Callable[[str, dict], None]  # emit("step", {...}) sends one event

_jobs: list[threading.Thread] = []  # the threads stream() started. Only the event loop touches this list, so it needs no lock


def format_event(name: str, data: dict) -> str:
    """One event. The JSON stays on a single line (non-ASCII characters are escaped), so it can never split the event."""
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def read_events(queue: asyncio.Queue, keep_alive: float = KEEP_ALIVE_SECONDS) -> AsyncIterator[str]:
    """Hand the page each event as it arrives, until the job says it is over (None). While nothing arrives, send a keep-alive comment."""
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), keep_alive)
        except TimeoutError:
            yield ": keep-alive\n\n"  # a line that starts with a colon is a comment: the page ignores it
            continue
        if item is None:
            return
        yield format_event(*item)


def stream(job: Callable[[Emit], dict], result_event: str = "answer") -> StreamingResponse:
    """Run `job(emit)` in the background and stream what it reports. What the job returns is sent as the last event (`result_event`).
    If it raises an HTTPException, the page gets an "error" event with that status and message. Anything else gets a plain 500 message
    (the details are only logged). Must be called from a route that runs on the event loop (an `async def` route)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def put(item: tuple[str, dict] | None) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # the server is shutting down: nobody is listening any more
            pass

    def run() -> None:
        try:
            put((result_event, job(lambda name, data: put((name, data)))))
        except HTTPException as exc:
            put(("error", {"status": exc.status_code, "detail": exc.detail}))
        except Exception:
            log.exception("A streamed job failed")
            put(("error", {"status": 500, "detail": INTERNAL_ERROR}))
        finally:
            put(None)

    # A daemon thread, so a job that hangs can never keep the process from ending. A stopping server waits for jobs in wait_for_jobs() instead.
    thread = threading.Thread(target=run, daemon=True, name="stream-job")
    thread.start()
    _jobs[:] = [*_running(), thread]  # the finished jobs are forgotten here
    return StreamingResponse(read_events(queue), media_type="text/event-stream", headers=HEADERS)


def _running() -> list[threading.Thread]:
    return [t for t in _jobs if t.is_alive()]


async def wait_for_jobs(timeout: float = STOP_WAIT_SECONDS) -> None:
    """For the server's shut-down step: let the answers that are still being made finish and save. A closed page does not stop a job, but
    the process ends right after the shut-down step, so without this wait such an answer would be lost. After `timeout` seconds it
    gives up and says how many were left."""
    waiting = len(_running())
    if waiting:
        log.info("Stopping: waiting up to %d seconds for %d answer(s) that are still being made", timeout, waiting)
    deadline = time.monotonic() + timeout
    while _running() and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    left = len(_running())
    if left:
        log.warning("Stopped while %d answer(s) were still being made: they are lost", left)
