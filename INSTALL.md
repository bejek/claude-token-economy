# INSTALL — Token Economy Kit

> **Tenhle soubor je návod pro RUČNÍ instalaci a je psaný pro Claude Code.**
> Otevři CC v adresáři kitu a řekni: „Nainstaluj mi Token Economy Kit podle
> INSTALL.md." Člověk si ho může projít taky — kroky jsou čitelné.

> 💡 **Většina lidí sem nemusí.** Standardní cesta je plugin:
> `/plugin marketplace add bejek/claude-token-economy` a
> `/plugin install token-economy`. Ruční instalace dává smysl jen když
> (a) chceš vybrat jen některé hooky, (b) máš `python3` a ne `python`, nebo
> (c) chceš mít skripty pod vlastní kontrolou a upravovat si je.
> **I po instalaci pluginu tě ale čekají kroky 5 a 6 níž** — prahy podle
> kontextového okna a sekce v `CLAUDE.md`. Ty plugin udělat nemůže.
> Kroky 1–4 (kopírování skriptů a sloučení `settings.json`) při pluginu
> přeskoč — dělal bys je dvakrát a guardy by ti fajrovaly dvojmo.

## Co instaluješ

Hooky, které drží session Claude Code v levném pásmu kontextu. Kontext je
kumulativní a platí se znovu každým callem; cena je plochá do 100k a nad ní se
láme až na 7,6×. Detaily a naměřená čísla jsou v `README.md`.

## Zásady, které musíš při instalaci dodržet

1. **NIKDY nepřepisuj existující `settings.json` a `CLAUDE.md` uživatele.**
   Vždy je **slučuj** a před zápisem udělej zálohu (`*.bak-tokeneconomy`).
2. **Nejdřív se podívej, co tam už je.** Když už uživatel nějaký z těchhle hooků
   má, řekni mu to a zeptej se, místo abys jeho verzi tiše přepsal.
3. **Ptej se u nejednoznačností**, netipuj. Zvlášť u kroku 5 (kontextové okno)
   a kroku 7 (gitignore).
4. Na konci **ověř, že to fajruje** (krok 8) a **vypiš uživateli shrnutí**, co
   se změnilo a co si má případně doladit.

---

## Krok 1 — Rozkoukej se

Zjisti a uživateli vypiš:

- domovský adresář (`~`) a jeho absolutní tvar (Windows: `C:\Users\<jméno>`)
- jestli existuje `~/.claude/settings.json` a jestli už má klíč `hooks`
- jestli existuje `~/.claude/CLAUDE.md`
- jestli existují `~/.claude/scripts/` a `~/.claude/agents/`
- verzi Pythonu (`python --version` nebo `python3 --version`)

**Python 3 musí být v `PATH`.** Hooky jsou čistý stdlib, žádné závislosti.
Když `python` neexistuje, ale `python3` ano, budeš to muset zohlednit v cestách
příkazů v kroku 4 — a řekni to uživateli.

## Krok 2 — Zkopíruj skripty

Vytvoř `~/.claude/scripts/` a `~/.claude/agents/`, pokud nejsou, a zkopíruj:

- `scripts/*.py` → `~/.claude/scripts/`
- `agents/skill-reader.md` → `~/.claude/agents/`

**Když už některý soubor existuje**, neprepisuj ho mlčky — porovnej a zeptej se.

Soubory a jejich role:

| soubor | role |
|---|---|
| `hook_io.py` | **sdílená knihovna, bez ní nefunguje nic** — UTF-8 streamy, parsování payloadu, měření kontextu z transkriptu, detekce zavírání session |
| `write_intent.py` | složení výsledného obsahu souboru z payloadu (dependency ledger guardu) |
| `context_size_warning.py` | tři prahy kontextu (175k/215k/250k) — **jádro celé sady** |
| `inject_session_ledger.py` | injektuje ledger na startu session |
| `guard_session_ledger.py` | drží ledger v roli štítku (≤ 3 000 zn.) |
| `guard_spawn_gate.py` | nespawnuj vlnu, kterou nedosedíš |
| `guard_agent_model_routing.py` | brání tichému inheritu modelu u `Agent` |
| `guard_workflow_model_routing.py` | totéž pro `Workflow` + `effort` |
| `guard_heavy_skill_delegation.py` | mega-skill jen přes `skill-reader` subagenta |
| `guard_read_before_search.py` | zastaví čtení celého velkého souboru, nabídne kostru |
| `read_skeleton.py` | výroba kostry (dependency předchozího) |
| `guard_runaway_loop.py` | 5× identický call → DENY |
| `post_compact_context.py` | po `/compact` vrátí posledních 10 zpráv |
| `context_attribution.py` | offline analýza: co sežralo kontext (nespouští se jako hook) |

## Krok 3 — Ověř, že skripty běží

Než je zapojíš jako hooky, ověř, že se aspoň importují:

```bash
cd ~/.claude/scripts
python -c "import hook_io, read_skeleton; print('imports OK')"
```

Prázdný payload musí projít fail-open (exit 0, žádný výstup):

```bash
echo '{}' | python ~/.claude/scripts/context_size_warning.py; echo "exit=$?"
```

Očekáváš `exit=0`. **Když kterýkoliv hook na prázdném vstupu spadne nenulově,
nezapojuj ho** a nahlas to uživateli — hook nesmí shodit prompt.

## Krok 4 — Slouč hooks do `settings.json`

Vezmi `settings-hooks.json` z kitu a **slouč** ho do `~/.claude/settings.json`.

**Před zápisem udělej zálohu.**

Pravidla slučování:

- Klíč `hooks` je objekt událostí (`SessionStart`, `PreToolUse`, …), každá nese
  **pole** položek. Nové položky **přidávej do pole**, nemaž existující.
- **V cestách nahraď `<CLAUDE_DIR>`** absolutní cestou k `~/.claude`
  (např. `C:/Users/pepa/.claude`). Na Windows používej v JSONu **lomítka `/`**,
  ať se nemusíš prát s escapováním zpětných lomítek.
- Když už uživatel identický hook má (stejný skript), **nepřidávej ho dvakrát** —
  duplicitní hook fajruje dvakrát.
- Zachovej `timeout` hodnoty tak, jak jsou v `settings-hooks.json`.

Po zápisu **ověř, že je soubor validní JSON**:

```bash
python -c "import json,io; json.load(io.open(r'C:/Users/<jméno>/.claude/settings.json', encoding='utf-8')); print('settings.json OK')"
```

Když validace selže, **vrať zálohu** a řekni to uživateli.

## Krok 5 — Doladit prahy podle kontextového okna

Prahy v `context_size_warning.py` (`T1=175_000`, `T2=215_000`, `T3=250_000`) jsou
nastavené pro **1M kontextové okno**. Uživatelům s 200k oknem nesedí.

**Zeptej se uživatele, jaké má kontextové okno**, a podle toho:

| okno | `T1` / `T2` / `T3` | spawn gate `BAND` / `HARD` |
|---|---|---|
| 1M | 175k / 215k / 250k (beze změny) | 150k / 175k |
| 200k | 120k / 150k / 175k | 100k / 120k |

Když uživatel neví, nech výchozí a řekni mu, kde se to mění.

Analogicky uprav pásma v `guard_spawn_gate.py` — konstanty `BAND, HARD` jsou
hned pod docstringem. `HARD` má být **stejné číslo jako `T1`** (nad prahem FINIŠ
se už nic nerozjíždí); tenhle vztah drž i po změně.

## Krok 6 — Přidej sekci do `CLAUDE.md`

Obsah `CLAUDE-md-snippet.md` **připoj** na konec `~/.claude/CLAUDE.md`
(vytvoř soubor, pokud neexistuje). Zálohu předem.

Ten snippet je druhá půlka systému — hooky vynucují meze, ale pravidla chování
(kdy psát do ledgeru, co delegovat subagentovi) musí model dostat v instrukcích.

**Když už tam podobná pravidla jsou**, neduplikuj je — ukaž uživateli, co bys
přidal, a nech ho rozhodnout.

## Krok 7 — Ledger do gitignore

`docs/session-ledger.md` **musí být gitignorovaný** — je to rehydratační štítek
jedné session, ne artefakt projektu. Verzovaný by dělal merge šum přesně ve
chvíli, kdy se slučují větve.

Zjisti, jestli má uživatel globální gitignore:

```bash
git config --global core.excludesFile
```

- **Když existuje** → přidej řádek `docs/session-ledger.md` (pokud tam není).
- **Když neexistuje** → zeptej se, jestli ho má založit (návrh:
  `~/.gitignore_global` + `git config --global core.excludesFile <cesta>`),
  nebo jestli si radši přidá řádek do `.gitignore` v každém repu zvlášť.

⚠️ **Řekni uživateli tuhle past:** protože je soubor gitignorovaný, `git add -A`
ho mlčky přeskočí a `git status` mlčí. Než kdokoliv (člověk i model) prohlásí, že
je něco „zapsané v repu", má ověřit `git ls-files` nebo `git check-ignore -v`.
Trvalé nálezy proto patří do **verzovaného** `docs/journal/YYYY-MM-DD-<téma>.md`,
ne do ledgeru.

Zkopíruj taky `docs/session-ledger-sablona.md` někam, kde ji uživatel najde
(např. `~/.claude/docs/`), nebo mu aspoň ukaž šablonu ze souboru.

## Krok 8 — Ověření

1. **JSON je validní** (viz krok 4).
2. **Hooky fajrují.** Restart Claude Code není potřeba pro `PreToolUse`, ale
   `SessionStart` hooky se načtou až v nové session — řekni uživateli, ať dá
   `/clear` nebo restartuje CC.
3. **Praktický test ledgeru** — v libovolném git repu vytvoř
   `docs/session-ledger.md` podle šablony se `STAV: běží`, dej `/clear` a ověř,
   že se obsah objevil v kontextu nové session.
4. **Praktický test guardu** — zkus přečíst velký soubor (>6 000 tok) bez
   `offset`/`limit`. Musí přijít deny s kostrou souboru.

## Krok 9 — Shrnutí pro uživatele

Na závěr vypiš:

- které soubory přibyly a kde
- co se změnilo v `settings.json` a `CLAUDE.md` (a kde jsou zálohy)
- jaké prahy jsou nastavené
- co si má doladit ručně (sekce 5 v `README.md`)
- **že `SessionStart` hooky naběhnou až po `/clear` nebo restartu**

---

## Odinstalace

Kdyby to uživatel chtěl vrátit: obnov `settings.json` a `CLAUDE.md` ze záloh
`*.bak-tokeneconomy` a smaž zkopírované skripty z `~/.claude/scripts/`.
Jednotlivý hook se vypne smazáním jeho položky z pole v `settings.json` —
skripty se navzájem nepotřebují, s jedinou výjimkou: `hook_io.py` potřebují
všechny a `read_skeleton.py` potřebuje `guard_read_before_search.py`.
