"""The page's code for a live reply (ui/common.js) runs in a browser, so these checks run the same file under Node.js.
They are skipped when Node.js is not installed. The server side of the same feature is tested in test_streaming.py."""
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS = Path(__file__).parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_page_reads_a_live_reply_however_the_network_cuts_it_up():
    """Events are read in order, even when a chunk ends inside a character or inside the blank line between two events, an error or a
    broken connection is told apart from an answer, and a step is drawn the moment it arrives."""
    run = subprocess.run(["node", str(TESTS / "ui_stream_check.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
