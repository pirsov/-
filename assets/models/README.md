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

`working_game.rbxl` → Folder **`Fruits_Inventory`** holds Part-voxel fruit Models
(Orange, Mango, DragonFruit, VoxelApple, …). Sibling **Banana** Accessory has a MeshId.
`Apple` is registered as an alias of `VoxelApple`.

```bash
python -m pip install zstandard        # once (also: pip install -r requirements.txt)
python -u run.py --scan-place-fruits   # refresh place_meshes.json + INVENTORY.md + catalog
python -u run.py --scan-assets         # models dir + place_meshes → assets.json
```

No `.glb` required for Gate ids from the place. Drop artist `.glb` here only for file-based meshes.
If `place_meshes.json` is already committed, `--scan-assets` works without reinstalling `zstandard`; re-scan of the `.rbxl` still needs it.
