# 3D models for Quality Forge (A11.0)

Drop external artist outputs here before `Старт 24h`:

- `Apple.glb`, `Banana.ldr`, `Coin.glb`, …

Supported: `.glb` `.gltf` `.ldr` `.fbx` `.obj`

Then rescan:

```bash
python -u run.py --scan-assets
```

Catalog → `assets/catalog/assets.json`. Planner sees: `Available 3D assets: Apple, Banana, …`

## From Studio place (`.rbxl`)

`working_game.rbxl` was scanned: only a Model named **Banana** was found (mesh `rbxassetid://178186804`).  
It is registered via `assets/catalog/place_meshes.json` after `--scan-assets`.

To add Apple / other fruits:

1. In Studio open the place → rename each fruit Model (`Apple`, `Orange`, …)
2. Export / save as `.glb` into this folder **or** re-upload the place and tell the agent to re-scan
3. `python -u run.py --scan-assets`
