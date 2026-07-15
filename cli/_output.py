"""Shared output formatting for the modkit CLI."""

import json
import os
import sys

JSON_FORMATS = {"json", "compact", "pretty"}


def format_json(data, fmt: str = "json") -> str:
    """Serialize CLI JSON output."""
    if fmt == "pretty":
        return json.dumps(data, indent=2, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def format_json_text(text: str, fmt: str = "json") -> str:
    """Normalize JSON text according to the CLI output format."""
    return format_json(json.loads(text), "pretty" if fmt == "pretty" else "json")


def output(data, fmt: str = "json"):
    """Format and print result data."""
    if isinstance(data, dict) and "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        sys.exit(1)

    if fmt in JSON_FORMATS:
        print(format_json(data, fmt))
    elif fmt == "table":
        _format_table(data)
    else:
        print(format_json(data))


def _format_table(data):
    """Pretty-print data as a table or key-value pairs."""
    if isinstance(data, dict):
        _print_dict(data)
    elif isinstance(data, list):
        if not data:
            print("No results.")
            return
        if isinstance(data[0], dict):
            _print_table(data)
        else:
            for item in data:
                print(item)
    else:
        print(data)


def _print_dict(d: dict):
    if not d:
        return
    max_key = max(len(str(k)) for k in d.keys())
    for k, v in d.items():
        val = str(v)
        if len(val) > 200:
            val = val[:200] + "..."
        print(f"  {k:<{max_key}}  {val}")


def _print_table(rows: list[dict]):
    if not rows:
        return

    skip = {"yaml_content", "source_code", "content", "yaml_path", "script_path"}
    all_keys = []
    for row in rows:
        for k in row:
            if k not in all_keys and k not in skip:
                all_keys.append(k)

    widths = {}
    for k in all_keys:
        w = len(k)
        for row in rows[:50]:
            val = str(row.get(k, ""))
            if len(val) > 60:
                val = val[:60]
            w = max(w, len(val))
        widths[k] = min(w, 60)

    total_width = sum(widths.values()) + (len(all_keys) - 1) * 3
    try:
        term_width = os.get_terminal_size().columns
    except OSError:
        term_width = 200

    if total_width > term_width and len(all_keys) > 3:
        for i, row in enumerate(rows):
            if i > 0:
                print()
            print(f"--- [{i + 1}/{len(rows)}] ---")
            _print_dict({k: row.get(k, "") for k in all_keys})
        return

    header = " | ".join(f"{k:<{widths[k]}}" for k in all_keys)
    print(header)
    print("-+-".join("-" * widths[k] for k in all_keys))

    for row in rows:
        parts = []
        for k in all_keys:
            val = str(row.get(k, ""))
            if len(val) > widths[k]:
                val = val[:widths[k] - 3] + "..."
            parts.append(f"{val:<{widths[k]}}")
        print(" | ".join(parts))

    print(f"\n({len(rows)} results)")
