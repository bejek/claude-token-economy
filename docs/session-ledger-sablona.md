# TASK <název tasku> — <repo/větev>
STAV: běží — <poznámka až za pomlčkou>
NEXT: <jediná nejbližší akce, konkrétně>
HOTOVO:
- <co příští session NESMÍ dělat znovu — commit SHA, soubor, rozhodnutí>
BLOKERY: <co brzdí / co příští session nesmí>
ROZHODNUTÍ: <co čeká na člověka>
NÁLEZY: <viděl jsem a nespravil — pointer, ne próza>
ŽURNÁL: —

<!--
JAK TENHLE SOUBOR POUŽÍVAT
==========================
Umísti do <repo>/docs/session-ledger.md. Musí být gitignorovaný.

PRAVIDLA (vynucuje guard_session_ledger.py):
  * ≤ 3 000 znaků
  * žádné vlastní `##` sekce — tohle je štítek, ne dokument
  * přepisuje se, nepřipisuje

PROČ STROP: injektor bere text[:4000], tedy drží ZAČÁTEK a zahazuje konec.
Kdybys připisoval na konec, nejnovější zápisy by se do kontextu nikdy
nedostaly — zaplatil bys za text, který nikdo nikdy nepřečte. Invariant
FILE_CAP (3 000) < INJECT_CAP (4 000) dělá tuhle kategorii NEMOŽNOU.

POŘADÍ POLÍ JE ZÁMĚRNÉ: ořezává se od konce, takže co je nahoře, přežije.

KDY ZAPISOVAT: po každém uzavřeném kroku, ne až při /clear. Cíl je, aby šlo
dát /clear kdykoliv po cestě.

STAV: uzavřenost se čte z PRVNÍHO segmentu (před ` — `, ` - `, `|`, `(`).
  `STAV: uzavřeno — zbývá review`   -> uzavřeno, injektor mlčí
  `STAV: běží — čeká na CI`         -> běží, injektuje se
Hodnoty, po kterých injektor mlčí: uzavřeno / hotovo / done / closed.

ŽURNÁL: trvalý nález (měření, root cause, co bylo vyvráceno, zavržená
alternativa) nepatří sem, ale do VERZOVANÉHO
<repo>/docs/journal/YYYY-MM-DD-<téma>.md. Sem jen ukazatel; `—` = nic trvalého.

⚠️ Soubor je gitignorovaný, takže `git add -A` ho mlčky přeskočí a `git status`
mlčí. Než prohlásíš, že je něco „zapsané v repu", ověř `git ls-files` nebo
`git check-ignore -v <cesta>`.

Tenhle komentář ze svého ledgeru smaž — počítá se do stropu 3 000 znaků.
-->
