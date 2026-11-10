# A16.0 Launch Preparation

## Delivered

1. **`START_24H.md`** — A15 flags (`FORGE_NUM_PREDICT`, diffs, 7B compact) + **Troubleshooting** (Ollama down, waiting_human logs, resume after crash, validator rules, VRAM).
2. **Launch checklist** — printed on `python -u run.py --ui` and via `--checklist` / `GET /api/checklist`:
   - Ollama
   - Skeletons registry
   - Assets catalog
   - Active validator rules (R001/R004/R006)
   - Token economy caps

## Local marathon (after merge / pull)

```bash
git pull
ollama serve && ollama pull qwen2.5-coder:14b-4k && ollama pull qwen2.5-coder:7b-2k
# drop Apple.glb → assets/models/
python -u run.py --scan-assets
python -u run.py --checklist
python -u run.py --ui
# → http://127.0.0.1:8787 → chat → Старт 24h
```

Suite **105 OK**.
