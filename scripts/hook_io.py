#!/usr/bin/env python3
"""Sdilena I/O vrstva hooku: stdin/stdout v UTF-8 + fail-open parse payloadu.

Proc existuje (nalez 2026-08-05, viz docs/handoff-2026-08-05-upcoming-guard-encoding.md):
Claude Code posila hook payload jako SYROVE UTF-8 bajty a stdout hooku cte taky
jako UTF-8. Python si ale na Windows oba streamy otevre v locale kodovani
(cp1250), takze bez reconfigure:

  * stdin  -- emoji a em-dash se rozpadnou na mojibake DRIV, nez na ne sahne
              jakykoliv regex. guard_upcoming_model_tag.py takhle falesne
              denyoval KAZDY legitimni zapis, tedy 100 % legitimnich
              zapisu, a protoze formatovy check bezi pred checkoff unikem,
              neslo ho ani obejit.
  * stdout -- `print(json.dumps(..., ensure_ascii=False))` s emoji hodi
              UnicodeEncodeError a hook spadne. context_size_warning.py na
              prahu T2 tiskne "⚠️", ktere v cp1250 neexistuje.

Jedno misto, protoze tuhle tri-radkovku nejde udrzet v synchronu ve dvanacti
souborech -- a pravidlo "vsechny hooky ctou pres hook_io" jde otestovat
(scripts/tests/test_hook_io.py), kdezto "nezapomen na reconfigure" ne.

Hooky se spousti jako `python ~/.claude/scripts/<hook>.py`, takze adresar
skriptu je sys.path[0] a `from hook_io import read_payload` funguje bez triku.
"""

import json
import re
import sys

_CMD_RE = re.compile(r"<command-name>\s*(/[\w:.-]+)")
# Commandy, ktere zaciname novou generaci kontextu -- viz session_closing().
RESET_COMMANDS = {"/clear", "/compact"}

# `/end` kdekoliv v promptu jako samostatny token: chyta i `<command-name>/end`
# (nasleduje `<`), i vetu "az budes hotovej, udelej /end a koncime". Nechyta
# `/endpoint` ani `//end`.
_CLOSING_RE = re.compile(r"(?<![\w/])/end(?![\w-])", re.IGNORECASE)
# Skills, jejichz vyvolani ZNAMENA zavirani session. Porovnava se holy nazev,
# tj. i plugin varianta `neco:end`.
CLOSING_SKILLS = {"end"}


def configure_streams():
    """stdin/stdout/stderr prepne na UTF-8. Fail-open: bez toho jedeme dal."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # None, pipe wrapper bez reconfigure, starsi Python -- nevadi


def read_payload():
    """Hook payload ze stdin jako dict. Cokoliv nepovedeneho -> {}.

    Prazdny dict = "nevim, co se deje". Kazdy hook na nej reaguje stejne jako
    driv na `except: return` -- nedela nic. Guard brani nehodam, ne praci.
    """
    configure_streams()
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def context_tokens(transcript_path):
    """Aktualni velikost kontextu v tokenech z transcriptu. Fail-open -> 0.

    Ground truth = `usage` POSLEDNIHO assistant zaznamu (cache_read +
    cache_creation + input). NEodhadovat ze znaku/4 -- podstreluje 2,3x
    (cestina + kod + tokenizer Opus 4.7+).

    Sdilene, protoze na tomhle cisle stoji dva hooky s ruznymi prahy
    (context_size_warning = navrh /clear, guard_spawn_gate = zakaz spawnu)
    a driftujici kopie by znamenala dva ruzne "kolik mam kontextu".
    """
    if not transcript_path:
        return 0
    # Od 08-16 bezi context_size_warning i na PostToolUse (= po KAZDEM callu),
    # a transcript na 200k ma desitky MB. Posledni assistant zaznam je u konce,
    # tak cteme jen chvost; kdyz v nem zadny neni (obri tool_result), fallback
    # na cely soubor.
    try:
        ctx = _scan_usage(transcript_path, tail_bytes=2_000_000)
        if ctx == 0:
            ctx = _scan_usage(transcript_path, tail_bytes=None)
    except Exception:
        return 0  # chybejici/necitelny transcript -> guard nebrzdi praci
    return ctx


def _scan_usage(transcript_path, tail_bytes):
    ctx = 0
    with open(transcript_path, "rb") as fh:
        if tail_bytes is not None:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            if size > tail_bytes:
                fh.readline()  # zahodit useknuty radek
        for raw in fh:
            try:
                rec = json.loads(raw.decode("utf-8", errors="ignore"))
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            usage = (rec.get("message") or {}).get("usage") or {}
            if not usage:
                continue
            ctx = (
                usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("input_tokens", 0)
            )
    return ctx


def _user_text(rec):
    """Text lidskeho turnu z user zaznamu. tool_result bloky ignoruje."""
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") != "tool_result"
        )
    return ""


def _invoked_skills(rec):
    """Nazvy skillu, ktere assistant v tomhle zaznamu vyvolal pres `Skill` tool."""
    for block in (rec.get("message") or {}).get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != "Skill":
            continue
        name = (block.get("input") or {}).get("skill")
        if isinstance(name, str):
            yield name.strip().lower().rsplit(":", 1)[-1]  # `plugin:end` -> `end`


def session_closing(transcript_path):
    """Zavira se v TEHLE generaci kontextu session? Fail-open -> False.

    Odpovida na otazku "drzi uzivatel session v rezimu uzavirani" -- guard se
    podle toho vyjme (viz guard_spawn_gate.py). Plati na zbytek generace, ne
    jen na jeden turn: `/end` neni turn, ale REZIM -- uzivatel k nemu dopisuje
    "a jeste dodelej X" a chce to dotahnout v TEHLE session (08-08).

    TRI SIGNALY, protoze jeden nestaci (nalez 08-08, artemis session shorela na
    277k). Puvodni verze cetla vyhradne `<command-name>/end</command-name>` --
    artefakt, ktery pri realnem `/end` NIKDY nevznikne:
      1. `<command-name>` pisou jen BUILT-IN commandy (`/clear`, `/effort`).
         `/end` je SKILL; ten se zapise jako `Skill` tool_use od assistanta plus
         `isMeta` zaznam s telem SKILL.md -- oboji guard preskakoval.
      2. Uzivatel ho navic casto neposila jako command, ale vetou: "az budes
         komplet hotovej, udelej /end a koncime". Pak zadny command zaznam
         nevznikne vubec a skill vyvola model sam.
    Proto: command-name NEBO holy `/end` v promptu NEBO `Skill(end)`. Ridi to
    fakt z transcriptu, ne marker, ktery si model napise sam.

    Vedome liberalni: `/end` zmineny v prompt v jinem vyznamu ("spawn gate se
    `/end` nedotyka") branu umlci na celou generaci. To je levna chyba -- gate
    je jen doporuceni a hlidani kontextu dela `context_size_warning.py`. Opacna
    chyba stoji to, co se stalo v artemis: nejdrazsi model dojel mechaniku
    rituálu rucne na 277k a stejne ji osekal.

    RESET NA `/clear`: /clear nezaklada novy soubor, transcript jede dal
    (overeno -- 120 zaznamu, /clear na indexu 58). Bez resetu by `/end` z minule
    generace umlcel gate uz napermanent. `/compact` stejne tak.

    Za lidsky turn se pocita user zaznam, ktery NENI:
      * tool_result (`toolUseResult`) -- vysledek volani, ne novy prompt,
      * `isMeta` -- expandovane telo skillu, `Base directory for this
        skill: ...`, `<local-command-caveat>`. Telo end.md cituje `/clear`
        i `/end`; ani jedno neni uzivateluv prompt.
    """
    if not transcript_path:
        return False
    closing = False
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                kind = rec.get("type")

                if kind == "assistant":
                    if CLOSING_SKILLS & set(_invoked_skills(rec)):
                        closing = True
                    continue

                if kind != "user":
                    continue
                if rec.get("isMeta") or rec.get("toolUseResult") is not None:
                    continue

                text = _user_text(rec)
                cmds = {m.group(1).lower() for m in _CMD_RE.finditer(text)}
                if cmds & RESET_COMMANDS:
                    closing = False  # nova generace kontextu -> cisty stit
                if _CLOSING_RE.search(text):
                    closing = True
    except Exception:
        return False  # necitelny transcript -> guard rozhodne sam podle kontextu
    return closing
