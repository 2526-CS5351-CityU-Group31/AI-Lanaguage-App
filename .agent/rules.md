# Project Covenant (`.agent/rules.md`)

## 1. Abstraction Limits
- Maximum directory nesting depth under `src/` is 3 levels.
- Each architectural element maps to exactly one module; avoid unnecessary wrapper classes or deep inheritance hierarchies (maximum inheritance depth: 1).

## 2. Dependency Constraints
- No unapproved third-party packages may be added without explicit human approval and verification against hallucinated dependencies.
- Deterministic safety boundary modules (`src/backend/safety/`) must only depend on standard library modules or vetted deterministic validation libraries—never on live LLM calls.

## 3. Test Independence
- Every requirement fit criterion must have at least one automated test.
- Every feature must include **at least one negative test** verifying graceful failure or rejection of invalid/unsafe inputs.
- Offline deterministic tests (`test/offline/`) must never make live network or external LLM API calls.

## 4. Safety-Critical Code Change Rule
- Modifying any safety-critical boundary code or governance configuration requires an approved Architecture Decision Record (`docs/architecture/adr/`) and explicit human sign-off prior to implementation.

## 5. Context Freshness Policy
- All governance rules, trace matrices (`docs/architecture/trace-matrix.md`), and requirement registries (`docs/req/requirements.yaml`) must be updated within **one sprint** of any requirements change.
