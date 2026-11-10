# Legacy project drop-zone (A12.0)

Положи сюда (или укажи любой путь) старый Luau-проект для аудита «подводных камней».

```bash
# из корня Quality Forge:
python -u run.py --audit-legacy legacy_project/
# или:
python -u run.py --audit-legacy /path/to/your/old/game

# только отчёт, без merge в knowledge_base.json:
python -u run.py --audit-legacy legacy_project/ --audit-no-kb-merge
```

Выход:

- `docs/LEGACY_ARCHITECTURE.md` — модули и функции
- `docs/LEGACY_PITFALLS.md` — где может сломаться / дыры
- `.forge/legacy_audit/draft_rules.json` — draft-правила для валидатора
- (по умолчанию) draft-правила дописываются в `knowledge_base.json` со статусом `draft`

Активируй правило вручную после ревью:

```bash
python -u run.py --rules-list
python -u run.py --rules-activate R0xx
```
