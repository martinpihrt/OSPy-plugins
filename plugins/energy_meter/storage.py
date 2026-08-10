"""Atomic local persistence for Energy Meter."""

import json
import os
import tempfile


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except (IOError, OSError, ValueError):
        return default


def atomic_json(path, value):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.energy-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class JsonStore:
    def __init__(self, directory, max_records=0):
        self.state_path = os.path.join(directory, 'state.json')
        self.history_path = os.path.join(directory, 'history.json')
        self.max_records = max(0, int(max_records or 0))

    def states(self):
        value = read_json(self.state_path, {})
        return value if isinstance(value, dict) else {}

    def history(self):
        value = read_json(self.history_path, [])
        return value if isinstance(value, list) else []

    def save_state(self, states):
        atomic_json(self.state_path, states)

    def append(self, records):
        history = self.history()
        history.extend(records)
        if self.max_records:
            history = history[-self.max_records:]
        atomic_json(self.history_path, history)
        return history

    def reset_meter(self, meter_id):
        states = self.states()
        states.pop(meter_id, None)
        self.save_state(states)
