#!/usr/bin/env python3
"""Generate the README plug-in catalog from official plug-in manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"
README = ROOT / "README.md"
START_MARKER = "<!-- plugin-table:start -->"
END_MARKER = "<!-- plugin-table:end -->"
LEGACY_HEADING = "Available plugins:"


def _clean_cell(value: object, field: str, manifest: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{manifest}: missing non-empty {field!r}")
    return " ".join(value.split()).replace("|", r"\|")


def load_plugins() -> list[dict[str, str]]:
    plugins: list[dict[str, str]] = []
    for manifest in sorted(PLUGINS_DIR.glob("*/plugin.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        plugins.append(
            {
                "directory": manifest.parent.name,
                "name": _clean_cell(data.get("name"), "name", manifest),
                "version": _clean_cell(data.get("version"), "version", manifest),
                "description": _clean_cell(
                    data.get("description"), "description", manifest
                ),
            }
        )

    if not plugins:
        raise ValueError(f"No plug-in manifests found under {PLUGINS_DIR}")

    plugins.sort(key=lambda item: (item["name"].casefold(), item["directory"]))
    return plugins


def render_table() -> str:
    lines = [
        START_MARKER,
        "| Plug-in | Version | Description |",
        "| --- | --- | --- |",
    ]
    for plugin in load_plugins():
        link = f"[**{plugin['name']}**](plugins/{plugin['directory']}/)"
        lines.append(
            f"| {link} | `{plugin['version']}` | {plugin['description']} |"
        )
    lines.append(END_MARKER)
    return "\n".join(lines)


def updated_readme(current: str) -> str:
    generated = render_table()
    if START_MARKER in current and END_MARKER in current:
        before, remainder = current.split(START_MARKER, 1)
        _, after = remainder.split(END_MARKER, 1)
        return before + generated + after

    if LEGACY_HEADING in current:
        before, _ = current.split(LEGACY_HEADING, 1)
        introduction = (
            "## Available plug-ins\n\n"
            "This table is generated from the `name`, `version` and `description` fields in every official `plugin.json`. Run `python tools/generate_plugin_table.py` after changing a manifest and `python tools/generate_plugin_table.py --check` to verify that the README is current.\n\n"
        )
        return before.rstrip() + "\n\n" + introduction + generated + "\n"

    raise ValueError(
        f"{README}: missing generated table markers and legacy heading"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when README.md does not contain the current generated table",
    )
    args = parser.parse_args()

    current = README.read_text(encoding="utf-8")
    expected = updated_readme(current)
    if args.check:
        if current != expected:
            print("README.md plug-in table is out of date.")
            return 1
        print(f"README.md plug-in table is current ({len(load_plugins())} plug-ins).")
        return 0

    if current == expected:
        print(f"README.md plug-in table is already current ({len(load_plugins())} plug-ins).")
        return 0

    README.write_text(expected, encoding="utf-8")
    print(f"Updated README.md with {len(load_plugins())} plug-ins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
