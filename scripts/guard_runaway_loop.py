#!/usr/bin/env python3
"""PreToolUse guard: zastavi RUNAWAY SMYCKU - tentyz tool call s tymiz parametry
poslany N-krat po sobe (napr. Read stejnych radku 48x dokola).

PROC (root cause z 2026-05-31):
Model muze degenerovat do smycky, kde emituje identicky tool call porad dokola
(stejny nazev toolu + stejny vstup), bez jakehokoliv pokroku. Pro Read/Grep/Bash
to neni destruktivni, jen to pali kontext, cas a penize a vypada to porouchane
(protoze to porouchane je).

JAK: cteme transcript. Aktualni call jeste v transcriptu NENI (PreToolUse fire
pred zapisem). Jdeme odzadu, skladame plochou
sekvenci predchozich tool_use bloku a pocitame, kolik poslednich za sebou ma
STEJNY podpis (nazev + kanonicky JSON vstupu) jako prave prichozi call.
tool_result (user) bloky preskakujeme - to je normalni mezikrok. Skutecna lidska
zprava (user text bez toolu) smycku resetuje = konec poctu.

Kdyz uz N-1 identickych callu predchazelo, tenhle by byl N-ty -> deny. Model
dostane error a musi zmenit pristup, ne strilet ten samy call podotracet.

THRESHOLD volba: 4 predchozi identicke -> 5. blokneme. 5 identickych callu za
sebou bez jakehokoliv mezikroku neni nikdy legitimni (re-run testu ma mezi sebou
Edit, re-read se dela jednou). Fail-open: jakakoliv chyba -> exit 0 = povol.
"""

import json
import sys
from hook_io import read_payload

# Kolik IDENTICKYCH predchozich callu staci, aby tenhle (dalsi v rade) byl deny.
MAX_REPEATS = 4


def signature(tool_name, tool_input):
    """Kanonicky podpis tool callu: nazev + setrideny JSON vstupu."""
    try:
        payload = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        payload = repr(tool_input)
    return f"{tool_name}\x00{payload}"


def trailing_identical_count(transcript_path, target_sig):
    """Pocet poslednich tool_use callu v rade, ktere maji podpis == target_sig.

    Jdeme odzadu plochou sekvenci tool_use bloku. Prvni neshoda = konec rady.
    tool_result preskakujeme; lidska textova zprava radu ukonci.
    """
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return 0

    streak = 0
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = evt.get("type")
        content = evt.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue

        if etype == "user":
            # tool_result = normalni mezikrok mezi cally -> nepocita se, pokracuj.
            # Skutecny user text (bez tool_result) = lidsky zasah -> konec rady.
            has_result = any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
            if has_result:
                continue
            return streak  # cerstvy lidsky vstup, smycka zacina znovu

        if etype != "assistant":
            continue

        tool_uses = [
            b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not tool_uses:
            continue  # cisty text assistanta mezi cally radu nelameme

        # bloky v ramci jedne zpravy bereme taky odzadu (paralelni batch)
        for b in reversed(tool_uses):
            if signature(b.get("name", ""), b.get("input", {})) == target_sig:
                streak += 1
            else:
                return streak  # prvni neshoda -> konec rady
    return streak


def main():
    data = read_payload()  # UTF-8 stdin + fail-open, viz hook_io.py

    tool_name = data.get("tool_name", "")
    if not tool_name:
        sys.exit(0)

    target_sig = signature(tool_name, data.get("tool_input", {}))
    streak = trailing_identical_count(data.get("transcript_path", ""), target_sig)

    if streak >= MAX_REPEATS:
        reason = (
            f"RUNAWAY SMYCKA - zastaveno. Posledni {streak} tool cally byly "
            f"IDENTICKE ({tool_name} se stejnymi parametry) a tenhle by byl dalsi "
            "v rade. To neni pokrok, to je zaseknuta smycka.\n\n"
            "STOP. NEopakuj ten samy call. Misto toho:\n"
            "1) Pojmenuj, co jsi se snazil zjistit/udelat tim opakovanym callem.\n"
            "2) Mas vysledek uz prvniho volani - pouzij ho, nevolej znovu.\n"
            "3) Kdyz vysledek nestaci, ZMEN pristup (jiny tool, jine parametry, "
            "jiny rozsah) nebo se zeptej uzivatele."
        )
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(out))
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
