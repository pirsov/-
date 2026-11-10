## BUGS
- [LOW] UpdateLeaderboard remote unused (Leaderboard UI is backlog W9.2).
- [LOW] HUD timer is local-only; BestTime uses server RunStartedAt (acceptable).
- [LOW] Pressure plate standing counter can desync if character is destroyed mid-touch (rare).

## RESOLVED
- Checkpoint death teleport via LoadCharacter
- CoinCollected remote + HUD coins
- Generator LevelConfig gaps
- Void soft fail
- Remotes getOrCreate table (not Folder)

## FALSE POSITIVES
- PlayerRespawn — not in project; never invent.

## SUGGESTIONS
- Studio smoke all @human gates before calling week done.
- Moving platforms / leaderboard UI only after Day 7 freeze.

## TEST CASES
- Touch CP3 then CP1 — attribute stays 3; HUD CP: 3
- Pick coin — Coins attribute and HUD increment; sound plays
- Fall below Y=-20 — respawn at last CP
- Stand on blue plate — red gate opens; step off — closes

## SCORE
- overall: 86
- note: No open HIGH/CRIT after seed week pass. Human Studio gates still required.
