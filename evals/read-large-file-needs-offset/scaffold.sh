#!/bin/sh
# Vyrobí soubor nad prahem guardu (THRESHOLD_MAIN = 6000 tokenů, odhad znaky/1,85),
# ale POD vestavěným limitem Readu (2000 řádků) — jinak by "use offset" napsal i
# holý Claude Code a case by plugin od baseline nerozlišil. Funkce mají DLOUHÁ těla
# schválně: guard nabídne kostru jen tehdy, když je ≤ 25 % originálu (MAX_SKELETON_RATIO),
# a modul z 400 jednořádkových funkcí se nezkomprimuje. 30 funkcí × 40 řádků
# ≈ 1 200 řádků ≈ 9 000 tokenů, kostra ~ 15 %.
# Hledaná funkce je schválně až na konci, aby ji nešlo trefit prvními řádky.
set -e
mkdir -p src
{
    echo '"""Velký modul — fixture pro eval token-economy pluginu."""'
    echo
    i=0
    while [ "$i" -lt 30 ]; do
        printf 'def pomocna_%s(hodnota):
    """Pomocná funkce číslo %s, pro eval nezajímavá."""
' "$i" "$i"
        j=0
        while [ "$j" -lt 36 ]; do
            printf '    v%s = hodnota * %s + %s
' "$j" "$j" "$i"
            j=$((j + 1))
        done
        printf '    return v0 + v35


'
        i=$((i + 1))
    done
    printf 'def spocitej_dan(zaklad, sazba_procent):
    """Spočítá daň ze základu. Sazba se zadává v procentech."""
    if zaklad < 0:
        raise ValueError("zaklad nesmi byt zaporny")
    return round(zaklad * sazba_procent / 100.0, 2)
'
} > src/big_module.py
