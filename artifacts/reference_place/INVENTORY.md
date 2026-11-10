# Inventory — `working_game.rbxl`

Binary place (614,668 bytes). Instance **Name** props are inside ZSTD-compressed chunks — a raw string scan misses them.

## Folder `Fruits_Inventory`

All fruit Models used by the game live here (mechanics under `FruitMechanics`).

| Name | Class | Geometry | Parts |
|------|--------|----------|------:|
| **Strawberry** | Model | parts | 346 |
| **Lemon** | Model | parts | 226 |
| **Watermelon** | Model | parts | 476 |
| **Grapes** | Model | parts | 175 |
| **Pineapple** | Model | parts | 310 |
| **Peach** | Model | parts | 119 |
| **Orange** | Model | parts | 148 |
| **Raspberry** | Model | parts | 123 |
| **Pear** | Model | parts | 478 |
| **DragonFruit** | Model | parts | 355 |
| **Pomegranate** | Model | parts | 261 |
| **Cherry** | Model | parts | 229 |
| **Coconut** | Model | parts | 257 |
| **Mango** | Model | parts | 184 |
| **Kiwi** | Model | parts | 191 |
| **Blackberry** | Model | parts | 123 |
| **Blueberry** | Model | parts | 37 |
| **Model *(unnamed)*** | Model | parts | 189 |
| **VoxelApple** | Model | parts | 212 |

## Sibling fruit assets (same parent Folder)

| Name | Class | Notes |
|------|--------|--------|
| **Trash_Orange** | Model | Part-voxel (148 parts), outside inventory |
| **Trash_Mango** | Model | Part-voxel (184 parts), outside inventory |
| **Banana** | Accessory | MeshId `rbxassetid://178186804`, texture `152661377` |

Registered for Forge Gate in `assets/catalog/place_meshes.json` (ids usable as `proposed_assets`; `Apple` aliases `VoxelApple`).

## Related fruit scripts / remotes

`FruitCarryClient`, `FruitCarryHandler`, `FruitMutationHandler`, `FruitRespawnManager`, `FruitAction*`, `FruitWorldUI`, `FruitSetup`, `FruitActionEvent`, `ThrowFruitEvent`, `FruitActionMenu`.

## What this means for Forge

- Gate accepts these fruit **ids** from `place_meshes.json` without needing `.glb` on disk.
- Geometry stays inside the `.rbxl` (Studio Part voxels / Banana mesh).
- Re-scan: `python -u run.py --scan-place-fruits`
