#!/usr/bin/env python3
"""Soubor -> kostra s cisly radku. Nahrada za precteni celeho souboru.

PROC (mereni 2026-07-28, docs/specs/2026-07-28-b2-kostra-misto-shrnovace.md):
Kostra je 3-13 % originalu (median 524 tok na 1073 realnych souborech) a
vyrobi se za 1,5 ms. Puvodni navrh - shrnuti z Haiku - stal 33 s a 2 368 tok.

Cisla radku jsou stejne dulezita jako obsah: kostra bez nich neumozni cileny
Read a deny se meni v cistou ztratu. Vystup je ve wire formatu Readu
(`cislo\\tobsah`), aby ho model cetl stejne jako normalni Read.

Modul NEZNA hooky ani payloady - jen soubory. Testuje se bez site.
"""

import ast
import os
import re

# Namereny pomer znaku na token pro tenhle korpus (NE chars/4). C0 S0.1.
CHARS_PER_TOKEN = 1.85


def extract_py(src):
    """ast: importy, modulove UPPER_CASE konstanty, class/def signatury.

    -> [(cislo_radku, text)] nebo None pri syntax erroru / prazdnem vysledku.
    """
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError):
        return None
    lines = src.splitlines()
    out = []

    def sig(node, depth):
        raw = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        if raw.count("(") > raw.count(")"):
            raw += " ..."  # viceradkova signatura
        doc = ast.get_docstring(node)
        first = doc.strip().splitlines()[0] if doc else ""
        return "  " * depth + raw + (f"   # {first[:70]}" if first else "")

    def walk(body, depth):
        for node in body:
            if depth == 0 and isinstance(node, (ast.Import, ast.ImportFrom)):
                out.append((node.lineno, lines[node.lineno - 1].strip()))
            elif depth == 0 and isinstance(node, ast.Assign):
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    out.append((node.lineno, lines[node.lineno - 1].strip()[:100]))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((node.lineno, sig(node, depth)))
            elif isinstance(node, ast.ClassDef):
                out.append((node.lineno, sig(node, depth)))
                walk(node.body, depth + 1)

    walk(tree.body, 0)
    return out or None


_PY_FALLBACK = re.compile(r"^\s*(?:async\s+)?(?:def|class|import|from)\s")


def extract_py_fallback(src):
    """Rozbity Python (syntax error) - regex je porad lepsi nez nic."""
    out = [
        (i + 1, ln.rstrip()[:120])
        for i, ln in enumerate(src.splitlines())
        if _PY_FALLBACK.match(ln)
    ]
    return out or None


_MD_H = re.compile(r"^(#{1,6})\s+(.*)$")


def extract_md(src):
    """Nadpisy # az ###### s cisly radku."""
    out = []
    for i, ln in enumerate(src.splitlines()):
        m = _MD_H.match(ln)
        if m:
            out.append((i + 1, f"{m.group(1)} {m.group(2)[:110]}"))
    return out or None


_TS = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function\s+\w+|class\s+\w+|interface\s+\w+|type\s+\w+\s*=|"
    r"const\s+\w+\s*[:=]\s*(?:async\s*)?\(|enum\s+\w+)"
)


def extract_ts(src):
    """export / function / class / interface / type / const x = ()."""
    out = [
        (i + 1, ln.strip()[:120])
        for i, ln in enumerate(src.splitlines())
        if _TS.match(ln)
    ]
    return out or None


# Kostra vetsi nez tenhle podil originalu = neni co setrit -> None.
# Namerene pomery jsou 3-13 %, takze 0,25 je stale volne sito.
MAX_SKELETON_RATIO = 0.25

# Strop poctu polozek. Vic uz neni mapa, ale jiny velky soubor.
MAX_SKELETON_LINES = 120

# Strop velikosti souboru pro vyrobu kostry (bytes). Guard ma vlastni
# MAX_SCAN_CHARS = 4 000 000 prave kvuli jednotkam ms - skeleton() drive
# zadny strop nemel a ast.parse/regex nad desitkami MB uz muze narazit na
# 10s timeout hooku (nameren 8 MB .py -> 5,5 s, 12 MB -> 6,2 s). Rule A fajruje
# i MIMO zaindexovane koreny, takze bez stropu je zranitelny kazdy velky
# .py/.md/.ts kdekoliv na disku.
MAX_SKELETON_FILE_BYTES = 2_000_000

# .json zamer ne CHYBI: json.loads zplosti strukturu a cisla radku se ztrati,
# takze kostra by neslo pouzit pro cileny Read. 0,6 % zasahu (spec sekce 7).
EXTRACTORS = {
    ".py": [extract_py, extract_py_fallback],
    ".md": [extract_md],
    ".ts": [extract_ts],
    ".tsx": [extract_ts],
    ".js": [extract_ts],
    ".jsx": [extract_ts],
    ".mjs": [extract_ts],
}


def _format(entries, total_lines):
    """[(radek, text)] -> wire format Readu + HLASITY marker pri orezu."""
    truncated = len(entries) > MAX_SKELETON_LINES
    if truncated:
        entries = entries[:MAX_SKELETON_LINES]
    body = "\n".join("%d\t%s" % (ln, txt) for ln, txt in entries)
    if truncated:
        body += (
            "\n... kostra orezana na %d polozek z %d radku souboru - "
            "zbytek souboru kostra NEPOPISUJE ..." % (MAX_SKELETON_LINES, total_lines)
        )
    return body


def skeleton(path, src=None):
    """-> (text, meta) nebo (None, meta s duvodem). NIKDY nevyhodi vyjimku.

    text is None znamena: kostru nelze nabidnout => volajici MUSI Read pustit.
    """
    meta = {
        "ext": "",
        "reason": None,
        "orig_tok": 0,
        "skel_tok": 0,
        "ratio": 1.0,
    }
    try:
        meta["ext"] = os.path.splitext(path)[1].lower()
        chain = EXTRACTORS.get(meta["ext"])
        if not chain:
            meta["reason"] = "neznamy typ"
            return None, meta
        if src is None:
            if os.path.getsize(path) > MAX_SKELETON_FILE_BYTES:
                meta["reason"] = "soubor prilis velky pro kostru"
                return None, meta
            with open(path, encoding="utf-8", errors="replace") as f:
                src = f.read()
        meta["orig_tok"] = round(len(src) / CHARS_PER_TOKEN)
        entries = None
        for fn in chain:
            entries = fn(src)
            if entries:
                break
        if not entries:
            meta["reason"] = "extraktor nic nenasel"
            return None, meta
        text = _format(entries, len(src.splitlines()))
        meta["skel_tok"] = round(len(text) / CHARS_PER_TOKEN)
        meta["ratio"] = meta["skel_tok"] / meta["orig_tok"] if meta["orig_tok"] else 1.0
        if meta["ratio"] >= MAX_SKELETON_RATIO:
            meta["reason"] = "kostra je %.0f %% originalu" % (100 * meta["ratio"])
            return None, meta
        return text, meta
    except Exception as e:  # fail-open vzdy
        meta["reason"] = "vyjimka: %s" % type(e).__name__
        return None, meta
