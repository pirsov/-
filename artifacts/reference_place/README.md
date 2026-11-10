# Reference place (user drop)

`working_game.rbxl` — рабочая (более-менее) Roblox-игра от пользователя.  
Бинарный place: Studio открывает напрямую. Для Forge — ориентир по архитектуре (есть DataStore, Remotes, LocalScript/ModuleScript).

## Как использовать

1. Открой в **Roblox Studio** → File → Open → `working_game.rbxl`
2. Смотри `ServerScriptService` / `ReplicatedStorage` / `StarterPlayer` — как устроены save/net/UI
3. В Quality Forge UI формулируй задачи в том же стиле (DataStore + Remotes + client HUD)
4. Для 3D: экспортируй/положи `.glb` в `assets/models/` → `python -u run.py --scan-assets`

Forge **не** читает `.rbxl` как исходники — код генерируется в `src/**/*.luau` (Rojo). Place = референс поведения.
