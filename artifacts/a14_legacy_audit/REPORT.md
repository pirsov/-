# A14.0 Legacy Audit & Bootstrapping

**Target:** `legacy_project/` (Claude Code–style sample with intentional holes)  
**Command:** `python3 run.py --audit-legacy legacy_project/`

## Findings: 8 pitfalls → 7 draft rules

| Sev | Pitfall | File | Draft rule |
|-----|---------|------|------------|
| CRIT | DataStoreService on client | `ShopUI.client.luau:6` | **R001** |
| CRIT | DataStore GetAsync without pcall | `PlayerData.server.luau:9` | **R004** (deduped w/ SetAsync) |
| CRIT | DataStore SetAsync without pcall | `PlayerData.server.luau:17` | → R004 |
| HIGH | while true without wait | `PlayerData.server.luau:27` | **R005** |
| HIGH | OnServerEvent without typeof | `Shop.server.luau:21` | **R006** |
| MED | FireServer needs server validation | `ShopUI.client.luau:14` | **R002** |
| MED | GetPlayerFromCharacter no nil check | `Checkpoints.server.luau:17` | **R003** |
| MED | Deprecated wait() | `Shop.server.luau:30` | **R007** |

## Activate (after your review)

```bash
python3 run.py --rules-list
python3 run.py --rules-activate R001   # no DataStore on client
python3 run.py --rules-activate R004   # DataStore files must use pcall
python3 run.py --rules-activate R006   # RemoteEvent args validated
# optional: R005 (while true), R007 (task.wait)
```

Rules match by **archetype** (not legacy filenames), so they protect new 14B generations.

## Outputs

- `docs/LEGACY_PITFALLS.md`
- `docs/LEGACY_ARCHITECTURE.md`
- `.forge/legacy_audit/draft_rules.json`
- `knowledge_base.json` (status=`draft`)
