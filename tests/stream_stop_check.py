"""Run by test_streaming.py, never by pytest itself: a real uvicorn server gets a real stop signal while an answer is still being made for
a page that has gone away. The job writes the file named on the command line when it has finished (that is what saving the answer stands for)."""
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI

from app.api import streaming

SAVED = sys.argv[1]


@asynccontextmanager
async def lifespan(_app):
    yield
    await streaming.wait_for_jobs()  # the same step app/main.py runs when it shuts down


api = FastAPI(lifespan=lifespan)


@api.post("/ask")
async def ask():
    def job(emit):
        emit("step", {"n": 1})
        time.sleep(1.0)
        with open(SAVED, "w") as f:
            f.write("saved")
        return {}

    return streaming.stream(job)


server = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=0, log_level="warning"))


def the_page():
    while not server.started:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    with httpx.stream("POST", f"http://127.0.0.1:{port}/ask") as response:
        next(response.iter_lines())  # the page sees the first step...
    time.sleep(0.2)  # ...and goes away
    signal.raise_signal(signal.SIGTERM)  # what `docker stop` sends


threading.Thread(target=the_page).start()
server.run()
