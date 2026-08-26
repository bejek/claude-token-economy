# Token ekonomie (TVRDÉ PRAVIDLO)

> Připoj tenhle blok na konec `~/.claude/CLAUDE.md`. Hooky vynucují meze,
> ale pravidla chování musí model dostat v instrukcích — tohle je druhá
> půlka systému.

- **Velikost session je jediná páka.** Kontext je kumulativní a platí se znovu
  každým callem; cena je plochá do 100k a nad ní se láme (500k+ = 7,6× proti
  pásmu do 50k). Session s peakem >300k stojí medián 27× víc než session
  s peakem <150k.
- **Kontext nevidím** — nemám živý čítač. Hlásí ho hook `context_size_warning`:
  **175k FINIŠ** = dotáhni rozdělaný celek, žádná nová fronta (nový task, další
  kolo review, deploy = nová session) · **215k CLEAR** = dočkat běžící
  subagenty → zapsat jejich výsledky do ledgeru → nabídnout `/clear` ·
  **strop 230k**. Nad 250k protokol selhal: zapiš, stop, žádná „ještě jedna věc".
- **Ledger je default pro každý netriviální task:** `<repo>/docs/session-ledger.md`,
  zápis **po každém uzavřeném kroku**, ne až při clearu. Cíl je jediný: aby šlo
  dát `/clear` kdykoliv po cestě a nic se neztratilo.
- **Ledger je ŠTÍTEK, ne žurnál.** Gitignorovaný, přepisovaný, ≤ 3 000 znaků,
  žádné `##` sekce — vynucuje `guard_session_ledger.py`. Trvalý nález (měření,
  root cause, co bylo vyvráceno, zavržená alternativa) patří do
  `<repo>/docs/journal/YYYY-MM-DD-<téma>.md`, který je **verzovaný**; ukazatel
  na něj jde do pole `ŽURNÁL:` (`—` = nic trvalého).
  ⚠️ Protože je ledger gitignorovaný, `git add -A` ho mlčky přeskočí. Než
  prohlásíš, že je něco „zapsané v repu", ověř `git ls-files` nebo
  `git check-ignore -v <cesta>`.
- **Mechanika patří subagentovi, ne hlavnímu kontextu.** Logy, git, grep,
  exploration, čtení dlouhých docs → sonnet subagent s třířádkovým promptem.
  Ekonomika není v úspoře tokenů, ale v pásmu: subagent hoří ve 30–50k
  ($0,13/call), hlavní session ve 300k ($0,65/call) — a tam ten token zůstane
  až do `/clear`.
- **Model a effort patří do každého spawnu explicitně.** Subagent bez `model`
  tiše zdědí model hlavní smyčky, takže „levný průzkumný agent" jede na tom
  nejdražším. Guardy tenhle tichý inherit blokují; vědomý inherit povol
  explicitním parametrem, ne obcházením guardu.
- **`fork` NENÍ levný subagent.** Dědí celou konverzaci včetně cache a `model`
  override ignoruje — vždy běží na modelu rodiče. Použij ho jen tam, kde je
  celá konverzace opravdu potřeba (post-mortem, recap), ne na mechaniku.
- **Guard DENY není zákaz práce.** Znamená chybějící parametr nebo plný kontext.
  Přečti si důvod a změň postup — neobcházej ho jinou cestou k témuž.
- **Nečti celé velké soubory.** `Read` s `offset` + `limit`, cílený `Grep`, nebo
  kostra, kterou ti guard nabídne v deny hlášce. Výsledek `Read` nezmizí po
  použití — v hlavní session se pošle znovu medián 134×.
- Po `/clear` navazuj z ledgeru. **Prázdný ledger ale není pozvánka najít si
  práci sám** — když zazní holé „pokračuj" bez jména tasku, zeptej se, který
  task to je. Neorientuj se podle toho, co je na disku nejčerstvější.

## Šablona ledgeru

Drž pořadí polí — soubor se při injektáži ořezává od konce.

```markdown
# TASK <název> — <repo/větev>
STAV: běží | čeká-na-rozhodnutí | uzavřeno — <poznámka až za pomlčkou>
NEXT: <jediná nejbližší akce>
HOTOVO: <odrážky, jen co příští session NESMÍ dělat znovu — commity SHA, soubory>
BLOKERY: <co brzdí / co příští session NESMÍ> (prázdné = žádné)
ROZHODNUTÍ: <co čeká na člověka> (prázdné = nic nečeká)
NÁLEZY: <viděl jsem a nespravil — pointer, ne próza>
ŽURNÁL: docs/journal/YYYY-MM-DD-<téma>.md   (nebo — = žádný trvalý nález)
```

Uzavřenost se čte z **prvního segmentu** za `STAV:` — `STAV: uzavřeno — čeká
review` je uzavřeno, popisné poznámky patří až za pomlčku.
