# Rules activated + A15 status

## Active HITL rules (A14 → live filter)

| ID | Status | Guard |
|----|--------|-------|
| **R001** | **active** | No `GetService("DataStoreService")` on `client_ui` |
| **R004** | **active** | If Get/Set/UpdateAsync present → require `pcall` |
| **R006** | **active** | If `OnServerEvent` present → require `typeof`/`assert` |
| R002 R003 R005 R007 | draft | Optional later |

Activate used dry-run that skips `legacy_project/` + `*_BAD*` + `artifacts/`.  
`if_present` gates prevent false positives on unrelated server scripts.

## A15.0 metrics (`--bundle-savings`)

- Bundle fat→lean: **~22–24%**
- Cycle ≈ **1306 tok** (code, predict 1024) / **~794 tok** (diff, predict 512)
- Output ceiling: 4096 → **1024/512**

Ready for desktop `git pull` + 24h marathon after stack merge.
