# Inventory — `working_game.rbxl`

Scanned binary place (614 668 bytes).

## Fruit / collectible models found by **Name**

| Name | Notes |
|------|--------|
| **Banana** | Only fruit-named instance. MeshId `rbxassetid://178186804`, texture `…/asset/?id=152661377` |

**Not found by name:** Apple, Orange, Grape, Lemon, Cherry, Pear, Peach, Mango, Melon, Kiwi, Strawberry, Watermelon, Pineapple, Fruit, Coin, LEGO.

## Other notable instances

- `CombatSword` (Tool-like)
- `VineBranch7`, `LeafParticles`
- Materials/terrain-ish: Brick, Grass, Ice, Rock, Sand, Snow, Wood, Mud, Salt, Slate, Foil, Metal
- Services present: DataStoreService, RemoteEvent, RemoteFunction, ServerScriptService, ReplicatedStorage, StarterGui

## What this means for Forge

Quality Forge asset Gate reads **`assets/models/*.{glb,gltf,ldr,fbx,obj}`**, not `.rbxl` geometry.

- Banana is registered in catalog as a **Roblox mesh ref** (see `assets/catalog/place_meshes.json`).
- To use Apple / other fruits in 24h: in Studio select each fruit Model → export / save as `.glb` (or drop artist `.glb`) into `assets/models/` → `python -u run.py --scan-assets`.

If you expected more fruits inside this `.rbxl`, re-save the place from Studio with each fruit Model named `Apple`, `Orange`, … and upload again — or export them as files.
