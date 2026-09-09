# Schéma `plugin eval` se dá vytáhnout z binárky, i když je brána zavřená

**Datum:** 2026-09-09 · **Task:** #1460 · **CLI:** 2.1.266

## Nález

`claude plugin eval` je early access **per organizace**. Náš účet ho nemá:
každý podpříkaz (včetně `init`) vypíše `plugin eval is currently in early
access` a skončí. `--help` přitom funguje, protože nápověda se registruje
před bránou. Brána je funkce nad server-side flagem, ne env proměnná —
v bundlu u ní stojí komentář „committed value normally leaves the command
gated off".

**Ale schéma tím nezmizelo.** Binárka (`~/.local/bin/claude`, single-file
Bun build) nese zod definice v plaintextu. `grep -a -o -E "vzor.{0,900}"`
nad ní vytáhne parser doslova. Tím jde suite opravit a ověřit **bez toho,
aby eval kdy běžel**.

## Co se tím zjistilo o `case.yaml`

1. `schema_version: "1.1"` je **povinný**, když `case.yaml` existuje. Default
   se dosazuje jen v prose režimu (`prompt.md` bez `case.yaml`).
2. Runtime klíče (`prompt`, `model`, `max_turns`, `timeout_seconds`,
   `allowed_tools`, `append_system_prompt`, `env`) patří pod **`execution:`**.
   Nahoře patří jen `schema_version, name, description, tags, plugins, runs,
   expected_outcome` + bloky `context`, `execution`, `graders`.
3. Vnější objekt **není** `.strict()` → klíč napsaný nahoru se **tiše zahodí**.
   Náš `prompt:` na top-levelu by tedy nebyl chyba, ale prázdný prompt.
   To je horší než error a `--help` to nijak nenaznačí.
4. Case složka jde napsat třemi způsoby a všechny se slučují do stejného
   objektu: `case.yaml`, `prompt.md` + `graders/*.md`, nebo **obojí naráz**
   (režim `mixed`). Náš hybrid je legální.
5. `context.scaffold_script` / `history_file` / `add_dirs` **nejdou** vyjádřit
   ve frontmatteru `prompt.md` — jsou jediný důvod, proč `case.yaml` mít.

## Co se tím zjistilo o graderech

6. Jméno graderu se bere z **názvu souboru**; `name:` do frontmatteru nepsat.
7. Frontmatter graderu **je** `.strict()` → `tool_used` s `target:` case shodí.
   (Náš `read-was-targeted.md` tuhle vadu měl.)
8. Grader **bez frontmatteru se tiše přeskočí** — mlčky, bez varování.
9. `arm: with-only` = vyřadit ze skóre; v baseline armu se takový grader
   ani nespustí. Automaticky se tak chová jen `tool_used` + `tool: Skill`
   (a `mock_calls` gradery).

## Provozní nález mimo schéma

10. **`--scaffold` je defaultně VYPNUTÝ.** Bez něj by dva ze tří našich casů
    běžely bez fixture a spadly na něčem jiném, než co testují. README i CI
    to měly špatně.
11. `--threshold` (default 1.0) se poměřuje se skóre **`with` armu**; baseline
    jde vedle jako delta. Guard-fired grader tedy nemůže shodit exit kód tím,
    že v baseline armu padá — což je přesně to, co od něj chceme.

## Poučení

Když je feature za bránou, „nedá se nic dělat" bývá lež. Klient, který ta data
validuje, je na disku. Nešlo ověřit *chování*, ale šlo ověřit *kontrakt* —
a všech 13 nalezených odchylek bylo v kontraktu.
