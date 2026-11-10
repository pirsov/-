---
name: roblox-code
source: heuristic
max_chars: 1200
---
---
name: roblox-code
---
# Roblox code that can be proven without Studio
> **First time on this machine?** Read `LOCAL.md` in this folder. If it does not exist, run the
> `roblox-skills-setup` skill (or copy `LOCAL.template.md` to `LOCAL.md` and fill it in).
> `LOCAL.md` holds your paths and tool locations; it is yours and is never shared.
The hard constraint on this platform is not the language, it is **feedback**. A
running Roblox game is close to uninspectable from outside: `capture_screenshot`
is edit-mode only, `execute_luau` only ever reaches the edit DataModel, and
`VirtualInputManager` is unavailable from plugin context. During a playtest, the
only channel back is `LogService`.
Everything below follows from that one fact. If the game cannot be watched while
it runs, then **as much of it as possible must be decidable while it sits still.**
```
write code on disk
  -> rojo build      does it parse and assemble?         ~1s
  -> lune run test    does the pure logic still hold?     no engine, no Studio
  -> selene           lint
  -> stylua --check   format
  -> rojo serve       Studio sees it     <- the FIRST time St