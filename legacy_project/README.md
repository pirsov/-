# Legacy project — Claude Code drop (A14.0)

Небольшой «старый» Roblox-проект (стиль Claude Code) с намеренными дырами для аудита Quality Forge.

```bash
python -u run.py --audit-legacy legacy_project/
python -u run.py --rules-list
python -u run.py --rules-activate R0xx
```

Ожидаемые эвристики: DataStore без `pcall`, DataStore на клиенте, `OnServerEvent` без `typeof`, `while true` без wait, deprecated `wait()`, `GetPlayerFromCharacter` без nil-check, `FireServer` без серверной валидации.
