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
        self.history_journal_path = os.path.join(directory, 'history.jsonl')
        self.max_records = max(0, int(max_records or 0))
        self._history_count = None

    def states(self):
        value = read_json(self.state_path, {})
        return value if isinstance(value, dict) else {}

    def history(self):
        legacy = read_json(self.history_path, [])
        result = legacy if isinstance(legacy, list) else []
        try:
            with open(self.history_journal_path, encoding='utf-8') as stream:
                for line in stream:
                    try:
                        value = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(value, dict):
                        result.append(value)
        except (IOError, OSError):
            pass
        self._history_count = len(result)
        return result

    def save_state(self, states):
        atomic_json(self.state_path, states)

    def append(self, records):
        if not records:
            return self.history()
        os.makedirs(os.path.dirname(self.history_journal_path), exist_ok=True)
        if self._history_count is None:
            self._history_count = len(self.history())
        with open(self.history_journal_path, 'a', encoding='utf-8') as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        self._history_count += len(records)
        if self.max_records and self._history_count > self.max_records:
            keep = self.max_records if self.max_records <= 100 else max(1, int(self.max_records * 0.9))
            history = self.history()[-keep:]
            self._rewrite_journal(history)
            return history
        return None

    def _rewrite_journal(self, records):
        directory = os.path.dirname(self.history_journal_path)
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='.energy-history-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                for record in records:
                    stream.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.history_journal_path)
            atomic_json(self.history_path, [])
            self._history_count = len(records)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def clear_history(self):
        """Remove recorded intervals without changing counter baselines."""
        atomic_json(self.history_path, [])
        self._rewrite_journal([])

    def reset_meter(self, meter_id):
        states = self.states()
        states.pop(meter_id, None)
        self.save_state(states)
