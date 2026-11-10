# 3D models for Quality Forge (A11.0)

Drop external artist outputs here before `Старт 24h`:

- `Apple.glb`, `Banana.ldr`, `Coin.glb`, …

Supported: `.glb` `.gltf` `.ldr` `.fbx` `.obj`

Then rescan:

```bash
python -u run.py --scan-assets
```

Catalog → `assets/catalog/assets.json`. Planner sees: `Available 3D assets: Apple, Banana, …`
