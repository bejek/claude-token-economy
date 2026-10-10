# První reálný běh `plugin eval` — gate otevřená, 3 vady v casech, 0 v pluginu

**Datum:** 2026-10-10 · **Task:** #1460 · **CLI:** 2.1.296 · **Cena:** ~$0,7 / suite, ~4 min

## Gate
Zavřená 09-11 (2.1.268), na 2.1.296 **otevřená**: `claude plugin eval .` už nehlásí
„early access", ale chce trust → `--trust-plugin`. Pro naši suite nutné ještě
`--scaffold` (default vypnutý) a `--no-publish`. Doporučené volání:
`claude plugin eval . --no-publish --trust-plugin --scaffold --max-cost-usd 5`.

## Co se při prvním běhu ukázalo
Plugin funguje (SessionStart i PreToolUse hooky se v evalu načítají), **vadné byly cases**:

1. **`allowed_tools` nezakazuje Grep.** Je to grant pro gated nástroje. Model v
   `read-large-file` použil `Grep -A40` (správně, levně) a Read guard neměl šanci.
   → zadání casu teď říká „čti nástrojem Read".
2. **Fixture měl 2 407 řádků** = přes vestavěný limit Readu (2000 ř.), takže „use offset"
   napsal i holý Claude Code a baseline vycházela stejně (Δ 0).
3. **Kostra 43 % originálu** (limit 25 %, `MAX_SKELETON_RATIO`) → u fixture z 400
   jednořádkových funkcí rule A guardu nezabere. Fixture je teď 30 funkcí × 40 řádků
   (1 237 ř., kostra 7,5 %).
4. **`guard-fired` regex nad `trace` neměřil nic:** trace nenese text deny hlášky z
   PreToolUse hooku (jen SessionStart hook eventy + tool volání). Padal v obou
   armech i tam, kde guard prokazatelně zabral. Gradery smazány; účinek guardu
   se pozná chováním (`read-was-targeted`).

## Výsledek po opravách (runs: ledger 3, ostatní 2)
| case | with | without | Δ |
|---|---|---|---|
| ledger-survives-clear | 1,00 | 0,00 | **+1,00** (3/3 vs 0/3) |
| read-large-file-needs-offset | 1,00 | 0,75 | +0,25 (with: vždy cílený Read) |
| agent-spawn-needs-explicit-model | 0,0–0,5 | 0,25–0,5 | **nerozhodnuto** |

`ledger-survives-clear` je jediný čistý důkaz účinnosti (haiku bez pluginu
neví, na čem se pracuje; s ním ano). `read-large-file` má správný směr, ale n=2.

## Otevřené
- **`agent-spawn` je flaky:** tři běhy téhož zadání daly 3 různé výsledky, model
  někdy `Agent` vůbec nezavolá (turns=1) a judge pak nemá co hodnotit. Chce víc
  běhů (`runs: 5+`) a/nebo grader na `tool_used: Agent` místo LLM judge nad prózou.
- Žádný case nepokrývá runaway loop, spawn gate ani context warning.
- `--keep-temp` na Windows nezapečetí adresář (varování CLI) a trace se jinak po
  běhu maže → debug přes `--keep-temp`, pak `rm -rf` temp adresáře.
