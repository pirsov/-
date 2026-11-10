# A15.0 Advanced Context Optimization

## Levers

| # | Lever | Implementation |
|---|-------|----------------|
| 1 | Ollama `num_predict` | `forge/llm_backends.py` + `models.json`: **1024** code / **512** diff-repair |
| 2 | Diff generation | Prompt PATCH mode + `patch_apply.py` SEARCH/REPLACE → apply on existing files |
| 3 | Semantic prune | `token_economy.prune_card` + `bundle_for_14b(focus_terms=…)` |
| 4 | 7B compaction | `llm_backends.summarize_local` in `state_hub` (no DeepSeek) |

## Measured (`python3 run.py --bundle-savings`)

- **Bundle fat→lean:** ~**24%** smaller (A13 economy + A15 prune)
- **Prune-only vs economy:** ~**4%** extra on live EN cards (more on fat RU/multi-export cards)
- **Cycle estimate (approx tokens):**
  - Full-file path: **~1224** (bundle≈200 + predict 1024)
  - Diff path: **~712** (bundle≈200 + predict 512)
- Output wall: previously up to **4096** predict → now **1024/512** (~**50–87%** less output budget)

## Toggle

- `FORGE_NUM_PREDICT` / `FORGE_NUM_PREDICT_DIFF`
- `FORGE_COMPACT_7B=0` → deterministic englishize only
- `FORGE_TOKEN_ECONOMY=0` → disable EN/short-key path
