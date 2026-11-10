# Legacy pitfalls

Ещё не сгенерировано. Запусти:

```bash
python -u run.py --audit-legacy path/to/your/legacy_project
```

Аудитор ищет, **где код может сломаться** (DataStore без pcall, OnServerEvent без typeof, `while true` без wait, DataStore на клиенте, …) и пишет draft-правила в `knowledge_base.json`.
