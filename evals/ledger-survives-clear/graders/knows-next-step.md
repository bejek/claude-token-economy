---
type: llm
criteria: |
  Odpověď musí uvést, že dalším krokem je idempotence u refundů
  (idempotency key v refund_handleru), tedy pole NEXT ze session ledgeru.

  PASS: odpověď jmenuje idempotenci/idempotency key u refundů.
  FAIL: odpověď říká NEVÍM, vymýšlí si jiný další krok, nebo mluví
        jen obecně o fakturaci bez konkrétního dalšího kroku.
focus: last_message
---

Tohle měří, jestli se do kontextu dostal celý ledger, ne jen jeho titulek.
Regex na „Stripe" by prošel i při náhodné trefě z názvu repozitáře; konkrétní
NEXT krok si model bez injekce vymyslet nemůže.
