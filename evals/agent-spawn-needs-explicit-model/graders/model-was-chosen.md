---
type: llm
criteria: |
  Finální odpověď musí jmenovat KONKRÉTNÍ model zvolený pro subagenta
  (haiku, sonnet, opus nebo fable) a zdůvodnit volbu povahou úkolu.

  PASS: odpověď jmenuje konkrétní model. Pro mechanickou práci s logy je
        věcně správně haiku nebo sonnet, ale grader hodnotí hlavně to, že
        volba padla vědomě a je zdůvodněná.
  FAIL: odpověď žádný model nejmenuje, mluví jen obecně o „levnějším modelu",
        nebo volbu vůbec nezdůvodňuje.
focus: last_message
---

Pointa guardu není zakázat drahé modely, ale vynutit vědomou volbu. Tenhle
grader měří přesně ten výstup: padlo rozhodnutí, nebo se model jen svezl
s tím, co zdědil?
