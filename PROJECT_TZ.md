# LAST_UPDATE: GAME FROZEN. Focus = Quality Forge agent core (not game1 polish).
# mode=agent_core. Awaiting plan approval for A6.1 graceful degradation + A6.2 state compaction.

## FROZEN (do not implement)
- game1 src/** gameplay / VFX / fog / HUD ideas deferred in ideas.json
- I009–I013 game polish held

## AGENT CORE (infra)
- [ ] A6.1 | Graceful degradation: ollama ping False → log + fallback backend/stub, do not abort week | @integrator | -> forge/llm.py forge/orchestrator.py
- [ ] A6.2 | compact_state(state.json) every 5 cycles; shrink contract snapshots | @integrator | -> forge/state_hub.py (new) forge/orchestrator.py
- [ ] A6.3 | tests for degrade + compact | @integrator | -> tests/test_orchestrator.py

## HUMAN
- [ ] H13 | Approve agent-core plan then implement | @human
