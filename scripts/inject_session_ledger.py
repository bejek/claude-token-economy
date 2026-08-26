"""SessionStart hook: injektuje generický `<cwd>/docs/session-ledger.md`, když je v něm rozdělaný task.

PROČ (2026-08-16, po incidentu „Deploy go na 220k"): kontext se platí každým callem, takže
netriviální task má být rozdělitelný `/clear`-em kdykoliv po cestě. To jde jen tehdy, když stav
NEŽIJE v kontextu, ale na disku — a čerstvá session ho dostane zadarmo, bez „kde jsme skončili".
Hook funguje pro JAKÝKOLIV task v JAKÉMKOLIV repu. Pravidla zápisu: CLAUDE.md „Token ekonomie".

Záměrně samostatný a malý skript: injektuje jen ledger, nic jiného.

Mechanika:
  * `STAV:` = první segment řádku rozhoduje (`uzavřeno` / `hotovo` → mlčí, jako by nebyl),
  * cap 4 000 znaků useknutím od konce (⇒ pořadí sekcí STAV/NEXT/BLOKERY/ROZHODNUTÍ/NÁLEZY je šablona),
  * mtime > 48 h → injektuje s varováním (zamrzlý ledger ≠ živý task),
  * chybějící / prázdný / uzavřený → ŽÁDNÝ výstup (cedule „nic neběží").

Šablona (drž pořadí, viz cap):
  # TASK <název> — <repo/větev>
  STAV: běží | čeká-na-rozhodnutí | uzavřeno — <poznámka až za pomlčkou>
  NEXT: <jediná nejbližší akce>
  HOTOVO: <odrážky, jen co příští session NESMÍ dělat znovu — commity SHA, soubory>
  BLOKERY: <co brzdí / co příští session NESMÍ> (prázdné = „žádné")
  ROZHODNUTÍ: <co čeká na člověka> (prázdné = „nic nečeká")
  NÁLEZY: <viděl jsem a nespravil — pointer, ne próza>
  ŽURNÁL: docs/journal/YYYY-MM-DD-<téma>.md   (nebo `—` = žádný trvalý nález)

DVA SOUBORY, DVĚ PRÁCE (2026-08-22). Tenhle ledger je ŠTÍTEK: gitignorovaný
(`~/.gitignore_global` ř. 3), přepisovaný, ≤ 3 000 znaků. Trvalé nálezy patří do
`docs/journal/YYYY-MM-DD-<téma>.md`, který je VERZOVANÝ a přežije checkout.
Předtím dělal ledger obojí a vyrostlo z něj 314 řádků / 23 kB —
neverzovaných (`git add -A` je mlčky přeskočí) a z 80 % neviditelných, protože
`text[:CAP]` drží ZAČÁTEK a zahazuje konec, tedy zrovna ty nejnovější zápisy.
Strop hlídá `guard_session_ledger.py` (PreToolUse deny + PostToolUse na heredoc);
FILE_CAP < CAP je invariant, který dělá „napsané, ale neviditelné" nemožným.

Fail-silent: chyba ⇒ žádný výstup, session startuje normálně.
"""

import json
import os
import sys
import time
from pathlib import Path

from hook_io import read_payload

CAP = 4000
STALE_H = 48
CLOSED = ("uzavřen", "uzavren", "hotovo", "done", "closed")


def is_closed(stav_line: str) -> bool:
    """Uzavřenost = PRVNÍ segment za `STAV:` (před ` — ` / ` - ` / `|` / `(`)."""
    body = stav_line.split(":", 1)[1].strip().lower() if ":" in stav_line else ""
    for sep in (" — ", " – ", " - ", "|", "(", "·"):
        body = body.split(sep, 1)[0]
    return any(body.strip().startswith(c) for c in CLOSED)


def build(cwd: str):
    ledger = Path(cwd) / "docs" / "session-ledger.md"
    try:
        text = ledger.read_text(encoding="utf-8").strip()
        age_h = (time.time() - ledger.stat().st_mtime) / 3600
    except OSError:
        return None
    if not text:
        return None
    stav = next((l for l in text.splitlines() if l.upper().startswith("STAV:")), "")
    if stav and is_closed(stav):
        return None
    if len(text) > CAP:
        text = (
            text[:CAP]
            + f"\n… [ŘEZ: ledger má {len(text)} zn., vejde se {CAP} — "
            "ořezává se KONEC, takže výš NEVIDÍŠ to nejnovější. Zkrať ho: "
            "minulost do `docs/journal/YYYY-MM-DD-<téma>.md` (verzovaný), "
            "hotové kroky do commit message. Strop souboru je 3 000 zn. "
            "a hlídá ho guard_session_ledger.py]"
        )
    if age_h > STALE_H:
        text = (
            f"⚠️ Na tenhle session-ledger nikdo nesáhl {age_h:.0f} h. Než z něj něco převezmeš, "
            "ověř proti gitu (`git log`, `git status`) — task mohl dojet jinde.\n\n"
            + text
        )
    return (
        "=== SESSION LEDGER: rozdělaný task (auto-injected z `docs/session-ledger.md`) ===\n"
        f"{text}\n"
        "=== KONEC session ledgeru — pokračuj od `NEXT:`. Git je pravda, ledger je záměr. "
        "Aktualizuj ho po každém uzavřeném kroku (ne až při /clear); hotový task → "
        "`STAV: uzavřeno`. Bez `STAV:` řádku se ledger po 48 h považuje za zamrzlý.\n"
        "Tohle je ŠTÍTEK, ne žurnál: ≤ 3 000 zn., žádné `##` sekce. Trvalý nález "
        "(měření, root cause, co bylo vyvráceno) → `docs/journal/YYYY-MM-DD-<téma>.md` "
        "a ukazatel na něj do pole `ŽURNÁL:` — ten soubor je VERZOVANÝ, ledger ne. ==="
    )


def main() -> int:
    data = read_payload()
    cwd = data.get("cwd") or os.getcwd()
    ctx = build(cwd)
    if not ctx:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": ctx,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


def selftest() -> int:
    cases = [
        ("STAV: běží — generace 1 uzavřena", False),
        ("STAV: uzavřeno — vše na prod", True),
        ("STAV: čeká-na-rozhodnutí (deploy go)", False),
        ("STAV: hotovo", True),
        ("STAV: code-complete | čeká deploy", False),
        ("stav: Uzavřeno", True),
    ]
    bad = [(s, e) for s, e in cases if is_closed(s) != e]
    print(
        f"selftest: {len(cases) - len(bad)}/{len(cases)} OK"
        + (f" — FAIL: {bad}" if bad else "")
    )
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
