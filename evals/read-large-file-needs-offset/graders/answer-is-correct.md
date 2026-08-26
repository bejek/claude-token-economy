---
type: llm
criteria: |
  Odpověď musí správně popsat funkci `spocitej_dan`:
  vrací základ krát sazba v procentech děleno 100, zaokrouhleno na 2 desetinná
  místa, a pro záporný základ vyhazuje ValueError.

  PASS: obojí sedí (výpočet i chování pro záporný vstup).
  FAIL: cokoli z toho chybí nebo je popsáno špatně.
focus: last_message
---

Pojistka proti falešnému vítězství. Guard, který ušetří tokeny za cenu špatné
odpovědi, není úspora — je to vada. Tenhle grader musí projít v OBOU armech;
kdyby padal jen s pluginem, znamená to, že guard modelu bere informace,
které potřebuje.
