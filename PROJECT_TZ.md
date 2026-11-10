# LAST_UPDATE: A6.1+A6.2+A6.3 CLOSED (agent core). game1 frozen. Tests 36 OK.
# HITL: python run.py --feedback y|n --plugin game1.hud --note "..."
# Rules: python run.py --rules-list | --rules-activate R001

## AGENT CORE DONE
- [x] A6.1 | Graceful LLM degrade + stub never closed | @integrator
- [x] A6.2 | compact_state every 5 cycles | @integrator
- [x] A6.3 | HITL feedback → JSON rules + golden | @integrator | -> forge/feedback.py

## FROZEN
- game1 src/** gameplay polish deferred

## NEXT
- [ ] A7.1 | DeepSeek planner redesign | @integrator | -> forge/deepseek.py
- [ ] H13 | Desktop ollama --doctor + optional --feedback after Studio | @human
