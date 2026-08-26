#!/bin/sh
# Vyrobí soubor bezpečně nad prahem guardu (THRESHOLD_MAIN = 6000 tokenů,
# odhad znaky/1,85). 400 bloků ≈ 48 000 znaků ≈ 26 000 tokenů.
# Hledaná funkce je schválně až na konci, aby ji nešlo trefit prvními řádky.
set -e
mkdir -p src
{
    echo '"""Velký modul — fixture pro eval token-economy pluginu."""'
    echo
    i=0
    while [ "$i" -lt 400 ]; do
        printf 'def pomocna_%s(hodnota):\n    """Pomocná funkce číslo %s, pro eval nezajímavá."""\n    mezivysledek = hodnota * %s\n    return mezivysledek + %s\n\n\n' "$i" "$i" "$i" "$i"
        i=$((i + 1))
    done
    printf 'def spocitej_dan(zaklad, sazba_procent):\n    """Spočítá daň ze základu. Sazba se zadává v procentech."""\n    if zaklad < 0:\n        raise ValueError("zaklad nesmi byt zaporny")\n    return round(zaklad * sazba_procent / 100.0, 2)\n'
} > src/big_module.py
