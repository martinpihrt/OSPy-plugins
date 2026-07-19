#!/usr/bin/env python3
"""External watchdog for an OSPy update.

This helper deliberately imports no OSPy modules.  It must remain able to roll
the repository back even when the updated OSPy sources cannot be imported.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time


COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, value):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def _valid_state(state, token):
    repo = os.path.abspath(str(state.get("repository", "")))
    previous = str(state.get("previous_commit", ""))
    target = str(state.get("target_commit", ""))
    return (
        token
        and state.get("token") == token
        and COMMIT_RE.fullmatch(previous) is not None
        and COMMIT_RE.fullmatch(target) is not None
        and os.path.isdir(os.path.join(repo, ".git"))
    )


def _restart_ospy(state):
    if shutil.which("systemctl") and os.path.isdir("/run/systemd/system"):
        subprocess.run(
            ["systemctl", "--no-block", "restart", "ospy.service"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return
    if shutil.which("service"):
        # SysV restart can legitimately take longer than the watchdog should
        # remain attached to the old OSPy process tree.  Queue it in a detached
        # process; the init system owns completion after the command starts.
        subprocess.Popen(
            ["service", "ospy", "restart"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return
    repository = os.path.abspath(state["repository"])
    python = str(state.get("python") or sys.executable)
    subprocess.Popen(
        [python, "-u", os.path.join(repository, "run.py")],
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def monitor(state_path, token):
    state_path = os.path.abspath(state_path)
    state = _read_json(state_path)
    if not _valid_state(state, token):
        return 2

    acknowledgement = str(state.get("acknowledgement", state_path + ".ack"))
    result_path = str(state.get("result", state_path + ".result"))
    ready_path = str(state.get("ready", state_path + ".ready"))
    deadline = float(state.get("deadline", time.time() + 120))
    _write_json(ready_path, {
        "token": token,
        "time": time.time(),
        "pid": os.getpid(),
    })

    while time.time() < deadline:
        ack = _read_json(acknowledgement)
        if ack.get("token") == token:
            result = {
                "status": ack.get("status", "confirmed"),
                "time": time.time(),
                "previous_commit": state["previous_commit"],
                "target_commit": state["target_commit"],
            }
            _write_json(result_path, result)
            for path in (acknowledgement, ready_path, state_path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            return 0
        time.sleep(1)

    repository = os.path.abspath(state["repository"])
    previous = state["previous_commit"]
    result = {
        "status": "rolling_back",
        "time": time.time(),
        "previous_commit": previous,
        "target_commit": state["target_commit"],
    }
    _write_json(result_path, result)

    try:
        subprocess.run(
            ["git", "-C", repository, "reset", "--hard", previous],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        previous_branch = str(state.get("previous_branch", ""))
        if previous_branch and BRANCH_RE.fullmatch(previous_branch):
            subprocess.run(
                ["git", "-C", repository, "checkout", "-B", previous_branch, previous],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
        result["status"] = "rolled_back"
        result["time"] = time.time()
        _write_json(result_path, result)
        for path in (ready_path, state_path):
            try:
                os.remove(path)
            except OSError:
                pass
        _restart_ospy(state)
        return 0
    except Exception as error:
        result["status"] = "rollback_failed"
        result["time"] = time.time()
        result["error"] = "{}: {}".format(type(error).__name__, error)
        _write_json(result_path, result)
        try:
            os.remove(ready_path)
        except OSError:
            pass
        return 4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    return monitor(args.state, args.token)


if __name__ == "__main__":
    raise SystemExit(main())
