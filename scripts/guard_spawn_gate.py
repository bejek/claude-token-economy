#!/usr/bin/env python3
"""PreToolUse guard: nespawnuj vlnu, kterou uz nedokazes dosedet.

PROC EXISTUJE (nalez 08-08): context_size_warning.py je `UserPromptSubmit` hook
-- meri VYHRADNE ve chvili, kdy uzivatel odesle prompt. Behem vlny jede
orchestrator dvacet turnu sam (spawn -> poll -> report -> merge), takze mezi
dvema uzivatelskymi prompty je hook slepy: posledni zmerenych 180k, dalsi hlaseni
uz zni 280k. Checkpoint STOP tim systematicky trefuje LET, ne pristani --
ctyri revieweri ve vzduchu, nula pristalych.

A tady vznika ta draha past: uzivatel nechce zabit rozdelanou praci subagentu, tak
ceka na drain a hned v te same session odjede endgame. Ucetnictvi ale rika opak:
  * drain 4 reportu (25 r. dle par. 5.2) = ~2k tokenu, tj. NIC,
  * endgame (merge/gate/diffy/cleanup) = 50+ callu hlavni smycky, kazdy
    preplaci CELY kontext -- to je ta cesta z 280k na 350k.
Subagenti svych 150-200k utratili tak jako tak; `/clear` je nevraci.

Reseni neni prisnejsi STOP, ale posunout branu k NAJEZDU:

  ctx < 200k            -> ticho
  200k <= ctx < 230k    -> DENY, dokud spawn nenese marker MARKER (viz nize).
                           Pasmo existuje proto, ze samotny tvrdy strop nestaci:
                           varka spawnuta na 220k skonci klidne na 300k+.
                           Marker = artefakt vedome volby, stejna filozofie jako
                           `model` v guard_agent_model_routing.py.
  ctx >= 230k           -> tvrdy DENY, marker nepomaha. Nad prahem se uz nic
                           nerozjizdi: dojed rozdelane, stav do ledgeru/handoffu,
                           ZASTAV a cekej na `/clear`.

VYJIMKA -- UZAVRENI SESSION (nalez 08-08): brana strelila do `/end`.
Ritual je pritom pravy opak toho, co gate hlida -- dva sonnet subagenti, kteri
zapisi memory a docs a vrati dva reporty; do hlavniho kontextu spadne par tisic
tokenu a session KONCI. Zablokovat ho znamena vyhodit handoff a memory presne
v okamziku, kdy jsou nejdrazsi na znovuzisk (zadna dalsi generace uz je nema
odkud vzit). Uzavrit session chce uzivatel VZDYCKY, levne, na jakemkoliv kontextu.
Proto: zavira-li se v tehle generaci session, guard mlci uplne -- a to na zbytek
generace, ne jen na ten jeden turn. `/end` totiz neni turn, ale rezim: uzivatel
k nemu dopisuje "a jeste dodelej X" a chce to dotahnout v TEHLE session. Cte se
to z transcriptu (`session_closing`, reset na `/clear`), ne z markeru v promptu.

DRUHY POKUS (nalez 08-08, artemis): prvni verze exempce NEFUNGOVALA a session
shorela na 277k -- guard hledal `<command-name>/end</command-name>`, jenze ten
u `/end` nikdy nevznikne (`/end` je SKILL, ne built-in command, a uzivatel ho
navic casto posila vetou "az budes hotovej, udelej /end"). Nasledek je presne
opacny, nez guard chce: nejdrazsi model dojel mechaniku rituálu RUCNE. Detekce
proto stoji na trech signalech, viz session_closing() v hook_io.py.

Hlida `Agent` i `Workflow` -- Workflow spawne desitky agentu, na strop kontextu
dopada nejhur ze vseho.

Guard je GLOBALNI, orchestrace byva projektova. Hlaska proto nesmi
predpokladat bezici vlnu -- v obycejne session zadne "reporty bezicich agentu"
ani checkpoint ping nejsou a instrukce k nim jen matou. Orchestracni kroky jsou
v hlasce oznacene jako podminene; Telegram ping tenhle hook neposila vubec
(je projektovy, `scripts/wave-checkpoint-ping.ps1`).

Chyby / chybejici transcript -> fail-open (exit 0). Guard brani nehodam, ne praci.
"""

import json
import sys
from hook_io import context_tokens, read_payload, session_closing

BAND, HARD = (
    200_000,
    230_000,
)  # 09-22: Opus 5.5 x1,3 (drive 150k/175k, 08-16 srovnano s kontext-watch)
MARKER = "[SPAWN-GATE-OK]"
GATED_TOOLS = {"Agent", "Workflow"}


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


def main():
    data = read_payload()  # UTF-8 stdin + fail-open, viz hook_io.py

    if data.get("tool_name") not in GATED_TOOLS:
        sys.exit(0)

    transcript = data.get("transcript_path")
    ctx = context_tokens(transcript)
    if ctx < BAND:
        sys.exit(0)

    # Uzavreni session se negatuje NIKDY -- levny spawn, po kterem session konci.
    # Plati na zbytek generace, ne jen na jeden turn: k `/end` uzivatel dopisuje
    # "a jeste dodelej X" a chce to dotahnout tady. Tri signaly, protoze
    # `<command-name>` u skillu nevznikne -- viz session_closing() v hook_io.py.
    if session_closing(transcript):
        sys.exit(0)

    k = ctx // 1000

    if ctx >= HARD:
        deny(
            f"SPAWN GATE: kontext ~{k}k >= {HARD // 1000}k -- nad prahem se uz nic "
            "nerozjizdi. NESPAWNUJ a misto toho: (1) dojed rozdelanou atomickou "
            "operaci -- nikdy neutikej uprostred merge/gate, (2) stav + NALEZY hned "
            "zapis tam, odkud je vezme dalsi generace (ledger/handoff/memory), "
            "(3) NAVRHNI uživateli `/clear` a UKONCI TURN. Endgame je plne "
            "rekonstruovatelny z gitu a zapisu -- patri do cerstve generace, kde "
            "stoji zlomek. Zadna 'jeste jedna rychla vec'. Bezi-li vlna subagentu, "
            "napred ingestni jejich reporty a posli checkpoint ping "
            "(ORCHESTRATION.md par. 5.8) -- jinak tyhle dva kroky ignoruj. "
            "UZAVRENI SESSION je z brany VYNATE: `/end` spustis kdykoliv "
            "a na jakemkoliv kontextu."
        )

    tool_input = data.get("tool_input")
    blob = json.dumps(tool_input, ensure_ascii=False) if tool_input else ""
    if MARKER in blob:
        sys.exit(0)  # vedome potvrzeno -> povol

    deny(
        f"SPAWN GATE: kontext ~{k}k je v pasmu {BAND // 1000}-{HARD // 1000}k = "
        "TOHLE JE POSLEDNI VARKA, ktera se do generace vejde. Spawni jen to, co "
        "dokazes dosedet vcetne endgame (~15-25k na task: report, merge, gate, "
        "cleanup). Nevejde-li se to, je levnejsi navrhnout `/clear` TED a spawnout "
        f"v cerstve generaci. Kdyz to dosedis, zavolej znovu s '{MARKER}' "
        "v promptu (u Workflow kdekoliv ve scriptu) -- at je to vedoma volba, "
        "ne setrvacnost. Viz ORCHESTRATION.md par. 5.8."
    )


if __name__ == "__main__":
    main()
