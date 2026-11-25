"""The Server-Sent Events helper: events leave in order and in time, a page that goes away does not stop the job, errors are plain."""
import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from conftest import parse_events
from fastapi import HTTPException

from app.api.streaming import INTERNAL_ERROR, format_event, read_events, stream, wait_for_jobs

ROOT = Path(__file__).parent.parent


async def collect(response) -> str:
    return "".join([chunk async for chunk in response.body_iterator])


def run(job) -> str:
    """Stream a job to the end and return everything the page would have received."""

    async def main():
        return await collect(stream(job))

    return asyncio.run(main())


def test_an_event_is_one_event_with_its_json_on_a_single_line():
    text = format_event("step", {"label": "Searching…\nnext line", "arrow": "→"})
    assert text.endswith("\n\n") and text.count("\n") == 3  # the event line, the data line, the blank line: nothing in the data splits it
    assert parse_events(text) == [("step", {"label": "Searching…\nnext line", "arrow": "→"})]  # and the page gets the same text back


def test_a_page_reads_the_events_in_order_and_the_end_marker_stops_it():
    async def main():
        queue = asyncio.Queue()
        for item in (("step", {"n": 1}), ("answer", {"n": 2}), None):
            queue.put_nowait(item)
        return "".join([chunk async for chunk in read_events(queue)])

    assert parse_events(asyncio.run(main())) == [("step", {"n": 1}), ("answer", {"n": 2})]


def test_a_quiet_connection_gets_keep_alive_comments_that_a_page_ignores():
    async def main():
        queue, got = asyncio.Queue(), []

        async def read():
            async for chunk in read_events(queue, keep_alive=0.02):
                got.append(chunk)

        task = asyncio.create_task(read())
        await asyncio.sleep(0.15)  # nothing arrives for a while
        queue.put_nowait(("answer", {"done": True}))
        queue.put_nowait(None)
        await task
        return got

    got = asyncio.run(main())
    assert got.count(": keep-alive\n\n") >= 2 and got[-1] == format_event("answer", {"done": True})
    assert parse_events("".join(got)) == [("answer", {"done": True})]  # a comment is not an event


def test_a_job_reports_steps_and_its_result_is_the_last_event():
    def job(emit):
        emit("step", {"n": 1})
        emit("step", {"n": 2})
        return {"answer": "done"}

    assert parse_events(run(job)) == [("step", {"n": 1}), ("step", {"n": 2}), ("answer", {"answer": "done"})]


def test_the_response_is_an_event_stream_that_nothing_may_cache_or_buffer():
    async def main():
        response = stream(lambda emit: {})
        await collect(response)
        return response

    response = asyncio.run(main())
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform" and response.headers["x-accel-buffering"] == "no"


def test_events_reach_the_page_while_the_job_is_still_running():
    release = threading.Event()

    def job(emit):
        emit("step", {"n": 1})
        assert release.wait(5)
        return {"answer": "late"}

    async def main():
        events = stream(job).body_iterator
        first = await asyncio.wait_for(anext(events), 2)  # here, the job has not finished and cannot until we let it
        release.set()
        return first, "".join([chunk async for chunk in events])

    first, rest = asyncio.run(main())
    assert parse_events(first) == [("step", {"n": 1})] and parse_events(rest) == [("answer", {"answer": "late"})]


def test_a_page_that_goes_away_does_not_stop_the_job():
    """Closing the tab must not lose a question that is already being answered: the job still finishes, and saves."""
    release, finished, saved = threading.Event(), threading.Event(), []

    def job(emit):
        emit("step", {"n": 1})
        release.wait(5)
        saved.append("the answer was saved")  # what saving to the database does
        finished.set()
        return {"answer": "x"}

    async def main():
        events = stream(job).body_iterator
        await asyncio.wait_for(anext(events), 2)  # the page reads one event...
        await events.aclose()  # ...and goes away
        release.set()

    asyncio.run(main())
    assert finished.wait(5) and saved == ["the answer was saved"]


def test_a_server_that_is_stopping_waits_for_an_answer_that_is_still_being_made():
    release, finished = threading.Event(), threading.Event()

    def job(emit):
        assert release.wait(5)
        finished.set()
        return {}

    async def main():
        stream(job)  # the page that asked has gone away: nobody reads the events
        waiting = asyncio.create_task(wait_for_jobs(timeout=5))
        await asyncio.sleep(0.3)
        held_back = not waiting.done()  # the job is still working, so the shut-down has to wait
        release.set()
        await waiting
        return held_back

    assert asyncio.run(main()) is True
    assert finished.is_set()  # and it let go only after the job had finished


def test_a_server_with_nothing_running_stops_at_once():
    started = time.monotonic()
    asyncio.run(wait_for_jobs(timeout=5))
    assert time.monotonic() - started < 1


def test_a_server_that_is_stopping_gives_up_on_a_job_that_takes_too_long_and_says_so(caplog):
    release = threading.Event()

    def job(emit):
        release.wait(5)
        return {}

    async def main():
        stream(job)
        started = time.monotonic()
        await wait_for_jobs(timeout=0.3)
        return time.monotonic() - started

    took = asyncio.run(main())
    release.set()  # let the thread end
    assert 0.3 <= took < 3  # it waited for the whole time it was given, and not for the 5 seconds the job wanted
    assert "answer(s) were still being made" in caplog.text


def test_a_real_stop_signal_does_not_lose_an_answer_that_is_still_being_made(tmp_path):
    """The real thing: a real server, a real stream whose page goes away, then the signal `docker stop` sends. uvicorn ends the process right
    after the app's shut-down step (it raises the signal again, with its default action), and that kills every thread, even one that is not
    a daemon. So the answer is saved only if the shut-down step waits for the job (see tests/stream_stop_check.py)."""
    saved = tmp_path / "saved.txt"
    run = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "stream_stop_check.py"), str(saved)],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True, timeout=60,
    )
    assert saved.exists(), "the server stopped before the answer was saved. " + run.stderr[-600:]


def test_a_job_that_finishes_after_the_server_has_stopped_does_not_crash(monkeypatch):
    crashes, finished, release = [], threading.Event(), threading.Event()
    monkeypatch.setattr(threading, "excepthook", crashes.append)

    def job(emit):
        release.wait(5)
        emit("step", {"n": 1})  # nobody is listening: the event loop is closed
        finished.set()
        return {}

    async def main():
        stream(job)

    asyncio.run(main())  # the loop closes while the job is still running
    release.set()
    assert finished.wait(5)
    for thread in threading.enumerate():
        if thread.name == "stream-job":
            thread.join(5)
    assert crashes == []


def test_the_job_runs_in_its_own_thread_so_the_event_loop_stays_free():
    seen = {}

    def job(emit):
        seen["job"] = threading.current_thread()
        return {}

    async def main():
        seen["loop"] = threading.current_thread()
        await collect(stream(job))

    asyncio.run(main())
    assert seen["job"] is not seen["loop"] and seen["job"].name == "stream-job"


def test_an_http_error_in_the_job_becomes_an_error_event_with_its_status_and_message():
    def job(emit):
        emit("step", {"n": 1})
        raise HTTPException(status_code=429, detail="The AI service is busy.")

    assert parse_events(run(job)) == [("step", {"n": 1}), ("error", {"status": 429, "detail": "The AI service is busy."})]


def test_any_other_error_is_a_plain_500_and_the_details_stay_in_the_log(caplog):
    def job(emit):
        raise RuntimeError("secret internal detail")

    text = run(job)
    assert parse_events(text) == [("error", {"status": 500, "detail": INTERNAL_ERROR})]
    assert "secret internal detail" not in text and "secret internal detail" in caplog.text
