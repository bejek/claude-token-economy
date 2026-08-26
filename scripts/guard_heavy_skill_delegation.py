#!/usr/bin/env python3
"""PreToolUse guard: zakazuje natazeni ZERAVYCH skillu do hlavniho kontextu.

Problem (pozorovani z provozu 2026-07-30): skill `claude-api` je referencni
mega-dokument s jazykovymi podstromy (python/typescript/go/java/php/ruby/curl).
Kazde
`Skill(claude-api)` v hlavni session natahne ~300k tokenu do kontextu -- a
kontext platis KAZDYM dalsim API callem do konce session. Na Fable/Opus[1m]
session to je nejdrazsi jednotlivy omyl, ktery se da udelat jednim tool callem.
Dneska se to stalo 4x.

Pravidlo:
  - Skill z HEAVY_SKILLS v hlavnim kontextu -> DENY. Musi se delegovat na
    sonnet subagenta, ktery skill nacte do SVEHO kontextu a vrati jen odpoved
    (par set tokenu misto 300k, a nezustane to viset v historii).
  - Subagent, ktery skill legitimne cte, prochazi diky magic tokenu
    DELEGATED_TOKEN v `args` -- guard nema jiny spolehlivy zpusob, jak poznat,
    ze bezi uvnitr subagenta (hooky fajruji i tam).
  - Uzivatel muze vedome protlacit skill do hlavniho kontextu pres FORCE_TOKEN.

Chyby / nezname tvary -> fail-open (exit 0). Guard brani nehodam, ne praci.
"""

import json
import sys
from hook_io import read_payload

# Skilly, jejichz SKILL.md je tak velky, ze do hlavniho kontextu nepatri.
# Rozsiruj podle mereni, ne podle pocitu.
HEAVY_SKILLS = {
    "claude-api",
}

DELEGATED_TOKEN = "--delegated"  # posila subagent, ktery skill cist SMI
FORCE_TOKEN = "--force-main-context"  # vedomy override od uzivatele

DELEGATION_RECIPE = (
    "Misto toho spust roli `skill-reader` (~/.claude/agents/skill-reader.md, "
    "model+effort ma fixnute ve frontmatteru -- ZADNY `model` parametr nepridavej, "
    "prepsal bys definici) a precti si jen jeji vystup:\n"
    "  Agent(\n"
    "    subagent_type: 'skill-reader',\n"
    "    run_in_background: false,\n"
    '    prompt: "Skill: {skill}. Puvodni args: <puvodni args>. "\n'
    '            "Otazka: <jedna konkretni otazka>."\n'
    "  )\n"
    "Otazku formuluj konkretne (model id / cena / parametr / snippet), at ti "
    "nevrati esej. Kdyz odpoved nestaci, doptej se pres SendMessage -- agent ma "
    "skill porad ve svem kontextu, druhy spawn je zbytecny."
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

    if data.get("tool_name") != "Skill":
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        sys.exit(0)

    # Skill jmeno muze prijit s plugin prefixem (`plugin:skill`) -> ber posledni cast.
    raw_skill = str(tool_input.get("skill", "") or "").strip().lower()
    skill = raw_skill.split(":")[-1]
    if skill not in HEAVY_SKILLS:
        sys.exit(0)

    args = str(tool_input.get("args", "") or "").lower()
    if DELEGATED_TOKEN in args or FORCE_TOKEN in args:
        sys.exit(0)  # subagent nebo vedomy override -> povol

    deny(
        "STOP: skill '" + raw_skill + "' je referencni mega-dokument (~300k tokenu). "
        "Do hlavniho kontextu NEPATRI -- kontext se plati kazdym dalsim API callem, "
        "takze jedno nacteni prodrazi celou zbylou session.\n\n"
        + DELEGATION_RECIPE.format(skill=raw_skill)
        + "\n\nJestli fakt potrebujes cely skill v hlavnim kontextu, pridej do `args` "
        "token '" + FORCE_TOKEN + "' -- ale nejdriv se uzivatele zeptej, jestli chce "
        "zaplatit 300k tokenu."
    )


if __name__ == "__main__":
    main()
