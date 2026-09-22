"""Kontext-watch hook (UserPromptSubmit + PostToolUse): hlídá velikost kontextu.

PROC EXISTUJE: Claude svuj vlastni kontext NEVIDI — nema zadny zivy citac.
Uzivatel ho ma ve status line, model ne. Bez tohohle hooku model nikdy sam
nenavrhne `/clear`, protoze nepozna, ze je cas.

PROC TO STOJI ZA TO (mereno 2026-07-25, 652 session):
  session s peakem >300k tok = median $23,24
  session s peakem <150k tok = median  $0,87   -> 27x rozdil
  53,8 % celkovych nakladu je cache-read = kontext placeny znovu KAZDYM callem.
Detail: `feedback_token_economy` v memory.

TRI PRAHY (2026-08-16, po incidentu "Deploy go na 220k"; 2026-09-22 posunuto
x1,3 kvuli Opus 5.5 -- levnejsi cache read, viz README):
  230k  FINIS   -> jen model: dotahni rozdelany celek, neotvirej nove fronty,
                   ledger aktualni. (Nova prace = nova session.)
  280k  CLEAR   -> model + uzivatel: jen nezbytne; pockej na bezici subagenty,
                   zapis jejich vysledky do ledgeru, nabidni /clear.
                   STROP je 300k — deploy/vetsi endgame patri do nove session.
  325k  SELHANI -> protokol selhal; zapis, ping, STOP. Zadna "jeste jedna vec".

PROC DVA EVENTY: do 08-16 bezel jen na UserPromptSubmit, tj. fajrnul az kdyz
uzivatel neco napsal. Behem autonomniho behu (subagenti, endgame, deploy priprava)
mlcel — presne tam, kde byl potreba. PostToolUse ho slysi i uprostred behu.
Na PostToolUse je THROTTLE (state file per session): hlasi jen pri PREKROCENI
prahu (a nad 325k kazdych +25k), ne po kazdem callu.

Ground truth = `usage` posledniho assistant zaznamu v transcriptu
(cache_read + cache_creation + input) — viz hook_io.context_tokens.

Fail-silent: jakakoliv chyba => exit 0 bez vystupu. Hook nesmi shodit prompt.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

from hook_io import context_tokens, read_payload

T1, T2, T3 = 230_000, 280_000, 325_000  # FINIS / CLEAR / SELHANI (09-22: Opus 5.5 x1,3)
T3_STEP = 25_000  # nad T3 pripominej kazdych +25k

MSG = {
    T1: (
        "Kontext ~{k}k = FINIŠ. Dotáhni rozdělaný logický celek, NEOTVÍREJ nové "
        "fronty (nový task, další review kolo, deploy = nová session). Ledger "
        "(`docs/session-ledger.md`) drž aktuální — po každém "
        "uzavřeném kroku, ne až při clearu. Cíl: /clear kolem 260–280k."
    ),
    T2: (
        "Kontext ~{k}k = CLEAR. Už jen nezbytnost: (1) počkej na VŠECHNY běžící "
        "subagenty a jejich výsledky ZAPIŠ do ledgeru (v nové session je neopakujeme), "
        "(2) dokonči atomickou operaci (ne endgame — merge/deploy/50 callů patří do "
        "nové session), (3) NABÍDNI `/clear` a UKONČI TURN (čekáš na uživatele). "
        "STROP 300k. Nikdy nenabízej clear s agenty v letu."
    ),
    T3: (
        "Kontext ~{k}k = SELHÁNÍ PROTOKOLU (mělo se clearovat na 280k). Okamžitě: "
        "ledger + STOP. Žádná „ještě jedna rychlá věc“. Pokračování "
        "existuje jediné: `/clear` + „pokračuj“."
    ),
}


def _state_path(session_id: str) -> Path:
    d = Path(tempfile.gettempdir()) / "claude-ctx-watch"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{session_id or 'nosession'}.json"


def _level(ctx: int) -> int:
    """Monotonni 'uroven hlasky': 0 pod T1, 1 = T1, 2 = T2, 3+ = T3 po 25k krocich."""
    if ctx >= T3:
        return 3 + (ctx - T3) // T3_STEP
    if ctx >= T2:
        return 2
    if ctx >= T1:
        return 1
    return 0


def _should_emit(event: str, session_id: str, level: int) -> bool:
    """UserPromptSubmit hlasi vzdy (novy turn = pripomenuti se hodi).
    PostToolUse jen kdyz uroven STOUPLA od posledniho hlaseni."""
    if event != "PostToolUse":
        return True
    p = _state_path(session_id)
    try:
        last = json.loads(p.read_text(encoding="utf-8")).get("level", 0)
    except (OSError, ValueError):
        last = 0
    if level <= last:
        return False
    try:
        p.write_text(json.dumps({"level": level}), encoding="utf-8")
    except OSError:
        pass
    return True


def main() -> int:
    data = read_payload()  # UTF-8 stdin + fail-open, viz hook_io.py
    event = data.get("hook_event_name") or "UserPromptSubmit"
    ctx = context_tokens(data.get("transcript_path"))  # sdilene s guard_spawn_gate

    level = _level(ctx)
    if not level:
        return 0
    if not _should_emit(event, data.get("session_id", ""), level):
        return 0

    tier = T3 if level >= 3 else (T2 if level == 2 else T1)
    text = MSG[tier].format(k=ctx // 1000)
    out = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": f"[kontext-watch] {text}",
        }
    }
    # Uzivateli to ukaz az od CLEAR prahu — FINIS je jen pro model,
    # aby mu status line necvakala hlaskou, kterou uz sam vidi.
    if tier >= T2:
        out["systemMessage"] = f"⚠️ Kontext ~{ctx // 1000}k tokenů — čas na /clear" + (
            " (SELHÁNÍ PROTOKOLU)" if tier >= T3 else ""
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-silent: hook nikdy neshodí prompt
