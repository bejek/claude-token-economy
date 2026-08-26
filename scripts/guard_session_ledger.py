#!/usr/bin/env python3
"""Drzi `docs/session-ledger.md` v roli STITKU: kratky, prepisovany, cely viditelny.

PROC (nalez 2026-08-22): ledger je globalne gitignorovany (`~/.gitignore_global`,
radek 3) -- spravne, protoze rehydratacni stitek se meni kazdou generaci a
verzovany by delal merge sum presne v okamziku, kdy se slucuji worker vetve
(rozhodnuti z 08-05). Jenze soubor si k te praci pribral
druhou: zacal byt append-only zurnalem nalezu. Vysledek namereny v praxi --
314 radku / 23 kB, deset vlastnich `##` sekci, `STAV: uzavreno` na radku 3 a
pod tim zapisy o den mladsi.

Slouceni je drahe hned trikrat:
  * NEVERZOVANE -- `git add -A` soubor tise preskoci a `git status` mlci, takze
    "zapsal jsem to do repa" je nepravda, kterou nic nevyvrati (skoro shorela
    forenzika hard freezu, 08-18);
  * NEVIDITELNE -- injektor bere `text[:CAP]`, tedy drzi ZACATEK a zahazuje
    konec. Pripisuje se na konec => nejnovejsi zapisy jsou prave ty, ktere se
    do kontextu nikdy nedostanou. Obsah, za ktery se zaplatily tokeny a ktery
    nikdo nikdy neprecte;
  * NEROZHODNUTELNE -- kdyz stitek nese i historii, prestava jit odpovedet
    "co je NEXT" pohledem.

Deleni prace, ktere tenhle guard vynucuje:
  docs/session-ledger.md            -- stitek. gitignored, <= FILE_CAP, prepisuje se.
  docs/journal/YYYY-MM-DD-<tema>.md -- nalez. VERZOVANY, append-only, roste.

Invariant, na kterem to stoji: FILE_CAP < INJECT_CAP. Do souboru se vejde jen
to, co injektor stejne cely ukaze => kategorie "napsane, ale neviditelne"
prestava existovat. Ne zakazana, NEMOZNA. Proto se strop importuje z
inject_session_ledger.py a nekopiruje: dve cisla by driftovala a dira by se
vratila potichu.

DVE FAZE, protoze jedna nestaci (lekce z guard_upcoming_postwrite.py):
  PreToolUse  -- Write/Edit/MultiEdit umime slozit dopredu => `deny`, zapis
                 nikdy nedopadne. Bash/PowerShell slozit neumime => jen snapshot.
  PostToolUse -- cte soubor Z DISKU a porovnava se snapshotem. Chyta heredoc,
                 `sed`, `python`, `Set-Content` -- tedy cestu, kterou v bypass
                 rezimu piseme nejcasteji a kterou by samotny PreToolUse guard
                 minul, aniz by o tom kdokoliv vedel.

Hlasi se VYHRADNE cerstve vady (stav presel cisty -> vadny). Druha hlaska o teze
vade by visela na kazdem dalsim prikazu a prestala by se cist.

Fail-open: cokoliv nepovedeneho => mlceni. Guard brani nehodam, ne praci.
"""

import hashlib
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# `resulting_text` / `_file_text` -- slozeni vysledneho obsahu z payloadu.
import write_intent as gu  # noqa: E402
from hook_io import read_payload  # noqa: E402
from inject_session_ledger import CAP as INJECT_CAP  # noqa: E402

TARGET = "session-ledger.md"

# Strop souboru. Rezerva pod INJECT_CAP je zamerna: injektor kolem textu jeste
# lepi hlavicku, pripadne varovani o zamrznuti, a ta rezie se do jeho capu pocita.
FILE_CAP = 3000
if FILE_CAP >= INJECT_CAP:  # nekdo snizil injekcni cap pod nas -- invariant padl
    FILE_CAP = max(500, INJECT_CAP - 1000)

_QUOTED_PATH_RE = re.compile(r"[\"']([^\"']*session-ledger\.md)[\"']", re.IGNORECASE)
_BARE_PATH_RE = re.compile(r"[^\s\"'<>|]*session-ledger\.md", re.IGNORECASE)
# H2+ nadpis = soubor si zalozil kapitoly, tedy se z nej stava zurnal. Sablona
# ma jediny H1 (`# TASK ...`) a dal uz jen pole `KLIC: hodnota`.
_HEADING_RE = re.compile(r"^\s{0,3}#{2,}\s+\S")
_JOURNAL_RE = re.compile(r"^\s*(ŽURNÁL|ZURNAL)\s*:", re.IGNORECASE)
_STAV_RE = re.compile(r"^\s*STAV\s*:", re.IGNORECASE)


def mentions_target(tool_input):
    """Spousti se uz na pouhou ZMINKU souboru, ne na detekci zapisu -- stejne
    jako u sesterskeho guardu. Heuristika "vypada to jako zapis" by snapshot
    neporidila prave u heredocu, tedy u vady, kvuli ktere hook vznikl."""
    blob = f"{tool_input.get('file_path') or ''} {tool_input.get('command') or ''}"
    return TARGET in blob.lower()


def target_path(tool_input, cwd):
    """Soubor ke kontrole. Relativni cesta z prikazu je vuci cwd hooku
    nepouzitelna => padame na kanonicke `<cwd>/docs/session-ledger.md`, coz je
    presne to misto, ktere cte injektor."""
    path = str(tool_input.get("file_path") or "")
    if TARGET in path.lower():
        return path
    command = str(tool_input.get("command") or "")
    for m in _QUOTED_PATH_RE.finditer(command):
        if os.path.isabs(m.group(1)):
            return m.group(1)
    for m in _BARE_PATH_RE.finditer(command):
        if os.path.isabs(m.group(0)):
            return m.group(0)
    return os.path.join(cwd, "docs", "session-ledger.md") if cwd else None


def _code_fenced(lines):
    """Indexy radku uvnitr ```blokum```. Shell komentar `## neco` ve vystrizku
    prikazu neni zalozeni kapitoly a nema kvuli nemu padnout legitimni zapis."""
    inside, fenced = False, set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            inside = not inside
            fenced.add(i)
            continue
        if inside:
            fenced.add(i)
    return fenced


def violations(text):
    """{'size': int, 'headings': [str], 'no_journal': bool} nebo None (necitelne).

    Tri osy, protoze kazda popisuje jinou mutaci stitku zpatky v zurnal:
    delka (naroste), kapitoly (strukturuje se), chybejici ukazatel (nalez se
    nema kam odlozit, takze zustane tady)."""
    if text is None:
        return None
    lines = text.splitlines()
    fenced = _code_fenced(lines)
    headings = [
        line.strip()
        for i, line in enumerate(lines)
        if i not in fenced and _HEADING_RE.match(line)
    ]
    has_stav = any(_STAV_RE.match(line) for line in lines)
    return {
        "size": len(text),
        "headings": headings,
        # Ukazatel se vyzaduje jen od stitku, ktery uz nejaky task nese. Prazdny
        # ci rozepsany soubor nema co ukazovat a nema smysl ho kvuli tomu brzdit.
        "no_journal": has_stav and not any(_JOURNAL_RE.match(line) for line in lines),
    }


SIZE_HELP = (
    "Ledger je ŠTÍTEK pro rehydrataci po `/clear`, ne žurnál. Strop je "
    f"{FILE_CAP} znaků a je záměrně POD injekčním capem ({INJECT_CAP}) — co se "
    "do souboru vejde, to celé i uvidíš. Nad stropem začne injektor ořezávat "
    "`text[:CAP]`, tedy zahodí KONEC, což je zrovna to, cos právě dopsal.\n"
    "  · minulost (co se stalo, měření, forenzika, co bylo vyvráceno) → "
    "`docs/journal/YYYY-MM-DD-<téma>.md` — VERZOVANÝ, přežije checkout i `/clear`\n"
    "  · hotové kroky → commit message, ne sem (`git log` je pravda, ledger je záměr)\n"
    "  · ve štítku nech jen: STAV, NEXT, HOTOVO (co se NESMÍ dělat znovu), "
    "BLOKERY, ROZHODNUTÍ, NÁLEZY, ŽURNÁL"
)

HEADING_HELP = (
    "`##` nadpis znamená, že si štítek zakládá kapitoly — a přesně takhle se z "
    "ledgeru stal 23kB žurnál, který nikdo nečte celý. Šablona má jediný `#` "
    "nadpis a dál už jen pole `KLÍČ: hodnota`.\n"
    "  · potřebuješ sekce → je to nález a patří do `docs/journal/`"
)

JOURNAL_HELP = (
    "Chybí pole `ŽURNÁL:`. Je povinné právě proto, aby absence trvalé stopy "
    "byla VIDĚT — ukazatel na verzovaný soubor jako jediný přežije `/clear` "
    "i zánik checkoutu.\n"
    "  · `ŽURNÁL: docs/journal/2026-08-22-<téma>.md` — když session našla něco trvalého\n"
    "  · `ŽURNÁL: —` — když nenašla. Legitimní odpověď, ne filler."
)


def _snapshot_file(session_id, path):
    key = hashlib.md5(str(path).encode("utf-8", "replace")).hexdigest()[:8]
    return os.path.join(
        tempfile.gettempdir(),
        f"claude_ledger_snap_{session_id or 'nosession'}_{key}.json",
    )


def _store(snap_file, vio):
    try:
        with open(snap_file, "w", encoding="utf-8") as fh:
            json.dump(vio, fh)
    except OSError:
        pass


def _load(snap_file):
    """(snapshot, mel_snapshot). Bez snapshotu se v Post fazi mlci -- jinak by
    guard rval na cizi bordel po kazdem prikazu, ktery soubor jen zmini."""
    try:
        with open(snap_file, encoding="utf-8") as fh:
            return json.load(fh), True
    except (OSError, ValueError):
        return None, False


def fresh_parts(before, after):
    """Hlasky pro vady, ktere vznikly TIMHLE zapisem."""
    parts = []
    if before is None or after is None:
        return parts

    # Delka: hlasi se jen kdyz soubor NAROSTL pres strop. Zmensujici zapis nad
    # stropem je uklid a nema se okrikovat -- jinak by guard trestal svou vlastni
    # napravu a vznikla by smycka.
    if after["size"] > FILE_CAP and after["size"] > before["size"]:
        parts.append(
            f"SESSION LEDGER — {after['size']} znaků, strop {FILE_CAP} "
            f"(přerostlo o {after['size'] - FILE_CAP}). Zápis přes Bash/PowerShell "
            "obchází PreToolUse kontrolu, takže to hlásím až teď. Zkrať ho TEĎ, ne "
            "na konci session.\n\n" + SIZE_HELP
        )

    new_headings = [h for h in after["headings"] if h not in set(before["headings"])]
    if new_headings:
        parts.append(
            "SESSION LEDGER — přibyly nadpisy, které do štítku nepatří ("
            + ", ".join(h[:60] for h in new_headings[:5])
            + ").\n\n"
            + HEADING_HELP
        )

    if after["no_journal"] and not before["no_journal"]:
        parts.append("SESSION LEDGER — " + JOURNAL_HELP)
    return parts


def deny_reason(vio):
    """Duvod pro PreToolUse deny, nebo None kdyz je vysledny soubor v poradku."""
    if vio is None:
        return None
    parts = []
    if vio["size"] > FILE_CAP:
        parts.append(
            f"Tenhle zápis by udělal ze session-ledgeru {vio['size']} znaků "
            f"(strop {FILE_CAP}, přes o {vio['size'] - FILE_CAP}).\n\n" + SIZE_HELP
        )
    if vio["headings"]:
        parts.append(
            "Zápis zakládá v ledgeru nadpisy: "
            + ", ".join(h[:60] for h in vio["headings"][:5])
            + "\n\n"
            + HEADING_HELP
        )
    if vio["no_journal"]:
        parts.append(JOURNAL_HELP)
    if not parts:
        return None
    return (
        "\n\n---\n\n".join(parts)
        + "\n\nZapiš znovu ve zkrácené podobě — obsah neztrácíš, jen ho ukládáš "
        "tam, kde ho někdo najde."
    )


def main():
    data = read_payload()  # UTF-8 stdin + fail-open, viz hook_io.py
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict) or not mentions_target(tool_input):
        return 0

    path = target_path(tool_input, data.get("cwd") or os.getcwd())
    if not path:
        return 0
    snap_file = _snapshot_file(data.get("session_id"), path)

    if data.get("hook_event_name") != "PostToolUse":
        # Pre faze. Snapshot se poridi VZDY -- i kdyz zapis vzapeti odmitneme,
        # protoze Post faze musi mit s cim porovnavat i u prikazu, ktere jsme
        # slozit neumeli.
        _store(snap_file, violations(gu._file_text(path)))
        _, after = gu.resulting_text(data.get("tool_name"), tool_input)
        if after is None:
            return 0  # Bash/PowerShell -- obsah nevidime, resi Post faze
        reason = deny_reason(violations(after))
        if reason:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    },
                    ensure_ascii=False,
                )
            )
        return 0

    before, had_snapshot = _load(snap_file)
    after = violations(gu._file_text(path))
    # Snapshot se posouva vzdy, i kdyz se hlasi -- druha hlaska o teze vade by
    # visela na kazdem dalsim prikazu v session.
    _store(snap_file, after)
    if not had_snapshot:
        return 0
    parts = fresh_parts(before, after)
    if not parts:
        return 0
    print(
        json.dumps(
            {"decision": "block", "reason": "\n\n---\n\n".join(parts)},
            ensure_ascii=False,
        )
    )
    return 0


def check(path):
    """`--check <cesta>`: rucni verdikt nad souborem. exit 0 = cisty, 1 = vadny.

    Existuje kvuli migracim: bez nej znel jediny zpusob overeni "zkus do nej
    zapsat a koukni, jestli te guard pusti", coz je test, ktery se neda dat do
    handoffu ani do CI. Kontroluje TENTYZ `violations()` jako obe hookove faze,
    takze verdikt nemuze driftovat od toho, co realne deny-uje."""
    gu_text = gu._file_text(path)
    if gu_text is None:
        print(f"{path}: nelze přečíst (fail-open — hook by mlčel)")
        return 0
    reason = deny_reason(violations(gu_text))
    if not reason:
        print(
            f"{path}: OK — {len(gu_text)} zn. / strop {FILE_CAP}, štítek je v pořádku"
        )
        return 0
    print(f"{path}: VADNÝ\n\n{reason}")
    return 1


if __name__ == "__main__":
    try:
        if "--check" in sys.argv:
            i = sys.argv.index("--check")
            target = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
            if not target:
                print(
                    "použití: guard_session_ledger.py --check <cesta k session-ledger.md>"
                )
                raise SystemExit(2)
            raise SystemExit(check(target))
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open: rozbity guard nesmi zastavit praci
