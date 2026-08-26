---
type: regex
pattern: "Stripe"
flags: "i"
match: contains
target: last_message
---

Odpověď musí jmenovat rozdělaný task ze session ledgeru (migrace fakturace
na Stripe). Bez pluginu model ledger nevidí — nemá tooly, kterými by si ho
přečetl — takže tenhle grader je přesně to místo, kde se `with` a `without`
arm rozejdou.
