# Hardware profile — GTX 1660 SUPER 6GB

## What you have
- VRAM 6GB; `qwen2.5-coder:14b-4k` ≈ 4GB loaded → **~2GB free**
- Monitor shows ctx **4096 / 33k** — raising num_ctx to 8k/16k on 14b will OOM or spill to RAM (slow)
- GPU 100% while generating is normal; VRAM ~90% means **do not load a second big model**

## Recommended (already in forge/models.json)
| Role | Model | ctx | predict |
|------|--------|-----|---------|
| Code CREATE/REWRITE | `qwen2.5-coder:14b-4k` | 4096 | 4096 |
| Repair attempt 2–3 | `qwen2.5-coder:7b-2k` | 2048 | 3072 |
| Docs/QA | `phi4-mini:4k` | 4096 | 1536–2048 |

## Do / Don't
- DO: `OLLAMA_NUM_PARALLEL=1`, one forge process, unload unused models (`ollama stop`)
- DO: keep Studio closed while `--week` runs if VRAM stuck >90%
- DON'T: set forge ctx to 8k/16k/32k for 14b on 6GB
- DON'T: run 14b + 7b both resident — forge switches on repair; let Ollama swap
- Better quality later: Space Bunny / OpenRouter when key works (1M ctx, no VRAM)

## Optional stronger local (if you free VRAM)
- Only `qwen2.5-coder:7b-2k` for all code (weaker but stable headroom)
- Or cloud for F* rewrite tasks, local for tiny NOTE tasks
