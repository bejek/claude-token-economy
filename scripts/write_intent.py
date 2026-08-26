#!/usr/bin/env python3
"""Slozeni vysledneho obsahu souboru z PreToolUse payloadu Write/Edit/MultiEdit.

Guard, ktery chce zapis zastavit DRIV, nez dopadne, musi umet dopredu rict, jak
bude soubor po zapisu vypadat. Tenhle modul to dela pro tooly, u kterych to jde.

Pouziva `guard_session_ledger.py`. Modul nezna hooky ani payloady jako celek --
dostane nazev toolu a jeho vstup, vrati (pred, po).
"""


def _file_text(path):
    """Obsah souboru, nebo None. Fail-open: co neprecteme, to nekontrolujeme."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, TypeError, ValueError):
        return None


def resulting_text(tool_name, tool_input):
    """(pred, po) obsah souboru -- nebo (None, None), kdyz to nejde slozit.

    Proc rekonstrukce misto cteni `new_string`: Edit nemusi poslat cely radek.
    Kdyz model meni radek pres jeho unikatni PREFIX, je `new_string` useknuty
    fragment a kontrola nad nim davala falesne vysledky. Radek ma smysl
    posuzovat az jako radek souboru.

    Bonus: chyti i Write (cely prepis), ktery pres `new_string` nebyl videt.

    Bash/PowerShell/NotebookEdit vraci (None, None) -- obsah dopredu nevidime.
    Prave proto ma guard i PostToolUse fazi, ktera cte soubor z disku.
    """
    path = tool_input.get("file_path")

    if tool_name == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str):
            return None, None
        return (_file_text(path) or ""), content

    if tool_name in ("Edit", "MultiEdit"):
        before = _file_text(path)
        if before is None:
            return None, None
        edits = tool_input.get("edits") if tool_name == "MultiEdit" else [tool_input]
        if not isinstance(edits, list) or not edits:
            return None, None
        after = before
        for e in edits:
            if not isinstance(e, dict):
                return None, None
            old, new = e.get("old_string"), e.get("new_string")
            if not isinstance(old, str) or not isinstance(new, str) or old not in after:
                return None, None  # stale/nejednoznacne -> Edit stejne selze sam
            after = (
                after.replace(old, new)
                if e.get("replace_all")
                else after.replace(old, new, 1)
            )
        return before, after

    return None, None
