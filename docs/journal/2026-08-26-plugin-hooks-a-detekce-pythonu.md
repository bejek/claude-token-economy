# Jak se v Claude Code pluginu dělají hooky (a proč `command -v python3` lže)

2026-08-26 · nálezy z přebalení Token Economy Kitu na plugin (v0.1.0 → v0.2.0)

Všechno níž je ověřené spuštěním na Windows 11 + Claude Code, ne převzaté
z dokumentace. Kde je zdrojem dokumentace, je to označené.

## 1. Tvar pluginu s hooky

```
<plugin>/
├── .claude-plugin/
│   ├── plugin.json          ← JEN tenhle soubor sem patří
│   └── marketplace.json     ← v monorepu (plugin v kořeni repa, "source": "./")
├── hooks/hooks.json         ← hooky jsou na KOŘENI, ne v .claude-plugin/
├── scripts/
└── bin/
```

Ověřeno `claude plugin validate` (validuje zvlášť `plugin.json` a zvlášť
marketplace manifest — cesta k adresáři validuje marketplace).

**Dva omyly, které validátor odhalil:**

- `metadata.repository` v `marketplace.json` **neexistuje** →
  `Unknown field 'repository'. Claude Code ignores it at load time.`
- `plugins[].author` musí být **objekt** (`{name, url}`), ne string →
  `Invalid input: expected object, received string`

Užitečný vedlejšák: validátor u neznámého klíče **varuje**. Když tedy
`experimental.evals` prošlo bez varování, je to důkaz, že ten klíč zná —
mlčení validátoru je informace.

## 2. `${CLAUDE_PLUGIN_ROOT}` funguje, i na Windows

Ověřeno probe hookem: dočasný `UserPromptSubmit` hook injektoval do kontextu
absolutní cestu k sobě samému, model ji vypsal.

```json
"command": "sh \"${CLAUDE_PLUGIN_ROOT}/bin/hook.sh\" guard_x.py"
```

Expanduje se i uvnitř uvozovkovaného řetězce.

**Metodická poznámka:** `--debug` výstup **není vidět v `-p` (headless) režimu**.
Ověřovat fajrování hooku debug logem tedy nejde; probe hook, který si nechá
vypsat vlastní stav modelem, je spolehlivější a levnější.

## 3. Hooky běží pod POSIX shellem i na Windows

```
uname -s  →  MINGW64_NT-10.0-26200
```

To je zásadní pro portabilitu: jeden `sh` launcher pokryje Windows, macOS
i Linux. Není potřeba větvit podle platformy.

## 4. `python3` na Windows je atrapa z Microsoft Storu

Tohle je ta past, kvůli které existuje `bin/hook.sh`.

```
command -v python3  →  /c/Users/<user>/AppData/Local/Microsoft/WindowsApps/python3
command -v python   →  /c/Users/<user>/AppData/Local/Python/pythoncore-3.13-64/python
```

`WindowsApps/python3` je **App Execution Alias** — 0bajtový reparse point, který
žádný Python nespustí. `command -v` ho najde a vrátí platnou cestu, takže
obvyklý recept „preferuj `python3`, je to modernější" na Windows plugin **tiše
zabije**: hooky se budou spouštět, okamžitě padat a fail-open je propustí dál.

Změřeno:

| kandidát | `-c "import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)"` |
|---|---|
| `WindowsApps/python3` (atrapa) | **exit 49** |
| `python` (reálný, 3.13) | exit 0 |
| `py` | exit 0 |

**Závěr: interpret se ověřuje SPUŠTĚNÍM, ne přítomností.** Pořadí
`python` → `python3` → `py`; kontrola verze zároveň odfiltruje python2 na
starších Linuxech, kde `python` ještě existuje.

(Bonus: spuštění atrapy **s argumentem** Store neotevře, jen vypíše hlášku
a skončí nenulově. Store otevírá až holé zavolání bez argumentů.)

## 5. Plugin hooky se s uživatelskými slučují

Dokumentace: plugin hooky se s `~/.claude/settings.json` **mergují (union)**,
nepřepisují se. Deduplikace je na shodě příkazu — a protože plugin míří na
`${CLAUDE_PLUGIN_ROOT}/…` a ruční instalace na `~/.claude/scripts/…`, jsou to
dva různé příkazy a **oba se spustí**. Kdo má kit nainstalovaný ručně a přidá
plugin, fajruje mu každý guard dvakrát.

## 6. Deny prochází launcherem beze změny

Guardy nevrací deny exit kódem, ale JSONem na stdout
(`{"hookSpecificOutput": {"permissionDecision": "deny", …}}`, exit 0).
`exec "$PY" "$SCRIPT"` v launcheru ho propustí nedotčený — ověřeno.
Kdyby se rozhodnutí guardu ztratilo, byly by z guardů jen ozdoby, takže
tenhle test patří do smoke suite natrvalo (`tests/smoke.sh`, sekce 3).

## 7. Co zbývá otevřené

`claude plugin eval` je **early access, zapínaný per organizace**. Suite
v `evals/` je napsaná podle schématu z offline reference, ale **nikdy
neproběhla** — první reálný běh může chtít opravy `case.yaml` i graderů.
Do té doby je to nejlépe zdokumentovaná nespuštěná věc v repu.

## 8. Dvě chyby, které málem odešly

- Git chtěl uložit `.sh` s CRLF → `bad interpreter: /bin/sh^M` na Linuxu a v CI.
  Řeší `.gitattributes` (`*.sh text eol=lf`) + exec bit přes
  `git update-index --chmod=+x`.
- Sekce smoke testu tiše **procházela naprázdno**, protože grep nesedl na
  escapované uvozovky v JSONu. Test, který netestuje nic a hlásí OK, je horší
  než žádný — proto tam je pojistka „prázdný seznam = fail".
