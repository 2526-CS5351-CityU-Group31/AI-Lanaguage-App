# AGENTS.md — Coding Agent Master Entry Point

## 1. Build Target
AI-Companion Language Learning Web Application featuring an LLM-powered conversational tutor and a deterministic safety-relevant output validation boundary.

## 2. Mandatory Reading Order for Architecture Artifacts
Before generating any plan or code, read the following artifacts in exact sequence:
1. `.opencode/rules.md` & `.agent/rules.md`
2. `docs/req/requirements.yaml`
3. `architecture-blueprint.md`
4. `docs/architecture/invariants.md`
5. `docs/architecture/permission-model.md`
6. `docs/code-governance/structural-constraints.md`
7. `docs/code-governance/verification-constraints.md`
8. `docs/architecture/role-ownership.md`
9. `Prompt.md` (Launch Instruction)

## 3. Code Baseline & Path Authority
- **Frozen (No Agent Write):** `.opencode/`, `.agent/`, `AGENTS.md`, `Prompt.md`, `.github/workflows/`
- **Read-Only Reference (Unless Operating as Plan Agent):** `docs/req/`, `docs/code-governance/`
- **Modifiable under Human Supervision:** `src/backend/`, `src/frontend/`, `test/offline/`, `test/live/`
- **Role lanes:** each teammate owns a specific path set; see `docs/architecture/role-ownership.md`

## 4. Module Organization & Integration Contracts
- `src/backend/ai_companion/`: Genuine AI component (LLM prompt assembly, layered context window, tutor dialogue). Advisory authority only.
- `src/backend/safety_boundary/`: Deterministic safety boundary enforcing hard lexical, schema, and educational constraints before any AI output reaches the user. Authoritative gate.
- `src/backend/api/` & `src/frontend/`: Application service layer and user interface communicating via strict JSON schema contracts.

## 5. Verification Requirements
- All generated code must pass three-tiered verification:
  1. **Structural:** Linting, static type checking, module boundary compliance.
  2. **Regression:** 100% pass rate on all existing suites in `test/offline/`.
  3. **Behavioral:** Zero safety escapes across invariant test cases.
