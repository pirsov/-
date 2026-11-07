# Quality Forge

Механика длинной качественной сборки Roblox-игры (часы → дни → до недели).

## Зачем

Старый `run.ps1` «сжигал» файлы: задачи APPEND перезаписывали модули целиком,
`DONE` без `<FILE>` считался успехом, промпт раздувался до ~39KB, `num_predict=600`
обрезал код. В итоге игра ломалась быстрее, чем росла.

## Как работает

1. Берёт первый `- [ ]` из `PROJECT_TZ.md`
2. Собирает узкий промпт (только релевантные файлы)
3. Пишет через CREATE / APPEND / REWRITE (режим из текста задачи)
4. Снапшот → валидатор → rollback при ошибке → feedback в retry
5. Эскалация модели; при полном провале — auto-decompose на микро-APPEND
6. Heartbeat в `.forge/state/heartbeat.json` — можно остановить и продолжить через неделю

## Прогоны

| Pass | Что даёт |
|------|----------|
| BLUEPRINT | GDD, архитектура, контракты |
| SYSTEMS | один рабочий модуль за задачу |
| CRITIQUE×N | QA → fix пока SCORE ≥ 80 |
| POLISH | juice, void, UX |
| HARDEN | integrator + Studio |
| DEEPEN | backlog Deluxe-фич |

## Команды

```bash
python3 run.py --loop --max 500          # оставить надолго
python3 run.py --loop --max 500 --sleep 5
python3 run.py --validate
python3 run.py --score
python3 -m unittest tests.test_orchestrator -v
```
