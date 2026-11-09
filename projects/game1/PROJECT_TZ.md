# game1 — BestTime fix after smoke (HUD Best: --)

## DONE
- [x] horror week T* + repair R* | @gameplay_programmer

## AGENT B — BestTime
- [ ] B1 | REWRITE PlayerData: init BestTime=0 if nil (not math.huge); on PlayerRemoving compute elapsed from RunStartedAt; if BestTime==0 or elapsed<BestTime SetAttribute BestTime; Studio only | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] B2 | REWRITE Checkpoints: set RunStartedAt if nil; on last CP update BestTime if better; attrs on Player only | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] B3 | REWRITE HUD: Best from player:GetAttribute BestTime; -- only if nil/0 else %.1f | @client_programmer | -> src/client/HUD.client.luau

## HUMAN
- [ ] H9 | Studio: Best number not -- | @human
