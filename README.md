# Token Economy Kit pro Claude Code

Sada hooků a konvencí, která drží session Claude Code v levném pásmu kontextu
a umožňuje kdykoliv dát `/clear`, aniž bys ztratil rozdělanou práci.

Není to teorie. Každý práh a každý guard tady vznikl jako reakce na konkrétní
session, která shořela — čísla níž jsou naměřená z reálného provozu (~88 600 API
callů, červenec–srpen 2026).

---

## 1. Proč to vůbec řešit

**Kontext je kumulativní a platí se ZNOVU při každém dalším callu.** Když si
v půlce session přečteš 20k tokenů dlouhý soubor, nezaplatíš 20k jednou —
zaplatíš je znovu při každém dalším tool callu až do konce session. Naměřený
medián: výsledek jednoho `Read` se v hlavní session pošle znovu **134×**.

Cena jednoho API callu podle velikosti kontextu (n = 88 612 callů):

| kontext | Ø cena / call | násobek |
|---|---|---|
| 0–50k | $0,13 | 1,0× |
| 50–100k | $0,14 | 1,1× |
| 100–150k | $0,24 | 1,9× |
| 150–200k | $0,35 | 2,7× |
| 200–300k | $0,48 | 3,7× |
| 300–400k | $0,65 | 5,0× |
| 500k+ | $0,98 | **7,6×** |

**Cena je plochá do 100k, pak se láme.** Z toho plyne celá strategie: nesnaž se
šetřit tokeny, snaž se držet session v nízkém pásmu a včas ji rozřezat.

Dvě čísla, která to shrnují:

- session s peakem >300k tok = medián **$23,24**
- session s peakem <150k tok = medián **$0,87** → **27× rozdíl**
- **53,8 %** celkových nákladů je `cache_read`, tj. kontext placený znovu

> Na předplatném se to neprojeví na faktuře, ale na limitech — jsou to stínové
> ceny, poměry platí stejně.

### Past č. 1: Claude svůj kontext NEVIDÍ

Tohle je jádro problému. **Model nemá živý čítač kontextu.** Ty ho vidíš ve
status line, on ne. Bez hooku, který mu velikost kontextu aktivně řekne, si sám
nikdy neřekne o `/clear` — protože nepozná, že je čas.

Proto je `context_size_warning.py` nejdůležitější kus téhle sady.

---

## 2. Čtyři pilíře

### Pilíř 1 — Tři prahy kontextu

Hook `context_size_warning.py` měří skutečnou velikost kontextu (z `usage`
posledního assistant záznamu v transkriptu: `cache_read + cache_creation +
input`) a při překročení prahu vloží modelu instrukci:

| práh | název | co to znamená |
|---|---|---|
| **175k** | FINIŠ | Dotáhni rozdělaný celek. **Neotvírej nové fronty** — nový task, další kolo review, deploy = nová session. Ledger drž aktuální. |
| **215k** | CLEAR | Už jen nezbytnost. Počkej na běžící subagenty, zapiš jejich výsledky do ledgeru, nabídni `/clear`. Strop je 230k. |
| **250k** | SELHÁNÍ | Protokol selhal. Zapiš, stop. Žádná „ještě jedna věc". |

**Hook běží na dvou eventech, a to je podstatné.** Původně jel jen na
`UserPromptSubmit`, tedy fajrnul, až když člověk něco napsal. Během autonomního
běhu (subagenti, deploy příprava) mlčel — přesně tam, kde byl potřeba.
`PostToolUse` ho slyší i uprostřed běhu. Na `PostToolUse` je throttle: hlásí jen
při překročení prahu, ne po každém callu.

### Pilíř 2 — Ledger: stav na disku, ne v kontextu

Princip: **netriviální task musí jít rozříznout `/clear`-em kdykoliv po cestě.**
To jde jen tehdy, když stav nežije v kontextu, ale na disku — a čerstvá session
ho dostane zadarmo, bez „kde jsme skončili".

`<repo>/docs/session-ledger.md` — píše se **po každém uzavřeném kroku**, ne až
při clearu. `inject_session_ledger.py` ho při startu session automaticky
injektuje do kontextu, pokud je v něm rozdělaný task.

**Ledger je ŠTÍTEK, ne žurnál.** Tohle je tvrdě vynucené a stojí za tím drahá
lekce: ledger si k roli štítku přibral druhou (append-only žurnál nálezů) a
vyrostl na 314 řádků / 23 kB, které **nebyly ani v gitu, ani v kontextu**:

- **neverzované** — je globálně gitignorovaný, `git add -A` ho mlčky přeskočí,
  `git status` mlčí ⇒ „zapsal jsem to do repa" je nepravda, kterou nic nevyvrátí
- **neviditelné** — injektor bere `text[:CAP]`, tedy drží ZAČÁTEK a zahazuje
  konec. Přispívá se na konec ⇒ nejnovější zápisy jsou přesně ty, které se do
  kontextu nikdy nedostanou

Dělba práce, kterou `guard_session_ledger.py` vynucuje:

| soubor | role | git | strop |
|---|---|---|---|
| `docs/session-ledger.md` | štítek — přepisovaný | **gitignored** | ≤ 3 000 zn. |
| `docs/journal/YYYY-MM-DD-<téma>.md` | nález — append-only | **verzovaný** | roste |

Invariant, na kterém to stojí: **`FILE_CAP` (3 000) < `INJECT_CAP` (4 000)**.
Co se do štítku vejde, to injektor celé ukáže ⇒ kategorie „napsané, ale
neviditelné" přestává existovat. Ne zakázaná — **nemožná**. Proto se strop
importuje z `inject_session_ledger.py` a nekopíruje: dvě čísla by driftovala
a díra by se vrátila potichu.

Guard má **dvě fáze**, protože jedna nestačí:

- `PreToolUse` — `Write`/`Edit` umíme složit dopředu ⇒ `deny`, zápis nikdy nedopadne
- `PostToolUse` — čte soubor z disku a porovnává se snapshotem ⇒ chytá heredoc,
  `sed`, `Set-Content`, tedy cestu, kterou se v bypass režimu píše nejčastěji

Šablona ledgeru: `docs/session-ledger-sablona.md`.

### Pilíř 3 — Guardy proti tichému inheritu modelu

**Nejdražší chyba, kterou lze udělat jedním tool callem.** Subagent nebo
workflow agent spawnutý bez explicitního `model` tiše zdědí model hlavní smyčky
— takže „levný průzkumný agent" jede na nejdražším modelu se session effortem.
Naměřeno: sonnet = 4 % útraty, opus + fable = 80 %. Přesně tenhle tichý inherit
je důvod.

- `guard_agent_model_routing.py` — generický `Agent` spawn (`general-purpose`,
  `Explore`, `Plan`) bez `model` → **DENY**. Vědomý inherit se povolí explicitním
  `model: "opus"` — jde o **artefakt vědomé volby**, ne o zákaz.
- `guard_workflow_model_routing.py` — totéž pro `Workflow`, navíc hlídá `effort`.
  Motivace: `/effort max` + 106 agentů = 3,25M tokenů.

**Pozor na `fork`** (`subagent_type: "fork"`, od CC 2.1.232 defaultně zapnutý):
dědí CELOU konverzaci včetně prompt cache a **`model` override IGNORUJE** —
vždycky běží na modelu rodiče. Není to levný subagent; guard ho pouští jen
s prefixem `fork:` v `description`.

**Proč subagenti vůbec pomáhají:** ekonomika není v úspoře tokenů, ale v pásmu.
Subagent startuje na mediánu 29k tokenů (hlavní session 46,9k) a hoří v pásmu
$0,13/call, zatímco hlavní session na 300k hoří za $0,65/call — a tam ten token
zůstane až do `/clear`. Mechanika (logy, git, grep, exploration) proto patří
subagentovi, ne hlavnímu kontextu.

### Pilíř 4 — Guardy proti drahým omylům

- **`guard_spawn_gate.py`** — nespawnuj vlnu, kterou už nedokážeš dosedět.
  `< 150k` ticho · `150–175k` DENY bez markeru vědomé volby · `≥ 175k` tvrdý DENY.
  Brána je záměrně u **nájezdu**, ne u přistání: drain 4 reportů stojí ~2k tokenů
  (nic), ale endgame po něm je 50+ callů hlavní smyčky, každý přeplácí celý
  kontext — to je ta cesta z 280k na 350k. V pásmu 150–175k se dá spawn protlačit
  markerem `[SPAWN-GATE-OK]` v promptu agenta (artefakt vědomé volby); nad 175k
  už marker nepomůže. Guard má výjimku pro zavírání session.
- **`guard_read_before_search.py`** — zastaví čtení celého velkého souboru bez
  `offset`/`limit` a **rovnou v deny hlášce doručí kostru souboru s čísly řádků**
  (3–13 % velikosti originálu, vyrobí se za 1,5 ms). Deny, které nabízí náhradu,
  není šikana. Explicitní `offset`/`limit` vždy projde — to je záměr, ne díra.
- **`guard_heavy_skill_delegation.py`** — mega-skill (např. `claude-api`, ~300k
  tok) se do hlavního kontextu nesmí načíst. Deleguje se na sonnet subagenta
  `skill-reader`, který ho načte do SVÉHO kontextu a vrátí jen odpověď.
- **`guard_runaway_loop.py`** — 5 identických tool callů po sobě → DENY. Model
  degeneroval do smyčky a pálí kontext bez pokroku.

Všechny guardy jsou **fail-open**: jakákoliv chyba ⇒ `exit 0` ⇒ mlčí.
Guard má bránit nehodám, ne práci.

---

## 3. Instalace

### Jako plugin (doporučeno)

V Claude Code:

```
/plugin marketplace add bejek/claude-token-economy
/plugin install token-economy
```

Restartuj Claude Code. Hotovo — hooky běží.

Plugin nesahá na tvůj `~/.claude/settings.json`; plugin hooky se s těmi tvými
**slučují** (union), nepřepisují se.

> ⚠️ **Máš už kit nainstalovaný ručně?** Pak ti po instalaci pluginu poběží
> každý guard **dvakrát** — plugin a tvůj `settings.json` míří na jiné cesty,
> takže je Claude Code nededuplikuje. Před instalací pluginu smaž bloky
> Token Economy z `hooks` v `settings.json` (skripty v `~/.claude/scripts/`
> můžeš nechat, prostě se přestanou volat).

**Zbývá ti udělat dvě věci ručně**, protože do nich plugin z principu nevidí:
prahy podle velikosti tvého kontextového okna (krok 5 v `INSTALL.md`) a sekci
v `CLAUDE.md` (krok 6, předloha je `CLAUDE-md-snippet.md`). Bez druhého jmenovaného
hooky sice fajrují, ale model neví, co s jejich hláškami dělat.

### Ruční instalace

Když nechceš plugin, chceš si vybrat jen některé hooky, nebo máš `python3`
místo `python` (viz předpoklady níž): otevři Claude Code v adresáři kitu a řekni

```
Nainstaluj mi Token Economy Kit podle INSTALL.md.
```

`INSTALL.md` je psaný pro model — kompletní postup včetně dosazení cest,
sloučení `settings.json` a ověření, že hooky fajrují. Čitelný je i pro člověka.

### Předpoklady

- **Python 3 v `PATH` pod jménem `python`.** Hooky jsou čistý stdlib, žádné
  závislosti a žádný `pip install`.
- ⚠️ **Systémy, kde je jen `python3` a ne `python`** (typicky Linux a část
  macOS): plugin verze tam hooky tiše neodpálí, protože příkazy v
  `hooks/hooks.json` volají `python`. Použij ruční instalaci a nahraď `python`
  za `python3`. Ověř si to jedním příkazem: `python --version`.

---

## 4. Denní provoz — jak to vypadá v praxi

1. **Start session** — pokud je v repu rozdělaný ledger, dostaneš ho do kontextu
   automaticky. Nemusíš vysvětlovat, kde jste skončili.
2. **Během práce** — po každém uzavřeném kroku jde jeden řádek do ledgeru.
   Mechanika (logy, git, průzkum) jde na sonnet subagenta.
3. **~175k** — hook řekne FINIŠ. Dotáhne se rozdělaný celek, nic nového se
   neotvírá.
4. **~215k** — hook řekne CLEAR. Dobíhající subagenti se dosedí, výsledky do
   ledgeru, pak `/clear`.
5. **Po `/clear`** — nová session si ledger načte a pokračuje. Kontext je zpátky
   na ~45k, tj. v nejlevnějším pásmu.

Klíčová věta pro model po `/clear` je prostě **„pokračuj"** — zbytek si vezme
z ledgeru.

> ⚠️ Prázdný ledger NENÍ pozvánka najít si práci sám. Když po `/clear` zazní holé
> „pokračuj" bez jména tasku, správná reakce je **zeptat se, který task** — ne
> zorientovat se podle toho, co je na disku nejčerstvější (to bývá cizí scope).

---

## 5. Co si dolaď podle sebe

| kde | co |
|---|---|
| `context_size_warning.py` | `T1/T2/T3` prahy. Nastavené na 1M kontextové okno; při 200k okně je zmenši úměrně (např. 120/150/175k). |
| `guard_spawn_gate.py` | pásma 150k/175k — stejná úvaha |
| `guard_read_before_search.py` | `INDEXED_ROOTS` — vyplň, jen když máš semantický search MCP server. Prázdné = pravidlo „kostra" funguje dál. |
| `guard_heavy_skill_delegation.py` | `HEAVY_SKILLS` — rozšiřuj podle měření, ne podle pocitu |
| `guard_agent_model_routing.py` | názvy modelů v nápovědě routingu |

---

## 6. Metodické varování, ať neměříš nesmysly

Tři pasti, do kterých se při vlastním měření spadne skoro vždy:

1. **`/context` je odhad, ne faktura.** Kategorie se sečtou na 34,1k, reálný call
   byl 44,2k. Umí se splést i ve **znaménku úspory** — u jedné změny hlásil
   „ušetřeno nic", zatímco reálná faktura klesla o 1 780 tok. Na verdikt
   „vyplatilo se to?" použij `usage` z `claude -p ... --output-format json`.
2. **JSONL bez dedupu nafoukne čísla 2,7×.** Claude Code loguje jeden řádek za
   každý content blok, ale všechny nesou tentýž `usage` objekt. Deduplikuj na
   `message.id` + `requestId`.
3. **Obrázky v transkriptu.** Base64 přes znaky/4 vypadá jako „300k tok", reálná
   delta kontextu je medián **2 212 tok/obrázek** (nadhodnocení 22×). Screenshoty
   jsou nevinné.

Bonus pro české uživatele: **čeština má ~1,97 znaku/token** (angličtina ~2,8) ⇒
odhad počítaný s anglickým poměrem podstřelí náklady o 40 %. Zhruba platí:
**tokeny ≈ znaky ÷ 2**.

Nástroj `scripts/context_attribution.py` rozpadne hotové session podle toho, co
kontext skutečně sežralo (tool výsledky / assistant / user / remindery):

```bash
python scripts/context_attribution.py 12
```

---

## 7. Co v týhle sadě NENÍ

Vědomě vynechané, protože je to svázané s konkrétním prostředím: kalendář
závazků, Telegram notifikace, orchestrační vlny, semantické hledání, closing
ritual, statusline. Sada je jádro, které funguje samo o sobě.

Detailní naměřená data a metodika: `docs/mereni.md`.
