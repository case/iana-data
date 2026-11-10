"""Tests for bin/ci-send-pushover, driven against a local HTTP listener."""

import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "ci-send-pushover"

ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "PUSHOVER_API_TOKEN": "tok",
    "PUSHOVER_USER_KEY": "usr",
    "PUSHOVER_TITLE": "IANA data - build failed",
    "PUSHOVER_MESSAGE": "Failed to build tlds.json",
}


@pytest.fixture
def listener():
    """A local endpoint recording each request body; `status` sets its reply."""
    state = {"bodies": [], "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            state["bodies"].append(self.rfile.read(length).decode())
            self.send_response(state["status"])
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/1/messages.json"
    yield state
    server.shutdown()
    thread.join()


def send(listener, tmp_path, **overrides):
    env = {**ENV, "PUSHOVER_URL": listener["url"], **overrides}
    return subprocess.run(
        [str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={key: value for key, value in env.items() if value is not None},
    )


def test_it_posts_all_four_fields(listener, tmp_path):
    result = send(listener, tmp_path)

    assert result.returncode == 0, result.stderr
    assert parse_qs(listener["bodies"][0]) == {
        "token": ["tok"],
        "user": ["usr"],
        "title": ["IANA data - build failed"],
        "message": ["Failed to build tlds.json"],
    }


def test_shell_syntax_in_a_field_arrives_as_text(listener, tmp_path):
    """The inline template this replaced would have run the substitution."""
    hostile = "\"; $(touch pwned) `touch pwned` ' & x=1 ❌"

    result = send(listener, tmp_path, PUSHOVER_MESSAGE=hostile)

    assert result.returncode == 0, result.stderr
    assert parse_qs(listener["bodies"][0])["message"] == [hostile]
    assert not (tmp_path / "pwned").exists()


def test_a_rejected_request_fails_the_step(listener, tmp_path):
    """An alert Pushover refused must not read as delivered."""
    listener["status"] = 400

    assert send(listener, tmp_path).returncode != 0


@pytest.mark.parametrize(
    "missing",
    ["PUSHOVER_API_TOKEN", "PUSHOVER_USER_KEY", "PUSHOVER_TITLE", "PUSHOVER_MESSAGE"],
)
def test_a_missing_field_fails_before_any_request(listener, tmp_path, missing):
    result = send(listener, tmp_path, **{missing: None})

    assert result.returncode != 0
    assert missing in result.stderr
    assert listener["bodies"] == []


def test_the_action_hands_inputs_over_as_environment():
    """The composite action must call the script, not template inputs inline."""
    action = SCRIPT.parent.parent / ".github" / "actions" / "pushover" / "action.yaml"
    text = action.read_text(encoding="utf-8")

    assert "bin/ci-send-pushover" in text
    assert "PUSHOVER_MESSAGE: ${{ inputs.message }}" in text
