# A18.1 — Hotfix: CSS cache, live logs, current task

## Что сделано
- Cache-bust: `ui/index.html` → `/styles.css?v=a18.1` и `/app.js?v=a18.1`; `Cache-Control: no-cache` на html/css/js.
- Тёмная тема подтверждена в `styles.css` (`--bg: #0f172a`, `--panel: #1e293b`); коричневых переменных нет.
- `GET /api/logs?lines=N` — хвост лога агента (`run_hub` / `.forge/ui_run`); UI поллит каждые **2 с** в панель «Лог» с автоскроллом.
- `current_task` в `/api/status` и `/api/status_snapshot` (напр. `T2: DataStore`) — строка **над** прогресс-баром.
- HITL: при `waiting_human` прогресс-бар жёлтый; вопрос дублируется в чат.

## Ветка
`cursor/a18-1-live-logs-task-9409` поверх `cursor/a18-ui-overhaul-9409` (PR #20).

## Windows
```powershell
git fetch origin
git checkout cursor/a18-1-live-logs-task-9409
git pull origin cursor/a18-1-live-logs-task-9409
python -u run.py --ui
```
Hard refresh: **Ctrl+F5**. UI: `http://127.0.0.1:8787`.
