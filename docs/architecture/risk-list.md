# Risk list - baseline R1

**Purpose:** hold the assumptions we believe but have not proven, the concrete failure if each is wrong, the design element that contains it, and the metric that reopens it.
**Owner:** Member 1 (Requirements & PM) maintains the list; each mitigation owner is named in the row.
**Rule:** this file holds **unproven assumptions only**. If an item is actually a requirement, move it to `requirements.yaml`; if it is an invariant, move it to `invariants.md`. A risk with a mitigation that does not exist in the design is a wish.

**Status at baseline:** every risk is `open`. None is `mitigated` or `closed`: no test or production evidence exists yet. A risk moves to `mitigated` only when its containment has executed at least once, and to `closed` with the evidence date.

## 1. Risk register

| ID | Assumption (proposition) | Impact if wrong | Mitigation (design element) | Review trigger (metric + threshold) | Owner | Status |
|---|---|---|---|---|---|---|
| R-001 | A 12-lesson corpus and a 24-question grounded set are representative enough that recall@5 generalises to the demo. | The right lesson is retrieved for the eval but not for unseen questions; answers abstain or cite a weaker section. | `RetrievalAdapter` top-5 + rerank; EVAL-1.0.0 replay; topic-level reporting | `recall@5 < 0.85` in two consecutive runs, or any topic with >= 3 cases below 0.60 | Member 2 | open |
| R-002 | The provider's p95 latency is low enough that a 12 s turn budget survives retrieval, validation and one repair. | Turns time out, the retry state dominates the demo, and learners abandon the conversation. | `Tutor` 25 s timeout, 2 retries; `PromptAssembler` 1,500-token budget; p95 alert | `tutor_response_p95_seconds > 12` for 3 consecutive days, or timeout rate > 2% | Member 3 | open |
| R-003 | Published lessons contain no adversarial instruction and the untrusted-evidence delimiter plus validator resist injection. | A retrieved passage changes policy or elicits a fabricated citation; a safety demo fails. | `PromptAssembler` untrusted block; `CitationValidator`; 24-case adversarial set; content review | `injection_escape_total > 0` or an injection signal in a published chunk | Member 2 | open |
| R-005 | A six-turn session at the 1,500-token prompt cap stays within the cost budget. | The demo hits the per-turn token cap or drift alert during the live walkthrough. | `Tutor` call cap and cost counter; `PromptAssembler` compaction at 6 messages | 7-day mean token drift > 25%, or repeated cap hits | Member 2 | open |
| R-006 | The selected hosted PostgreSQL plan supports pgvector at the required dimension and region. | ADR-007 must be reopened; retrieval moves to C2/C3 late, costing a sprint. | `RetrievalAdapter` seam; ADR-007 review trigger; compatibility spike in Sprint 2 | Compatibility spike fails, or the host plan changes | Member 3 | open |
| R-008 | The provider's terms state no training on submitted data and a data-processing addendum is available. | Learner turns are used for provider training; the isolation design is undermined. | ADR-009 isolation; provider agreement review; no email/name in prompts | A provider policy change, or no DPA before the live demo | Member 2 | open |
| R-009 | A 24-question human-scored set gives a usable signal at the 0.80 threshold. | The score is indistinguishable from noise and the release decision is not defensible. | Two-reviewer rubric; `SafetyEvaluator`; confidence interval reported with the score; logbook row per run | 95% CI width > 0.15, or the score within 0.05 of the threshold | Member 2 | open |
| R-011 | One member (Member 2) can own corpus, retrieval, prompt and evaluation through the demo without becoming a single point of failure. | A member is unavailable, RAG work stops, and the demo depends on one person's context. | Pair review of every RAG PR; runbook in the README; rotation in Sprint 4 | Member 2 unavailable > 3 working days, or no second reviewer for a RAG PR | Member 1 | open |
| R-012 | Stakeholders accept the R1 scope: one language, text only, no teacher portal, no speech. | Scope creep consumes the buffer and the core grounding/feedback flows slip. | Scope guard (`INV-LANG-001`, `INV-SEC-002`); ADR required for a new capability; sprint review | A new capability request without an ADR, or any out-of-scope route | Member 1 | open |
| R-013 | The pinned provider model remains available through the demo and does not change behaviour silently. | A forced migration late in the project invalidates the eval baseline and the report numbers. | `Tutor` pinned id; RP-014 freeze/replay; EVAL-1.0.0 gate | Deprecation notice < 30 days, or a silent alias/behaviour change | Member 2 | open |
| R-014 | Two reviewers are available for each release gate (plan, content, PR). | The gate becomes a rubber stamp or blocks the sprint; review quality drops. | G1-G5 gates; review memo; rotation plan | Fewer than 2 reviewers for a release, or review latency > 2 working days | Member 5 | open |
| R-015 | The approval-artifact timestamp is trustworthy enough to prove tests were approved before implementation. | An implementation commit precedes its approval, and the course's process claim is unverifiable. | `check_test_approval.py` (planned); PR timeline; reviewer verification; AI log entry | Any implementation commit without a prior approval, or an unverifiable timestamp | Member 5 | open |

## 2. Closed risks

None. A risk may not be moved here without a dated evidence link and the trigger that was satisfied. At baseline there is no runtime or test evidence to close any assumption.

## 3. Risk review cadence

| When | What | Owner |
|---|---|---|
| Sprint 1 sign-off | Review the register; assign owners; confirm no risk is actually a requirement | Member 1 |
| Each integration review | Update status only with evidence; add a new row for a new assumption | Member 1 |
| Before release | Check every `open` risk has a live mitigation and a numeric trigger; close with evidence or carry forward explicitly | Member 5 |
| After any incident | Add a risk if the incident revealed an unlisted assumption; link the bug diary entry | Member 5 |

## 4. What does not belong here

- A requirement with a threshold: it belongs in `requirements.yaml`.
- An invariant with an enforcer: it belongs in `invariants.md`.
- A known bug with a reproduction: it belongs in `bug-diary.md`.
- A deferred fix with an interest cost: it belongs in `debt-register.md`.

## 5. Done-when status

- [x] Every `R-*` has a mitigation that exists in the design (element or gate).
- [x] Every `R-*` has a review trigger with a number or a named event.
- [x] Assumptions that were later proven would be marked `closed` with an evidence date; none are proven at baseline.
- [x] No risk duplicates a requirement or an invariant.
