---
type: tool_used
tool: Read
input_match: '"offset"'
min: 1
target: trace
---

Jádro věci: model má dojít k cílenému čtení s `offset`, ne k nasátí celého
souboru do kontextu. Bez pluginu je běžné chování jeden `Read` bez parametrů,
který sežere ~26 000 tokenů a pak se s každým dalším callem platí znovu.
