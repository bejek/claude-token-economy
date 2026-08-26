#!/bin/sh
# Položí do workspace rozdělaný session ledger. Hook `inject_session_ledger.py`
# ho na SessionStart načte z `<cwd>/docs/session-ledger.md`.
set -e
mkdir -p docs
cat > docs/session-ledger.md <<'LEDGER'
# TASK Migrace fakturace na Stripe — services/billing
STAV: běží — webhooky hotové, zbývá idempotence u refundů
NEXT: dopsat idempotency key do `refund_handler.py`, pak zapnout retry
HOTOVO: checkout session, webhook signature verification, 3DS flow
BLOKERY: —
ROZHODNUTÍ: platíme v EUR, konverzi řeší Stripe, ne my
NÁLEZY: sandbox Stripe posílá `charge.refunded` dvakrát — proto ta idempotence
ŽURNÁL: —
LEDGER
