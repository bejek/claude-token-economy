#!/usr/bin/env python3
"""PreToolUse guard: brani tichemu inheritu MODELU i EFFORTU ve Workflow.

Workflow agent bez `model` tise zdedi main-loop model; bez `effort` tise zdedi
session effort. /effort max + Fable5 -> 106 agentu na MAX = 3.25M tokenu. Prave
tak vypada realny prusvih, proti kteremu tohle stoji.

Tri vrstvy obrany (vsechny pres deny+reason = "hlucny blocking reminder"):
  1. NAMED workflow ({name: ...}): guard NEVIDI do resolvnuteho scriptu, takze
     nemuze overit nic -> DENY. Tady se dela nejvic skody (SDK workflows casto
     nerouteji vubec). Postup pro odblokovani je v reasonu.
  2. Inline/scriptPath BEZ markeru `// MODEL-ROUTING:` -> DENY (chybi artefakt
     vedome volby modelu+effortu).
  3. Marker JE, ale ve scriptu neni realny `model:`/`effort:` param -> DENY
     (napsal jsi marker, ale stejne routujes vzduch). Vedomy inherit se povoli
     markerem `inherit-ok: <duvod>`.

Presence-check (bod 3) je zamerne: hleda `model:`/`effort:` kdekoli ve scriptu,
ne per-call. Per-call regex nad multi-line JS je krehky (false-positives ->
vypnuty guard). Tohle chyta hlavni hrich "zapomenuty effort" robustne.

Chyby / nezname tvary -> fail-open (exit 0). Guard ma branit nehodam, ne blokovat.
"""

import json
import os
import re
import sys
from hook_io import read_payload

MARKER = re.compile(r"MODEL[-_]ROUTING", re.IGNORECASE)
AGENT_CALL = re.compile(r"\bagent\s*\(")
MODEL_PARAM = re.compile(r"\bmodel\s*:", re.IGNORECASE)
EFFORT_PARAM = re.compile(r"\beffort\s*:", re.IGNORECASE)
INHERIT_OK = re.compile(r"inherit[-_ ]?ok", re.IGNORECASE)

# Spolecny zaklad ke kazde hlasce: co je spravna volba routingu.
ROUTING_HINT = (
    "PORADI+CENA (MTok in/out): fable $10/$50 (STROP, 2x opus) > opus $5/$25 "
    "(DEFAULT) > sonnet $3/$15 > haiku $1/$5. Fable NENI levna varianta a NENI "
    "sonnet -- je to nejdrazsi model. "
    "Default routing: mechanika/impl/review=sonnet+medium, trivialni grunt "
    "(websearch/fetch/vypis)=haiku+low, hloubka (adversarial/security/"
    "architektura/synthesis)=opus+high; fable az kdyz spec NEEXISTUJE a visi na "
    "tom realne penize. Per-agent: agent(prompt, "
    "{model:'sonnet', effort:'medium', ...}). Effort levels: low|medium|high|"
    "xhigh|max. Pointa neni zakazat drahe, ale zvolit VEDOME (ne tichy inherit)."
)


def load_script(tool_input):
    """Text scriptu k analyze (inline > scriptPath), nebo None = neinspekovatelne."""
    if tool_input.get("script"):
        return tool_input["script"]
    path = tool_input.get("scriptPath")
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
    return None


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

    if data.get("tool_name") != "Workflow":
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    script = load_script(tool_input)

    # ── Vrstva 1: named workflow -> guard je slepy -> DENY ──
    if script is None:
        if tool_input.get("name"):
            deny(
                "Workflow spusteno pres {name: '" + str(tool_input.get("name")) + "'} "
                "-> guard NEVIDI do resolvnuteho scriptu, takze nemuze overit routing "
                "modelu ANI effortu. Named/SDK workflows (napr. deep-research) casto "
                "nemaji zadny per-agent model/effort -> vsichni agenti tise zdedi tvuj "
                "main-loop model+effort (Fable5 + MAX = 106 agentu na MAX, 3.25M tokenu).\n"
                "Odblokovani: precti snapshot scriptu (workflows/scripts/<jmeno>-wf_*.js), "
                "pridej model: a effort: do agent callu, pridej na zacatek marker "
                "'// MODEL-ROUTING: ...' a spust pres inline `script` nebo `scriptPath` "
                "(ty guard vidi a zkontroluje). Vedomy blind-run: do markeru "
                "'inherit-ok: <duvod>'.\n" + ROUTING_HINT
            )
        sys.exit(0)  # neni name ani script -> nic ke kontrole

    # ── Inspekovatelny script (inline / scriptPath) ──
    if not AGENT_CALL.search(script):
        sys.exit(0)  # nespawnuje agenty -> nic k routovani

    # Vrstva 2: chybi marker vedome volby
    if not MARKER.search(script):
        deny(
            "Workflow spawnuje agenty bez `// MODEL-ROUTING:` markeru -> hrozi tichy "
            "inherit main-loop modelu I effortu u vsech agentu. Pridej na zacatek "
            "scriptu komentar s vedomou volbou, napr.:\n"
            "  // MODEL-ROUTING: impl+review=sonnet/medium, fetch=haiku/low, "
            "adversarial/synthesis=opus/high\n"
            "a odpovidajici model:+effort: do agent opts.\n" + ROUTING_HINT
        )

    # Vrstva 3: marker JE — vedomy inherit povolen escapem
    if INHERIT_OK.search(script):
        sys.exit(0)

    # ...jinak vyzaduj realny routing param (presence-check, ne per-call)
    missing = []
    if not MODEL_PARAM.search(script):
        missing.append("model:")
    if not EFFORT_PARAM.search(script):
        missing.append("effort:")
    if missing:
        deny(
            "Marker MODEL-ROUTING je, ale ve scriptu chybi realny routing: nenasel "
            "jsem `" + "` ani `".join(missing) + "` v zadnem agent callu. Model "
            "routovany bez effortu je presne ta past, co spalila 3.25M tokenu (Fable5 "
            "byl model, MAX byl ZDEDENY effort). Pridej chybejici param do agent opts, "
            "nebo pokud je inherit zamer, dej do markeru 'inherit-ok: <duvod>'.\n"
            + ROUTING_HINT
        )

    sys.exit(0)  # marker + model: + effort: pritomny -> povol


if __name__ == "__main__":
    main()
