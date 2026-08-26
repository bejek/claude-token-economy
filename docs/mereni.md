# Naměřená data — proč ta sada vypadá takhle

Všechno níž je změřené z reálného provozu Claude Code (`~/.claude/projects/**/*.jsonl`),
období červenec–srpen 2026. Žádný odhad, žádná analogie z jiného nástroje.

---

## 1. Cena callu podle velikosti kontextu

**n = 88 612 unikátních assistant callů**, 3 980 souborů, 2026-07-06 → 08-05.

| kontext | Ø cena / call | násobek vůči 0–50k |
|---|---|---|
| 0–50k | $0,13 | 1,0× |
| 50–100k | $0,14 | 1,1× |
| 100–150k | $0,24 | 1,9× |
| 150–200k | $0,35 | 2,7× |
| 200–300k | $0,48 | 3,7× |
| 300–400k | $0,65 | 5,0× |
| 400–500k | $0,80 | 6,2× |
| 500k+ | $0,98 | **7,6×** |

**Cena je plochá do 100k, pak se láme.** Tohle je jediný graf, který je potřeba
si zapamatovat — celá strategie z něj plyne.

**Distribuce útraty** (749 top-level konverzací): nejdražších 10 % = **39 %**
spotřeby, nejdražších 20 % = 61 %. Medián $12,60, průměr $23,48. Nejdražší jedna
konverzace: $215,83 / 259 callů / kontext přes 650k.

**Startovní kontext:** medián **46 391 tokenů** na prvním callu session.
`CLAUDE.md` + `MEMORY.md` z toho dělají jen **7 %** — zbytek je system prompt,
definice nástrojů, popisy subagentů a MCP instrukce. **Škrtat v `CLAUDE.md` je
proto slabá páka.**

---

## 2. Subagent nestartuje na nule

Dedup na `message.id` + `requestId`, sidechainy grupované přes `parentUuid`.

| | n | medián | p25 | p75 |
|---|---|---|---|---|
| Subagent (`isSidechain`) | 3 078 | **29 007** | 26 536 | 32 759 |
| Hlavní session | 750 | **46 928** | 44 313 | 49 985 |

Subagent **nedědí konverzaci, ale dědí všechno ostatní**: system prompt, definice
nástrojů, MCP instrukce i `CLAUDE.md`. `Explore` a `Plan` jsou podle dokumentace
jediné, které `CLAUDE.md` a git status vynechávají — proto jsou nejlevnější a na
hledání se má sahat po nich.

**Ekonomika není v úspoře tokenů, ale v pásmu:** subagent hoří ve 30–50k
($0,13/call), hlavní session ve 300k ($0,65/call) — a tam ten token zůstane až
do `/clear`.

### Fork je výjimka ze všeho výše

`subagent_type: "fork"` (od CC 2.1.232 defaultně zapnutý) dědí **celou
konverzaci + prompt cache** a **`model` override IGNORUJE** — vždycky běží na
modelu rodiče, effort dědí ze session. Nepadá tedy do pásma 30–50k, ale do pásma
hlavní session. Cache-read ho zlevňuje ~10× proti plnému inputu, proti
scopovanému sonnet subagentovi je pořád řádově dráž.

- **Dává smysl:** úkol potřebuje celou konverzaci a převyprávění by bylo ztrátové
  (post-mortem, recap) · hlučný tool output má zůstat mimo hlavní kontext, ale
  agent musí rozumět všemu, co předcházelo · větvení téhož stavu.
- **Nedává:** mechanika, logy, git, grep, testy, docs, exploration → sonnet
  s třířádkovým promptem.

### Popisy subagentů v system promptu

Do kontextu jde **jen `description` z frontmatteru, ne tělo souboru.** Naměřeno
na 20 agentech: 4 800 znaků popisů ≈ **1 333 tok**. Největší soubor (21 kB) má
popis na 218 znaků ⇒ **škrtat podle velikosti souboru je nesmysl, rozhoduje
počet agentů a délka popisu.**

Kdo se fakt používá:

```bash
grep -oh '"subagent_type":"[^"]*"' -r ~/.claude/projects | sort | uniq -c | sort -rn
```

Vypnutí bez mazání: `mv agent.md agent.md.bak` — CC čte z `~/.claude/agents/`
jen `*.md`.

---

## 3. Z čeho je startovní kontext

Změřeno `/context` v běžící interaktivní session (Opus, 1M okno). Reálný první
call téže session podle transkriptu = **44 249 tok**.

| kategorie | tok | ovlivnitelné? |
|---|---|---|
| System tools (16 aktivních definic) | **23 000** | ne |
| System prompt | 4 100 | ne |
| Index skillů (37) | 3 300 | `skillOverrides`, odinstalovat pluginy |
| Custom agents (20, jen `description`) | 1 900 | rename na `.bak` |
| Memory files (`CLAUDE.md`) | 1 800 | ano |
| MCP nástroje (46 z 5 serverů) | **0** | deferred — ale viz níž |
| nepřiřazeno `/context`em | ~10 000 | — |

**Deferred nástroje** (k dispozici, ale neplatí se, dokud si je model nevyžádá):
MCP 11 800 + systémové 17 000 = **28 800**. Bez deferralu by start byl 73k místo
44k ⇒ **update Claude Code je někdy největší optimalizace, co existuje.**

### Deferred ≠ zdarma

Řádek „MCP nástroje = 0" platí jen na *schémata*. Server si navíc sám vlepuje do
promptu `instructions` z `initialize` a **názvy toolů** v deferred listingu — a
obojí **za každou instanci zvlášť**. Čtyři instance téhož serveru = čtyři kopie
téhož návodu. Úklid duplicit: **−3,8k tok (−8,2 %)** startovního kontextu.

### `skillOverrides` má čtyři hodnoty

Zdroj = binárka CC 2.1.233:

> `"name-only"` lists the skill without its description; `"user-invocable-only"`
> hides it from the model but keeps `/name`; `"off"` hides it from both.
> Absent = on.

⇒ **`off` je skoro vždy blbá volba.** `user-invocable-only` ušetří stejně a
slash příkaz dál funguje. `name-only` je kompromis, když má model o skillu vědět,
ale jeho dlouhý trigger-popis je předražený.

**Plugin skilly se přes `skillOverrides` vypnout NEDAJÍ** — override se ani
nepřečte. Jdou sundat jen vypnutím celého pluginu.

Naměřený úklid: 12 nepoužívaných agentů → `.bak` = **−986 tok**, plus
`skillOverrides` (22 položek) = **−1 780 tok**, celkem **−2 751 (−8,9 %)**.

### Úzká složka NEZMENŠÍ startovní kontext

| cwd | celkem | souborů v dosahu |
|---|---|---|
| rodič všeho | 24,7k | 144 970 |
| konkrétní projekt | **24,0k** | **5 886** |

Rozdíl jsou **3 % a jde oběma směry**. Co ale platí: kupka sena je 25× menší,
`.gitignore` se aplikuje jen v repu, a špatné cwd znamená špatný projektový
`CLAUDE.md` a špatný `settings.json` ⇒ model si kontext doplní čtením, což je
nejdražší cesta.

---

## 4. Read je nejdražší běžný úkon

Naměřeno na distribuci `Read` volání:

- medián **násobiče**: **134×** v hlavní session, **25×** v subagentovi
  (kolikrát se výsledek pošle znovu)
- `Read` výsledky dělají **26,1 %** kontextové spotřeby hlavní session
  a **39,5 %** u subagentů
- sklizeň guardu (volání nad prahem, bez `offset`/`limit`) = **5,6 %** veškeré
  spotřeby při ~6 viditelných zásazích denně

**Kostra místo celého souboru:** 3–13 % velikosti originálu (medián 524 tok na
1 073 reálných souborech), vyrobí se za **1,5 ms**. Původní návrh — shrnutí
z Haiku — stál 33 s a 2 368 tok.

Čísla řádků jsou v kostře stejně důležitá jako obsah: bez nich neumožní cílený
`Read` a deny se mění v čistou ztrátu.

**Pomer znaků na token je naměřený, ne odhadnutý:** **1,85** na 17 900 párech
z transkriptu. `chars/4` je pro tenhle korpus lež o 50 %.

`Read` má vlastní strop ~25 000 tok (`truncatedByTokenCap`) — nad ním se celý
soubor stejně nedozvíš, jen za něj zaplatíš.

---

## 5. Kam skutečně tečou peníze

Audit okna 08-06 → 08-20 ($4 775, ~$318/den):

1. **Cache read $2 796 (58,5 %)** — daň kontext × cally. Cally nad 150k kontextu
   = **33 % útraty**. Sessions s peakem >200k: 137 ze 436.
2. **Subagenti $2 146 (44,9 %)**, z toho drahé modely $1 215.
3. **Adverzární reviews $741 (15,5 %)**.

**Tichý inherit modelu:** sonnet = 4 % útraty, opus + fable = 80 %. Součástí
auditu byl i objevený leak — implementátoři běžící na nejdražším modelu jen
proto, že to nikdo explicitně nenastavil ($207 za dva týdny na jedné roli).

---

## 6. Metodické pasti (přečti, než začneš měřit sám)

### `/context` je odhad, ne faktura

Kategorie se sečtou na 34,1k, reálný call byl 44,2k. Do žádné kategorie nejdou
MCP `instructions`, výstup `SessionStart` hooků, index paměti, systémové
remindery ani první user prompt.

**Horší: umí se splést i ve znaménku úspory.** U jedné změny hlásil `Skills`
2,9k→1,2k, ale současně `System tools` 12,1k→13,8k ⇒ „ušetřeno nic". Reálná
faktura přitom klesla o **1 780 tok**. Obě čísla se opakovala napříč běhy, takže
to nebyl šum.

⇒ Na **rozpad** (co je čí kategorie) `/context` ano. Na **verdikt „vyplatilo se
to?"** nikdy — použij `usage` z `claude -p ... --output-format json`
(`input + cache_creation + cache_read` prvního callu).

### JSONL bez dedupu nafoukne čísla 2,7×

Claude Code loguje **jeden řádek za každý content blok** assistant zprávy, ale
všechny nesou **tentýž `usage` objekt**. Bez deduplikace na `message.id` +
`requestId` vyjdou čísla nafouklá 2,7× (58,6 % řádků jsou duplicity).

### Obrázky vypadají 22× dráž, než jsou

Base64 v JSONL dělá z PNG „300k tok" přes znaky/4. Reálná delta kontextu
(ověřená `usage` deltou před/po) je medián **2 212 tok/obrázek**. Screenshoty
jsou nevinné.

### Čeština je tokenizačně drahá

Naměřený poměr: **~1,97 znaku/token** (angličtina ~2,8) ⇒ odhad s anglickým
poměrem podstřelí náklady o 40 %. Nejhorší je čeština bez diakritiky nasekaná
`snake_case` identifikátory a backtickovanými cestami. Zhruba: **tokeny ≈ znaky ÷ 2**.

### Nesahej na běžící session

„Vezmi nejnovější `.jsonl`" sáhne na session, do které se právě zapisuje, a
vrátí její čísla dvakrát. `--output-format json` vrací `usage` i `session_id`
rovnou.

### Napřed měř, pak dělej forenziku

Reálná epizoda: příčinu regrese našel `/context all` + grep configu za pár minut.
Tři subagenti (~250k tok) předtím vyprodukovali čtyři chybné hypotézy a jednu
halucinovanou sadu settings klíčů. **U vlastního setupu měř nejdřív, teprve
potom vyšetřuj.**

---

## 7. Jak si to změřit u sebe

Rozpad hotových session podle toho, co sežralo kontext:

```bash
python scripts/context_attribution.py 12
```

Startovní kontext bez TUI (`/context` funguje i headless a vrací markdown):

```bash
claude -p "/context"
```

⚠️ **Print mode podstřeluje interaktivní session o ~16k**, protože nenačte
interaktivní nástroje. Na absolutní čísla o vlastním setupu jen interaktivní
`/context`; headless je dobrý na poměry.

⚠️ Změny v system promptu se projeví **až v nové session** — ověřuj po `/clear`,
jinak měříš starý prompt.
