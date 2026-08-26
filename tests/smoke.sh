#!/bin/sh
# Smoke test, který nepotřebuje Claude Code ani API klíč.
# Ověřuje tři věci: launcher najde interpret, každý hook je fail-open,
# a guard, který má blokovat, opravdu blokuje.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FAILED=0

ok()   { printf '  ✔ %s\n' "$1"; }
fail() { printf '  ✘ %s\n' "$1"; FAILED=$((FAILED + 1)); }

echo "== 1. launcher najde Python =="
if printf '{}' | sh "$ROOT/bin/hook.sh" context_size_warning.py >/dev/null 2>&1; then
    ok "bin/hook.sh rozřešil interpret a spustil skript"
else
    fail "bin/hook.sh nespustil skript (exit $?)"
fi

echo "== 2. každý hook je fail-open na prázdném vstupu =="
for script in "$ROOT"/scripts/*.py; do
    name=$(basename "$script")
    case "$name" in hook_io.py|read_skeleton.py|write_intent.py) continue ;; esac
    printf '{}' | sh "$ROOT/bin/hook.sh" "$name" >/dev/null 2>&1
    code=$?
    if [ "$code" -eq 0 ]; then
        ok "$name (exit 0)"
    else
        fail "$name skončil s exit $code — na nesmyslném vstupu musí být fail-open"
    fi
done

echo "== 3. guard opravdu blokuje =="
deny=$(printf '{"hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","description":"x","prompt":"y"}}' \
    | sh "$ROOT/bin/hook.sh" guard_agent_model_routing.py 2>/dev/null)
if printf '%s' "$deny" | grep -q '"permissionDecision": *"deny"'; then
    ok "Agent bez model -> deny"
else
    fail "Agent bez model NEBYL zablokován"
fi

allow=$(printf '{"hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"sonnet","description":"x","prompt":"y"}}' \
    | sh "$ROOT/bin/hook.sh" guard_agent_model_routing.py 2>/dev/null)
if printf '%s' "$allow" | grep -q '"permissionDecision": *"deny"'; then
    fail "Agent s explicitním model byl zablokován — falešně pozitivní guard"
else
    ok "Agent s model=sonnet -> projde"
fi

echo "== 4. hooks.json ukazuje jen na existující skripty =="
# Pozor na escapované uvozovky uvnitř JSONu: v souboru stojí
#   sh \"${CLAUDE_PLUGIN_ROOT}/bin/hook.sh\" guard_x.py
NAMES=$(grep -o 'hook\.sh[^ ]* [a-z_]*\.py' "$ROOT/hooks/hooks.json"     | awk '{print $2}' | sort -u)
if [ -z "$NAMES" ]; then
    fail "z hooks.json se nepodařilo vytáhnout ANI JEDNO jméno skriptu — test by jinak tiše prošel naprázdno"
else
    for name in $NAMES; do
        if [ -f "$ROOT/scripts/$name" ]; then
            ok "$name existuje"
        else
            fail "hooks.json volá $name, ale scripts/$name neexistuje"
        fi
    done
fi

echo
if [ "$FAILED" -eq 0 ]; then
    echo "VŠE PROŠLO"
    exit 0
fi
echo "SELHALO: $FAILED"
exit 1
