# Skills hub

## Sources
- `raw/ash` — https://github.com/AshExplained/roblox-skills (architecture/design)
- `raw/sypho` — https://github.com/SyphoDev-yt/roblox-ai-skills (code/ui/map; markdown only)
- `compact/` — short skills injected into Ollama prompts (budget ~1200 chars each, max 3)

## Flow
1. DeepSeek (or heuristic) compresses `raw` → `compact`
2. Ollama `--week` writes Luau with compact skills in the prompt
3. Human answers smoke in UI → working compact skills get `PROMOTED.json`

## Commands
```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python run.py --skills-list
python run.py --skills-compress ash__roblox-luau-architecture
python run.py --ui
```
