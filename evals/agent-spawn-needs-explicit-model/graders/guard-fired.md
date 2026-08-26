---
type: regex
pattern: "(tichy inherit|tichý inherit|BEZ .model.|permissionDecision)"
flags: "i"
match: contains
target: trace
---

Guard musí zachytit spawn bez explicitního `model` a vrátit deny s nápovědou
routingu. V baseline armu (bez pluginu) se subagent spustí tiše na modelu
hlavní smyčky a v trace po tomhle nezůstane ani stopa.
