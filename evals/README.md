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
claude plugin eval .
```

Cílem je **cesta k pluginu**, ne k `evals/` — tím se zapne baseline arm
a každý case se spustí dvakrát, s pluginem a bez něj. To srovnání je celá
pointa; `claude plugin eval ./evals` by ho neudělalo.

JSON report pro CI:

```bash
claude plugin eval . --json eval-results.json --no-publish
```

Exit kód 0 = všechny casy nad prahem, 1 = pod prahem nebo chyba načtení,
2 = částečný běh (strop nákladů, auth), 130/143 = přerušeno.

## Než na tom postavíš CI

⚠️ **`claude plugin eval` je early access a je zapínaný per organizace.**
Když ho zapnutý nemáš, příkaz vypíše `plugin eval is currently in early access`
a skončí s kódem 1. Suite je proto napsaná podle schématu, ale **nebyla
spuštěna** — než ji zapojíš do CI, pusť ji jednou lokálně a případné odchylky
schématu oprav tady.

## Jak číst výsledek

U casů 2 a 3 jsou vždy dva druhy graderů a je důležité je nesloučit:

- **`guard-fired`** — fajrnul hook vůbec? Tohle je test pluginu.
- **`answer-is-correct` / `model-was-chosen`** — je výsledek pořád správně?
  Tohle je pojistka proti falešnému vítězství. Guard, který ušetří tokeny za
  cenu horší odpovědi, není úspora. Kdyby tenhle grader padal jen v `with`
  armu, je vada v guardu, ne v evalu.
