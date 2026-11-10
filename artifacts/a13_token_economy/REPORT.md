# A13.0 Token Economy — bundle savings

## Results

| Sample | Before | After | Saved |
|--------|--------|-------|-------|
| Fixture (RU card + rules + skeleton) | 841 B | 572 B | **32.0%** |
| Live repo (3 EN cards + client_ui@v1) | 1113 B | 884 B | **20.6%** |
| CLI `--bundle-savings` (compact list) | 1058 B | 837 B | **20.9%** |

RU-heavy context saves more (≈32%); already-English cards still shrink ≈21% via short keys + minify + compact headers.

## What changed

1. **EN for 14B** — `token_economy.englishize_*` on cards/rules/summaries before local LLM injection. UI/HITL stay Russian.
2. **Minify** — `dumps_disk` / `dumps_llm`; `state.json`, contracts, CARD.json, KB (set `FORGE_JSON_PRETTY=1` to indent).
3. **Short keys** — LLM-only: `exports→exp`, `forbid→f`, `purpose→p`, …
4. **CODE_ECONOMY** — strict prompt: no excess comments, concise locals, necessary code only.
5. **Compact cycle** — every 5 pulses, summaries englishized.

Toggle: `FORGE_TOKEN_ECONOMY=0` disables prompt compaction. Measure: `python3 run.py --bundle-savings`.
