"""
PostCompact hook — po kompresi konverzace injektuje posledních N zpráv jako kontext.
Spouští se automaticky přes Claude Code hook PostCompact.
"""

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

N_MESSAGES = 10  # kolik posledních zpráv chceme vrátit
MAX_CHARS = 400  # max délka jedné zprávy (zkrácení)


def get_project_slug(cwd: str) -> str:
    r"""Převede cestu jako D:\Projects\csk na slug d--Projects-csk"""
    p = Path(cwd)
    drive = p.drive  # např. 'D:'
    rest = str(p)[len(drive):]  # např. '\Projects\csk'
    drive_letter = drive[0].lower()
    rest_clean = rest.replace("\\", "-").replace("/", "-").strip("-")
    return f"{drive_letter}--{rest_clean}"


def extract_text(content) -> str:
    """Vytáhne čistý text z content pole (může být string nebo list bloků)"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return str(content)


def main():
    cwd = os.getcwd()
    project_slug = get_project_slug(cwd)
    claude_dir = Path.home() / ".claude" / "projects" / project_slug

    if not claude_dir.exists():
        # Nic nevypisujeme — hook selže tiše
        sys.exit(0)

    # Nejnovější JSONL soubor v projektu
    jsonl_files = list(claude_dir.glob("*.jsonl"))
    if not jsonl_files:
        sys.exit(0)

    latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)

    # Přečteme posledních ~100 řádků a filtrujeme human/assistant zprávy
    messages = []
    try:
        with open(latest, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        sys.exit(0)

    for line in reversed(lines[-200:]):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = entry.get("type")
        if msg_type not in ("human", "assistant"):
            continue

        content = entry.get("message", {}).get("content", "")
        text = extract_text(content).strip()
        if not text:
            continue

        timestamp = entry.get("timestamp", "")[:16].replace("T", " ")  # '2026-04-12 14:37'
        messages.insert(0, (msg_type, timestamp, text))

        if len(messages) >= N_MESSAGES:
            break

    if not messages:
        sys.exit(0)

    # Výstup — injektuje se jako kontext pro Claude
    print("=== KONTEXT: POSLEDNÍCH ZPRÁV PŘED KOMPRESÍ ===")
    for msg_type, timestamp, text in messages:
        role = "UŽIVATEL" if msg_type == "human" else "CLAUDE"
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "…"
        print(f"[{timestamp}] {role}: {text}")
    print("=== KONEC KONTEXTU ===")


if __name__ == "__main__":
    main()
