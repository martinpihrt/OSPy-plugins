"""Persistent backup-state helpers for the OSPy package Backup plug-in."""

import os


def latest_backup(data_dir):
    """Return metadata for the newest plug-in backup ZIP on disk."""
    if not data_dir or not os.path.isdir(data_dir):
        return None
    candidates = []
    for filename in os.listdir(data_dir):
        path = os.path.join(data_dir, filename)
        if (not os.path.isfile(path) or
                not filename.lower().endswith('.zip') or
                'pluginsbackup' not in filename.lower()):
            continue
        candidates.append((os.path.getmtime(path), filename, os.path.getsize(path)))
    if not candidates:
        return None
    modified, filename, size = max(candidates, key=lambda item: item[0])
    return {'modified': modified, 'filename': filename, 'size': size}
