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

`working_game.rbxl` contains Folder **`Fruits_Inventory`** with all fruit Models (Orange, Mango, DragonFruit, …) plus Accessory **Banana**.

They are registered in `assets/catalog/place_meshes.json` and merged on `--scan-assets` (no `.glb` required for Gate).

Optional: export a Model from Studio as `.glb` into this folder if you want a file-based mesh for non-Roblox tooling.
