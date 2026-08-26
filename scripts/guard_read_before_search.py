#!/usr/bin/env python3
"""PreToolUse guard: zastavi CTENI CELEHO VELKEHO SOUBORU, ktery je zaindexovany
v semantickem hledani - misto nej nabidne search_code + cileny Read s offsetem.

PROC (mereni 2026-07-27, docs/specs/2026-07-27-c0-distribuce-read-volani.md):
Read vysledek nezmizi - sedi v kontextu a posila se znovu pri KAZDEM dalsim callu.
Namereny medianovy nasobic: 134x v hlavni session, 25x v subagentovi. Read vysledky
delaji 26,1 % kontextove spotreby hlavni session a 39,5 % u subagentu. Sklizen
(volani nad prahem AND pod zaindexovanym korenem AND bez offset/limit) = 5,6 %
veskere spotreby pri ~6 viditelnych zasazich denne.

DVE PRAVIDLA, OR (spec docs/specs/2026-07-28-b2-kostra-misto-shrnovace.md):
  pravidlo A (kostra, nove)  6 000 hlavni / 8 000 subagent tok, nemusi byt
    pod zaindexovanym korenem - staci, ze kostru lze vyrobit
  pravidlo B (puvodni C2, beze zmeny)  20 000 hlavni / 10 000 subagent tok,
    musi byt pod zaindexovanym korenem - drzi soubory bez kostry (.diff, .ps1)
Prahy A jsou obracene proti C1 schvalne: subagent ma 4x mensi kontext, ale
5,4x mensi nasobic, takze vynucene kolo navic se u nej nema cim rozpustit.

DETEKCE SUBAGENTA (overeno empiricky, probe hook + headless session 2026-07-27):
PreToolUse payload ma v subagentovi navic klice `agent_type` a `agent_id`;
v hlavni session chybi. POZOR: `transcript_path` ani `session_id` NErozlisuji -
subagent dostava tutez cestu k hlavnimu transcriptu, takze detekce pres cestu
(napr. hledani "/subagents/") NEFUNGUJE, i kdyz subagenti vlastni transcript maji.

ODHAD VELIKOSTI - pocita se WIRE FORMAT, ne st_size (lekce z mereni):
Read doda `<cislo_radku>\\t<obsah>` spojene \\n, bez odsazeni, BEZ orezu dlouhych
radku (overeno: 6000znakovy radek prosel cely). Odhad = (znaky souboru + rezie
prefixu) / 1,85. Pomer 1,85 znaku/token je NAMERENY na 17 900 parech z transcriptu,
ne odhadnuty jako chars/4 (to je pro tenhle korpus lez o 50 %).
Cte se maximalne MAX_SCAN_CHARS znaku, ne cely soubor - u vetsich se hlasi dolni
odhad ("min."), protoze uz naskenovana cast je platna spodni mez.

Read ma vlastni token cap ~25 000 tok (`truncatedByTokenCap` v toolUseResult),
takze nad nim se cely soubor stejne nedozvis - to je v deny hlasce zminene, aby
model nemel iluzi, ze deny ho pripravil o kompletni obsah.

FAIL-OPEN vsude: chyba, neznamy tvar, nectitelny soubor, binarka -> exit 0.
Guard ma branit nehodam, ne blokovat praci. Explicitni offset/limit vzdy projde -
to je zamer, ne dira: vedomy pozadavek na rozsah je presne to chovani, ktere chceme.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_skeleton  # noqa: E402
from hook_io import read_payload

# Namereny pomer znaku na token pro tenhle korpus (NE chars/4).
CHARS_PER_TOKEN = 1.85

# Prahy pravidla A (kostra) - spec 2026-07-28 sek. 4. Obracena asymetrie proti C1:
# subagent ma 4x mensi kontext, ale 5,4x mensi nasobic, takze vynucene kolo
# navic se u nej nema cim rozpustit => jeho break-even je VYSSI.
#   break-even = kostra + X + kontext/nasobic
#   hlavni  524 + 1000 + 136366/134 = 2 542 tok  (p90 kontext: 3 869)
#   subagent 524 + 1000 +  50439/25 = 3 542 tok  (p90 kontext: 6 288)
THRESHOLD_MAIN = 6000
THRESHOLD_SUBAGENT = 8000

# Prahy pravidla B = puvodni C2. Drzi zaindexovane soubory, ktere kostru
# nemaji (.diff, .txt, .ps1) - bez nich by nove nastala regrese proti C2.
THRESHOLD_B_MAIN = 20000
THRESHOLD_B_SUBAGENT = 10000

# Vlastni strop Read toolu (namereno: 2500radkovy soubor doruceny na 1771 radku
# s priznakem truncatedByTokenCap). Slouzi jen k formulaci hlasky.
READ_TOKEN_CAP = 25000

# Namereny medianovy nasobic - kolikrat se vysledek posle znovu (spec §0.3).
MULTIPLIER_MAIN = 134
MULTIPLIER_SUBAGENT = 25

# Strop skenovani. Vic nez tohle uz je stejne davno nad kazdym prahem, takze
# presne cislo nema cenu - staci dolni mez. Drzi hook v jednotkach ms.
MAX_SCAN_CHARS = 4_000_000

# Zaindexovane koreny -> ktery semsearch server je pokryva (z .claude.json,
# SEMANTIC_SEARCH_ROOT kazdeho serveru).
INDEXED_ROOTS = [
    # PRAZDNE = pravidlo B (velke soubory bez kostry: .diff, .txt, .ps1) je vypnute,
    # pravidlo A (kostra) funguje dal a je to to hlavni. Guard je tim padem plne
    # funkcni i bez semantickeho hledani -- nabidka search_code se sama preskoci.
    #
    # Mas-li semanticky search MCP server, dopln (koren, nazev_serveru), napr.:
    #   (r"C:\Users\<ty>\Projects", "muj-semsearch-server"),
]

# Semsearch tooly jsou deferred (tool search) -- `alwaysLoad: true` slo z
# ~/.claude.json pryc 2026-08-14, protoze drzelo 44 schemat v promptu za 9,9k
# tokenu v KAZDE session (mereno /context all: 56,1k -> 46,2k).
# Overeno po zmene: primy `search_code` na deferred toolu normalne PROJDE, schema
# se dotahne transparentne -> fallback nize je pojistka pro pripad, kdy se server
# nestihne pripojit do 5s startup timeoutu a jeho tooly spadnou zpatky za tool
# search (holy call pak vrati InputValidationError). Kdyz guard nefajruje, stoji
# nula. Nevracet alwaysLoad bez zmereni ceny.
TOOL_SEARCH_FALLBACK = (
    "   (Kdyz tool neni nactenej -> `ToolSearch` s "
    '`query="select:mcp__%s__search_code"`, teprve pak volej.)'
)

# Read tyhle soubory nerendruje jako text (PDF stub, obrazky, notebooky s outputy),
# takze odhad znaky/1,85 pro ne neplati -> guard je nechava byt.
SKIP_EXT = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".tif",
    ".tiff",
    ".xlsx",
    ".xls",
    ".docx",
    ".pptx",
    ".odt",
    ".ods",
    ".zip",
    ".gz",
    ".7z",
    ".rar",
    ".tar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".ipynb",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
}


def matched_root(abs_path):
    """(koren, semsearch server) pokud soubor lezi pod zaindexovanym korenem."""
    target = os.path.normcase(abs_path)
    for root, server in INDEXED_ROOTS:
        norm_root = os.path.normcase(os.path.abspath(root))
        # hranice na separatoru, aby D:\Projects nechytal D:\Projects-zaloha
        if target == norm_root or target.startswith(norm_root + os.sep):
            return root, server
    return None


def line_prefix_chars(n_lines):
    """Rezie cislovani radku: soucet len(str(i)) + 1 tab pro i = 1..n."""
    total, start, digits = 0, 1, 1
    while start <= n_lines:
        end = min(n_lines, start * 10 - 1)
        total += (end - start + 1) * (digits + 1)
        start *= 10
        digits += 1
    return total


def estimate_tokens(path):
    """(odhad tokenu, je_presny) nebo None pri chybe.

    Presne prepocita, co Read doopravdy doda: znaky souboru + rezie cislovani
    radku, deleno namerenym pomerem znaku na token. Nad MAX_SCAN_CHARS se vraci
    dolni mez z naskenovane casti (je_presny=False).
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            buf = f.read(MAX_SCAN_CHARS + 1)
    except (OSError, ValueError):
        return None

    exact = len(buf) <= MAX_SCAN_CHARS
    lines = buf.count("\n") + 1
    return (len(buf) + line_prefix_chars(lines)) / CHARS_PER_TOKEN, exact


def human(n):
    """Citelne cislo: 3,3 M misto 3 318 376."""
    n = int(n)
    if n >= 1_000_000:
        return ("%.1f M" % (n / 1_000_000)).replace(".", ",")
    return format(n, ",d").replace(",", " ")


def build_reason(
    name, tokens, exact, threshold, scope, multiplier, match, skeleton_text
):
    """Deny hlaska. MUSI rict nahradu, ne jen zakazat - jinak je to sikana."""
    approx = "" if exact else "min. "
    tok_txt = "%s~%s tok" % (approx, human(tokens))
    downstream = human(int(tokens) * multiplier)
    root, server = match if match else (None, None)

    lines = [
        "CELY VELKY SOUBOR - zastaveno. `%s` = %s, prah pro %s je %s tok, "
        "ctes ho BEZ offset i BEZ limit." % (name, tok_txt, scope, human(threshold)),
        "",
        "PROC: Read vysledek nezmizi po pouziti - zustane v kontextu a posila se "
        "znovu pri kazdem dalsim callu. Namereny medianovy nasobic pro %s je %dx, "
        "takze to neni jednorazovych %s, ale kumulativne ~%s tokenu."
        % (scope, multiplier, tok_txt.replace("min. ", ""), downstream),
    ]

    if tokens > READ_TOKEN_CAP:
        lines += [
            "Navic bys cely soubor stejne nedostal: Read ma vlastni strop ~%s tok "
            "(truncatedByTokenCap) - zaplatil bys strop a mel jen zacatek."
            % human(READ_TOKEN_CAP),
        ]

    if skeleton_text is not None:
        lines += [
            "",
            "KOSTRA SOUBORU (vyrobena hookem, cisla radku sedi na original):",
            skeleton_text,
            "",
            "MISTO toho udelej tohle: `Read` tehoz souboru s `offset=<radek z "
            "kostry>` a `limit=100-200`. Kostra NENI cely soubor - popisuje jen "
            "strukturu, ne obsah tel funkci.",
        ]
        if root:
            lines += [
                "Kdyz z kostry neni jasne, kam sahnout, `mcp__%s__search_code` "
                "s dotazem prirozenym jazykem." % server.split(" ")[0],
                TOOL_SEARCH_FALLBACK % server.split(" ")[0],
            ]
    else:
        lines += [
            "",
            "MISTO toho udelej tohle:",
            "1) `mcp__%s__search_code` s dotazem na to, co v souboru doopravdy "
            "hledas (dotaz prirozenym jazykem, ne grep pattern) -> vrati konkretni "
            "misto + cisla radku." % server.split(" ")[0],
            "2) `Read` tehoz souboru s `offset=<radek z hledani>` a `limit=100-200`.",
            "   Kdyz jde o presny retezec/identifikator, je Grep levnejsi nez oboji.",
            TOOL_SEARCH_FALLBACK % server.split(" ")[0],
        ]

    lines += [
        "",
        "NEDELEJ tohle: Read s limit=2000 -> zjistit ze to nestaci -> Read znovu "
        "s offsetem. To jsou dva cally misto jednoho a vyjde DRAZ nez puvodni cteni.",
        "",
        "Kdyz opravdu potrebujes velky souvisly usek a vis proc, projde to "
        "s explicitnim offset + limit - vedomy rozsah je presne to chovani, "
        "ktere tenhle guard chce.",
    ]
    return "\n".join(lines)


def main():
    data = read_payload()  # UTF-8 stdin + fail-open, viz hook_io.py

    if data.get("tool_name") != "Read":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)

    # Podminka 1: volani je bez offset I bez limit (explicitni rozsah vzdy projde).
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        sys.exit(0)

    file_path = tool_input.get("file_path")
    if not file_path or not isinstance(file_path, str):
        sys.exit(0)

    # Relativni cesty vztahni k cwd ze payloadu, ne k cwd hooku.
    if not os.path.isabs(file_path):
        file_path = os.path.join(data.get("cwd") or os.getcwd(), file_path)
    abs_path = os.path.abspath(file_path)

    if os.path.splitext(abs_path)[1].lower() in SKIP_EXT:
        sys.exit(0)
    if not os.path.isfile(abs_path):
        sys.exit(0)  # neexistuje / adresar -> Read si to vyresi sam

    # Scope: subagent se pozna podle agent_type/agent_id v payloadu (viz docstring).
    is_subagent = bool(data.get("agent_type") or data.get("agent_id"))
    scope = "subagenta" if is_subagent else "hlavni session"
    multiplier = MULTIPLIER_SUBAGENT if is_subagent else MULTIPLIER_MAIN

    est = estimate_tokens(abs_path)
    if est is None:
        sys.exit(0)  # nectitelne -> fail-open
    tokens, exact = est

    match = matched_root(abs_path)  # None = mimo zaindexovane koreny
    skel_text, skel_meta = read_skeleton.skeleton(abs_path)

    th_a = THRESHOLD_SUBAGENT if is_subagent else THRESHOLD_MAIN
    th_b = THRESHOLD_B_SUBAGENT if is_subagent else THRESHOLD_B_MAIN

    rule_a = tokens > th_a and skel_text is not None
    rule_b = tokens > th_b and match is not None

    if not rule_a and not rule_b:
        sys.exit(0)

    reason = build_reason(
        name=os.path.basename(abs_path),
        tokens=tokens,
        exact=exact,
        threshold=th_a if rule_a else th_b,
        scope=scope,
        multiplier=multiplier,
        match=match,
        skeleton_text=skel_text if rule_a else None,
    )
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


if __name__ == "__main__":
    main()
