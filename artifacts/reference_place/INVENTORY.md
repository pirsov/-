# Inventory — `working_game.rbxl`

Binary place (614 668 bytes). Instance **Name** props are inside ZSTD-compressed chunks — a raw string scan misses them.

## Folder `Fruits_Inventory`

All fruit Models used by the game live here (plus related mechanics under `FruitMechanics`).

| Name | Class | Notes |
|------|--------|--------|
| **Banana** | Accessory | MeshId `rbxassetid://178186804`, texture `152661377` (SpecialMesh) |
| **Blackberry** | Model | CSG / Union (no MeshId) |
| **Blueberry** | Model | CSG / Union |
| **Cherry** | Model | CSG / Union |
| **Coconut** | Model | CSG / Union |
| **DragonFruit** | Model | CSG / Union |
| **Grapes** | Model | CSG / Union |
| **Kiwi** | Model | CSG / Union |
| **Lemon** | Model | CSG / Union |
| **Mango** | Model | CSG / Union |
| **Orange** | Model | CSG / Union |
| **Peach** | Model | CSG / Union |
| **Pear** | Model | CSG / Union |
| **Pineapple** | Model | CSG / Union |
| **Pomegranate** | Model | CSG / Union |
| **Raspberry** | Model | CSG / Union |
| **Strawberry** | Model | CSG / Union |
| **Trash_Mango** | Model | variant |
| **Trash_Orange** | Model | variant |
| **VoxelApple** | Model | Part-based voxel apple |
| **Watermelon** | Model | CSG / Union |

Registered for Forge Gate in `assets/catalog/place_meshes.json` (ids usable as `proposed_assets`).

## Related fruit scripts / remotes

`FruitCarryClient`, `FruitCarryHandler`, `FruitMutationHandler`, `FruitRespawnManager`, `FruitAction*`, `FruitWorldUI`, `FruitSetup`, `FruitActionEvent`, `ThrowFruitEvent`, `FruitActionMenu`.

## Other notable instances

- `CombatSword` (Tool)
- Biomes folder, GardenPlots, MonsterTemplates, vines / foliage MeshParts
- Services: DataStoreService, RemoteEvent, ServerScriptService, ReplicatedStorage, StarterGui

## What this means for Forge

- Gate accepts these fruit **ids** from `place_meshes.json` without needing `.glb` on disk.
- Geometry stays inside the `.rbxl` (Studio). Export to `assets/models/*.glb` only if you want file-based meshes for non-Roblox tooling.
