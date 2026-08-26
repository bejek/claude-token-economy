#!/bin/sh
# Token Economy Kit — spouštěč hooků.
#
# Proč vůbec existuje: hook v `hooks.json` je jeden příkaz, ale jméno Pythonu
# se liší podle systému. Na Windows je to `python`, na většině Linuxů a macOS
# jen `python3`, a na Windows navíc `python3` často ukazuje na 0bajtovou
# atrapu z Microsoft Storu, která žádný Python nespustí (skončí nenulovým
# exit kódem a nabídne instalaci). Proto se kandidáti neověřují přes
# `command -v`, ale tím, že se opravdu SPUSTÍ.
#
# Claude Code spouští hooky přes POSIX shell na všech platformách — na Windows
# přes MINGW (ověřeno `uname -s` = MINGW64_NT). Tenhle skript proto vystačí
# s čistým POSIX sh, žádný bash-ismus.
#
# Použití z hooks.json:
#   sh "${CLAUDE_PLUGIN_ROOT}/bin/hook.sh" guard_runaway_loop.py
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd) || exit 0
SCRIPT_NAME=${1:-}
[ -n "$SCRIPT_NAME" ] || exit 0
shift
SCRIPT="$ROOT/scripts/$SCRIPT_NAME"
[ -f "$SCRIPT" ] || exit 0

# Ověří, že kandidát je skutečný Python >= 3.8, ne atrapa ani python2.
py_works() {
    [ -n "${1:-}" ] || return 1
    "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" \
        >/dev/null 2>&1
}

# Výsledek detekce se cachuje, aby se při každém tool callu nespouštěly
# až tři interpretery navíc. Cache se sama zahodí, jakmile přestane platit.
CACHE_DIR=${TMPDIR:-/tmp}
CACHE="$CACHE_DIR/.token-economy-python"

PY=""
if [ -f "$CACHE" ]; then
    PY=$(cat "$CACHE" 2>/dev/null || printf '')
    py_works "$PY" || PY=""
fi

if [ -z "$PY" ]; then
    # Pořadí není libovolné: `python` první, protože na Windows je to ten
    # skutečný interpret, zatímco `python3` tam bývá atrapa. Na Linuxu, kde
    # `python` může být ještě python2, ho odmítne kontrola verze a přijde
    # na řadu `python3`.
    for candidate in python python3 py; do
        if py_works "$candidate"; then
            PY=$candidate
            printf '%s' "$PY" > "$CACHE" 2>/dev/null || :
            break
        fi
    done
fi

# Fail-open: bez Pythonu se hook tiše přeskočí. Guard, který nejde spustit,
# nesmí zablokovat práci — to je stejná zásada jako uvnitř samotných skriptů.
[ -n "$PY" ] || exit 0

exec "$PY" "$SCRIPT" "$@"
