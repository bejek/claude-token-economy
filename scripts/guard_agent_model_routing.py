#!/usr/bin/env python3
"""PreToolUse guard: brani tichemu inheritu MODELU u ad-hoc Agent spawnu.

Sesterske dilo guard_workflow_model_routing.py, stejna filozofie. Ad-hoc Agent
spawn (general-purpose / Explore / Plan) bez `model` tise zdedi main-loop model
-- to znamena, ze "levny pruzkumny agent" jede na modelu session (dnes
opus[1m], drive fable5[1m]) s xhigh effortem. Mereno 07-18: sonnet = 4 % utraty,
opus+fable = 80 %. Presne tenhle tichy inherit je duvod.

Pravidlo:
  - BUILTIN genericke typy (general-purpose, Explore, Plan, prazdny=default)
    BEZ `model` -> DENY s napovedou routingu. Vedomy inherit se povoli
    explicitnim model: "fable"/"opus" (= artefakt vedome volby).
  - subagent_type "fork" (od CC 2.1.232 defaultne zapnuty) -> DENY, dokud
    `description` nezacina "fork:". Fork `model` parametr IGNORUJE (vzdy jede
    na modelu rodice), takze artefaktem vedome volby nemuze byt model -- je jim
    prefix v description. Duvod: fork dedi CELY kontext session, takze kazdy
    jeho turn nese 200k+ tokenu navic proti subagentovi s tririadkovym promptem.
  - Custom agent typy (.claude/agents/*.md) maji model+effort ve frontmatter
    -> exit 0, routing je v definici (ORCHESTRATION.md par. 9).

Chyby / nezname tvary -> fail-open (exit 0). Guard brani nehodam, ne praci.
POZN: Agent tool NEMA per-call `effort` -- ad-hoc spawn dedi session effort
(dnes xhigh). Trvale role proto fixuj pres frontmatter definici, ne ad-hoc.
"""

import json
import sys
from hook_io import read_payload

# Genericke builtin typy bez frontmatter definice -> tichy inherit hrozi.
GENERIC_TYPES = {"general-purpose", "explore", "plan", ""}

# Fork nema routing (model se ignoruje) -> artefaktem vedome volby je prefix.
FORK_OPT_IN = "fork:"

FORK_HINT = (
    "Fork NENI levny subagent. Dedi CELY kontext session vcetne prompt cache, "
    "takze jede na modelu rodice (dnes opus[1m]) a kazdy jeho turn tahne cely "
    "dosavadni prubeh. Cache-read to zlevnuje ~10x proti plnemu inputu, ale "
    "porad je to radove vic nez subagent, ktery dostane tririadkovy prompt.\n"
    "KDY MA FORK SMYSL: (a) ukol potrebuje CELOU konverzaci a prevypraveni by "
    "bylo ztratove nebo delsi nez ten ukol; (b) hlucny tool output ma zustat "
    "mimo hlavni kontext, ale agent musi rozumet vsemu, co predchazelo; "
    "(c) paralelni vetveni tehoz stavu (3 varianty ze stejneho mista).\n"
    "KDY NE: mechanika, logy, git, grep, testy, docs, exploration -- tam je "
    "spravna odpoved Agent(subagent_type='general-purpose', model='sonnet') "
    "se scopovanym promptem, ne fork.\n"
    "Kdyz fork opravdu chces, zavolej Agent znovu se stejnym promptem a "
    "`description` zacinajici 'fork:' (napr. 'fork: post-mortem vlny'). "
    "`model` u forku neposilej, harness ho zahodi."
)

ROUTING_HINT = (
    "PORADI+CENA (MTok in/out): fable $10/$50 (STROP, 2x opus) > opus $5/$25 "
    "(DEFAULT) > sonnet $3/$15 > haiku $1/$5. Fable NENI levna varianta a NENI "
    "sonnet -- je to nejdrazsi model, sahej po nem vedome.\n"
    "Default routing: mechanika/exploration/logy/testy/docs/git = model:'sonnet' "
    "(pripadne 'haiku' na trivialni grunt). Existuje spec/design doc/handoff -> "
    "model:'opus' (tezke je to UDELAT). Az kdyz tvoris pravidlo, jde o JOINT "
    "rozhodnuti nebo o ireverzibilni krok s realnymi penezi -> model:'fable' "
    "-- EXPLICITNE, at je inherit vedomy. "
    "Pointa neni zakazat drahe, ale zvolit VEDOME (sonnet = 4 % utraty, "
    "opus+fable = 80 %, mereno 07-18). Effort per-call u Agent NEexistuje -- "
    "dedi se session effort; trvale role -> frontmatter .claude/agents/*.md."
)


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def main():
    data = read_payload()  # UTF-8 stdin + fail-open, viz hook_io.py

    if data.get("tool_name") != "Agent":
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        sys.exit(0)

    subagent_type = str(tool_input.get("subagent_type", "") or "").strip().lower()

    if subagent_type == "fork":
        description = str(tool_input.get("description", "") or "").strip().lower()
        if description.startswith(FORK_OPT_IN):
            sys.exit(0)  # vedoma volba -> povol
        deny(
            "Agent spawn typu 'fork' bez opt-in prefixu v `description`.\n" + FORK_HINT
        )

    if subagent_type not in GENERIC_TYPES:
        sys.exit(0)  # custom agent -> model/effort resi frontmatter definice

    if tool_input.get("model"):
        sys.exit(0)  # model zvolen vedome -> povol

    shown_type = subagent_type or "general-purpose (default)"
    deny(
        "Agent spawn typu '" + shown_type + "' BEZ `model` parametru -> tichy "
        "inherit main-loop modelu (Fable5/Opus + session effort). Zvol model "
        "VEDOME a zavolej Agent znovu se stejnym promptem + `model` parametrem.\n"
        + ROUTING_HINT
    )


if __name__ == "__main__":
    main()
