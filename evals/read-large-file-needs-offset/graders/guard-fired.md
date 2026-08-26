---
type: regex
pattern: "(offset|kostr|skeleton)"
flags: "i"
match: contains
target: trace
---

Ve stopě běhu musí být vidět reakce guardu — deny hláška nabízí kostru souboru
a cílený `Read` s offsetem. V baseline armu (bez pluginu) se v trace neobjeví,
protože žádný guard nefajruje.
