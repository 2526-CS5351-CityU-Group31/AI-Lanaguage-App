# OpenCode Always-On Behavioral Rules (HUMAN-ONLY FILE)

1. **Read Order Enforcement:** Always read `AGENTS.md` first, followed by `Prompt.md` and the architecture artifacts listed in `AGENTS.md` before proposing any action.
2. **Mandatory Human Gates:** Never generate, modify, or delete source code (`src/`) or tests (`test/`) without first outputting a structured Execution Plan and receiving explicit human approval in the session.
3. **Immutable Governance Boundary:** You are strictly forbidden from modifying `.opencode/rules.md`, `.opencode/permissions.jsonc`, `.agent/rules.md`, `AGENTS.md`, or `Prompt.md`.
4. **Traceability Mandate:** Every generated module, class, and function must include a docstring or comment referencing the specific Requirement ID (`REQ-XXX`), Architecture Decision Record (`ADR-XXX`), and Invariant ID (`INV-XXX`) it implements.
5. **AI-Use Logging Reminder:** Whenever you modify files under `src/` or `prompts/`, remind the human supervisor to log the session intervention in `docs/code-governance/ai-use-log.yaml`.
