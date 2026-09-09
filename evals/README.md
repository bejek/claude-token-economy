# Eval suite

Tři casy, které mají prokázat, že plugin **mění chování modelu** — ne jen že
se hooky spustí bez chyby.

| Case | Co dokazuje | Proč to baseline arm neumí |
|---|---|---|
| `ledger-survives-clear` | SessionStart injektuje rozdělaný task do kontextu | Case běží s `allowed_tools: []`, takže bez injekce se model o tasku nemá jak dozvědět |
| `read-large-file-needs-offset` | PreToolUse odkloní slepé čtení velkého souboru na cílený `Read` s `offset` | Bez guardu je běžné chování jeden `Read` bez parametrů za ~26 000 tokenů |
| `agent-spawn-needs-explicit-model` | PreToolUse vynutí vědomou volbu modelu pro subagenta | Bez guardu subagent tiše zdědí model hlavní smyčky |

## Spuštění

```bash
claude plugin eval . --scaffold
```

Dvě věci na tom příkazu nejsou volitelné:

- **Cílem je cesta k pluginu**, ne k `evals/` — tím se zapne baseline arm
  a každý case se spustí dvakrát, s pluginem a bez něj. To srovnání je celá
  pointa; `claude plugin eval ./evals` by ho neudělalo.
- **`--scaffold` musíš dát ručně.** Scaffold skripty jsou defaultně VYPNUTÉ
  (CLI je bere jako „cizí bash, co běží pod tvým účtem"). Bez toho flagu
  case `ledger-survives-clear` nedostane ledger a `read-large-file-needs-offset`
  nedostane velký soubor — oba pak selžou na chybějící fixture, ne na pluginu.

JSON report pro CI:

```bash
claude plugin eval . --scaffold --json eval-results.json --no-publish
```

Exit kód 0 = všechny casy nad prahem, 1 = pod prahem nebo chyba načtení,
2 = částečný běh (strop nákladů, auth), 130/143 = přerušeno.

## Než na tom postavíš CI

⚠️ **`claude plugin eval` je early access a je zapínaný per organizace.**
Když ho zapnutý nemáš, příkaz vypíše `plugin eval is currently in early access`
a skončí s kódem 1. Platí to i pro `claude plugin eval init` — nejde tedy ani
vygenerovat referenční skeleton.

**Stav k 2026-09-09 (CLI 2.1.266):** brána je pořád zavřená, suite tím pádem
**nikdy neběžela**. Schéma níž ale už není odhad — je vytažené přímo z parseru
v binárce (`case.yaml` zod schéma, prose loader `prompt.md` + `graders/`,
merge obou). Odchylky proti němu jsou opravené. Co zbývá ověřit reálným během:
chování `allowed_tools: []` (očekáváme „žádné tooly", ne „výchozí sada")
a to, že scaffold `#!/bin/sh` projde i na Windows hostiteli.

### Schéma case.yaml (ověřené proti CLI 2.1.266)

Case složka smí být zapsaná třemi způsoby a všechny tři se slučují do stejného
objektu: samotný `case.yaml`, samotný `prompt.md` + `graders/*.md`, nebo obojí
(tzv. *mixed* — a to je právě náš případ).

```yaml
schema_version: "1.1"   # POVINNÉ, pokud case.yaml existuje (default se
                        # dosazuje jen tam, kde case.yaml chybí)
name: <string>          # POVINNÉ
description: <string>   # volitelné
tags: [...]             # default []
plugins: [...]          # volitelné
runs: <1..50>           # default 3
expected_outcome: <string>   # volitelné
context:                     # jediné místo, kde tohle jde říct —
  scaffold_script: ./x.sh    # prompt.md frontmatter tyhle klíče NEZNÁ
  history_file: ...
  add_dirs: [...]
execution:                   # POZOR: tyhle klíče patří SEM, ne nahoru
  prompt: |
    ...
  model: <string>
  max_turns: <1..200>        # default 10
  timeout_seconds: <1..3600> # default 300
  allowed_tools: [...]       # default []
  append_system_prompt: <string>
  env: {...}
```

Klíče navíc na horní úrovni se **tiše zahodí** — proto se `prompt:` napsaný
nahoru neprojeví jako chyba, ale jako case s prázdným promptem.

### Schéma graderů

Soubor `graders/<jméno>.md`, **jméno grader** se bere z názvu souboru (klíč
`name` do frontmatteru nepiš). Frontmatter je `.strict()` — neznámý klíč case
shodí. Typy a jejich klíče:

| `type` | klíče |
|---|---|
| `regex` | `pattern`, `flags`, `match` (`contains` \| `not_contains` \| `count:N`), `target` |
| `tool_used` | `tool`, `input_match`, `min`, `max` — **žádný `target`** |
| `tool_order` | `before`, `after` |
| `file_exists` | `path`, `exists` |
| `llm` | `criteria`, `focus` |
| `baseline` | `baseline_file`, `criteria` |

Společné pro všechny: `weight` (kladné, default 1) a `arm`
(`with-only` \| `both`). Povolené `target`/`focus`: `last_message` (default),
`trace`, `files`, `mock_calls`, nebo `{source: file, path: ...}`.

Když u `llm`/`baseline` vynecháš `criteria` (resp. u `regex` `pattern`),
použije se místo něj **tělo markdownu**. My klíče vyplňujeme explicitně, takže
tělo je jen komentář pro člověka.

## Jak číst výsledek

U casů 2 a 3 jsou vždy dva druhy graderů a je důležité je nesloučit:

- **`guard-fired`** — fajrnul hook vůbec? Tohle je test pluginu.
- **`answer-is-correct` / `model-was-chosen`** — je výsledek pořád správně?
  Tohle je pojistka proti falešnému vítězství. Guard, který ušetří tokeny za
  cenu horší odpovědi, není úspora. Kdyby tenhle grader padal jen v `with`
  armu, je vada v guardu, ne v evalu.

### Proč `guard-fired` NENÍ označený `arm: with-only`

Nabízí se to: grader, co bez pluginu nemůže projít, vypadá jako klasický
„plugin-fired indikátor". Schválně ho tak neoznačujeme.

`arm: with-only` znamená **vyřadit ze skóre** — v `with` armu se grader
vyhodnotí, ale nezapočítá (`scored: false`), a v baseline armu se **vůbec
nespustí**. Tím by z reportu zmizela přesně ta půlka, kvůli které suite
existuje: doklad, že bez pluginu to nejde.

Riziko, že nám baseline arm shodí exit kód, přitom neexistuje — `--threshold`
(default 1.0) se poměřuje se skóre **`with` armu**. Baseline se reportuje
vedle jako delta. Takže: nechat `arm` nevyplněný, ať se guard-fired skóruje
v obou armech a delta je vidět.

Automaticky se jako with-only chová jen idiom `type: tool_used` + `tool: Skill`
(a `mock_calls` gradery) — na regex nad `trace` se to nevztahuje.
