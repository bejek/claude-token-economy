"""CO ZERE KONTEXT. Projde transcripty a rozpadne obsah session podle zdroje.

Kontext je kumulativni: skoro vsechno, co jednou pribylo, tam zustane az do
compactu. Takze soucet velikosti vsech bloku ~ velikost finalniho kontextu.
Meri se ve znacich / 4 (hruby odhad tokenu, staci na pomery).

Kategorie:
  tool:<Nazev>   vysledek nastroje (tool_result namapovany na jmeno nastroje)
  assistant      text + thinking hlavniho modelu
  user           co napsal uzivatel
  reminder       <system-reminder> bloky (memory, hooky, injekce harnessu)
  command        <command-name>/skill injekce (telo slash prikazu)
"""

import json
import glob
import os
import sys
import collections

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
TOPN = int(sys.argv[1]) if len(sys.argv) > 1 else 12


def blocks(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def scan(path):
    """-> (celkem_znaku, Counter kategorie->znaky, Counter detail->znaky)"""
    cat = collections.Counter()
    det = collections.Counter()
    id2tool = {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = r.get("type")
            if t not in ("user", "assistant"):
                continue
            m = r.get("message") or {}
            for b in blocks(m.get("content")):
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "tool_use":
                    id2tool[b.get("id")] = b.get("name", "?")
                    n = len(json.dumps(b.get("input") or {}, ensure_ascii=False))
                    cat["assistant"] += n
                    det[f"vstup:{b.get('name', '?')}"] += n
                elif bt == "tool_result":
                    c = b.get("content")
                    n = len(
                        c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                    )
                    name = id2tool.get(b.get("tool_use_id"), "?")
                    cat[f"tool:{name}"] += n
                    det[f"vysledek:{name}"] += n
                elif bt in ("text", "thinking"):
                    s = b.get("text") or b.get("thinking") or ""
                    n = len(s)
                    if t == "assistant":
                        cat["assistant"] += n
                    elif "<system-reminder>" in s:
                        cat["reminder"] += n
                    elif "<command-name>" in s:
                        cat["command"] += n
                    else:
                        cat["user"] += n
    return sum(cat.values()), cat, det


files = []
for d in glob.glob(os.path.join(ROOT, "*")):
    if not os.path.isdir(d):
        continue
    for f in glob.glob(os.path.join(d, "*.jsonl")):
        try:
            files.append((os.path.getsize(f), f))
        except OSError:
            pass
files.sort(reverse=True)

# POZOR na metodiku: brat jen N nejvetsich SOUBORU je kruhove (selektuje to na
# nastroj, ktery zapisuje nejvic bajtu). Scanujeme vsechny a delime do pasem
# podle finalni velikosti session.
import statistics as st

bands = {"<50k": [], "50-200k": [], "200k-1M": [], ">1M": []}
tot_cat = collections.Counter()
tot_det = collections.Counter()
n_sess = 0
per_sess = []
for _, f in files:
    ch, cat, det = scan(f)
    if ch < 40_000:  # < ~10k tokenu = sum
        continue
    n_sess += 1
    tot_cat.update(cat)
    tot_det.update(det)
    tk = ch / 4
    b = (
        "<50k"
        if tk < 50_000
        else ("50-200k" if tk < 200_000 else ("200k-1M" if tk < 1_000_000 else ">1M"))
    )
    read_share = cat.get("tool:Read", 0) / max(1, ch)
    bands[b].append((tk, read_share))
    per_sess.append((tk, read_share, f))

print(f"=== VSECHNY session >10k tok (n={n_sess}) — podil Read podle velikosti ===")
print(f"{'pasmo':10} {'n':>4} {'median velikost':>16} {'median podil Read':>19}")
for b, v in bands.items():
    if not v:
        print(f"{b:10} {0:4}")
        continue
    print(
        f"{b:10} {len(v):4} {st.median([x[0] for x in v]):15.0f}k {st.median([x[1] for x in v]) * 100:18.1f}%".replace(
            "k", " tok", 1
        )
    )
over = [x for x in per_sess if x[0] > 200_000]
print(
    f"\nsession pres 200k tok: {len(over)} z {n_sess} ({len(over) / max(1, n_sess) * 100:.0f}%)"
)

print(f"\n=== SOUCET pres {n_sess} nejvetsich session ===")
tot = sum(tot_cat.values()) or 1
print(f"{'kategorie':22} {'~tok':>9} {'podil':>7}")
for k, v in tot_cat.most_common(14):
    print(f"{k:22} {v // 4000:8}k {v / tot * 100:6.1f}%")

print("\n=== detail: vstupy vs vysledky nastroju ===")
for k, v in tot_det.most_common(14):
    print(f"{k:26} {v // 4000:8}k {v / tot * 100:6.1f}%")
