# ADR-007: Adopt transactional, versioned content publication with published-only retrieval

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 2 (AI & RAG) with Member 3 (Backend & Data)
- **Related requirements:** REQ-LANG-FR-010, REQ-LANG-GOV-001, REQ-LANG-ARCH-003, REQ-LANG-SEC-004, REQ-LANG-NFR-001, REQ-LANG-FR-003, REQ-LANG-FR-004
- **Related artifacts:** `docs/architecture/invariants.md` INV-008/009, `runtime-policy-catalog.md` RP-005/RP-015, `memory-design.md`, `configuration-governance.md`, `options-ledger` (C2/C3)
- **Review triggers:** `unpublished_chunk_served > 0`; a publish rolled back more than once in a sprint; hosted PostgreSQL lacks pgvector at the selected plan; corpus `> 100,000` chunks; retrieval p95 `> 800 ms` for 2 weeks; `recall@5 < 0.85` after two tuning rounds; a licence review rejects a published source.

## Context

The product's trust claim depends on two properties that are easy to state and hard to keep: every citation resolves to a real, reviewed, published lesson section; and a retired or half-ingested lesson never appears in an answer.

The corpus is small but edited by humans. A lesson may be corrected, re-levelled or retired. Embeddings are expensive to regenerate and must stay consistent with the text they represent. The team has one PostgreSQL instance and no separate search cluster.

## Decision

Treat a content version as an immutable artifact and make publication a transactional state transition:

`draft -> validated -> active -> retired`.

Only one version of a source may be `active`; retrieval filters on `status = 'active'` **before** ranking; ingestion writes chunks and embeddings into a staging version; activation switches the pointer in one transaction; retirement removes the version from serving but keeps it for audit.

The vector index is `pgvector` inside the same PostgreSQL instance, behind `RetrievalPort`, so a future split (C2) is a seam change rather than a rewrite.

## Rationale

- A version pointer makes publication atomic without copying chunks at query time. A failed ingest leaves the previous active version untouched.
- Pre-filtering by status is the only way to prove that unpublished text cannot be ranked; post-filtering after top-k can leak an unpublished chunk into the candidate set even if it is later removed.
- Keeping retired versions supports citation provenance and "what did the learner see on that date" audits.
- pgvector keeps one backup and one transaction boundary for R1. The cost is scale, not correctness; the reconsideration trigger is explicit.
- Embedding model ID and dimension are stored with the index version, so a model change cannot silently mix vector spaces.

## Publication model

| Object | Fields | Invariant |
|---|---|---|
| `content_sources` | `source_id`, title, language, level, topic, author, licence, licence_url, checksum, reviewer, review_status, created_at | A source cannot be published without licence and reviewer |
| `content_versions` | `version_id`, `source_id`, status, manifest_hash, embedding_model_id, dimension, chunk_count, activated_at, retired_at | Exactly one `active` version per source |
| `content_chunks` | `chunk_id`, `version_id`, section, ordinal, text, token_count, embedding, checksum | A chunk belongs to exactly one version; text and embedding cannot be edited after validation |
| `content_audit` | event, version_id, actor, at, reason | Append-only; every activation/retirement recorded |

## Ingestion and activation flow

1. **Dry run:** `scripts/ingest_content.py --manifest content/manifest.yaml --dry-run` validates fields, licence, duplicates, language and empty text; it writes a report and no rows.
2. **Stage:** extract, clean, split into 200-400 token sections with <= 10% overlap, embed with the pinned model, write a `draft` version and its chunks.
3. **Validate:** chunk count > 0, no empty/oversized chunks, unique `chunk_id`, embedding dimension matches the index, checksum matches the manifest. Failures keep the version `draft`.
4. **Activate (transaction):** lock the source, set the previous `active` to `retired`, set the new version to `active`, write `content_audit`, commit. A failure rolls back both changes.
5. **Serve:** `RetrievalService` selects from `content_chunks` joined to `content_versions` where `status='active'` and the source language/level/topic match, then ranks.
6. **Retire:** set `retired` in a transaction; the next query excludes it. In-flight turns revalidate chunk IDs against the active set before display.
7. **Rollback:** activate the prior `validated` or `retired` version; the retired version remains retrievable only through the admin audit view, never through learner retrieval.

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| `ContentPublisher` | Manifest validation, staging, transactional activate/retire, audit | `src/content_publisher.py` |
| `RetrievalService` | Published-only, language/level/topic pre-filter; ranking and dedupe | `src/retrieval_service.py` |
| `ResponseValidator` | Reject citations not in the retrieved active set | `src/response_validator.py` |
| `ObservabilityStore` | Record version ids, chunk ids and publication events | `src/observability_store.py` |
| `AppConfig` | Pin embedding model, dimension and retrieval thresholds | `src/config.py` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Grounding | Immutable versions + published-only pre-filter | No stale or half-published citation | Extra version row and pointer switch | `citation_validity < 100%` |
| Availability | Activation transaction + rollback to prior version | A bad publish is reversible in one action | Requires a validated prior version to exist | rollback takes > 5 minutes |
| Privacy | Corpus stores licensed content only; learner text never enters versions | A licensable, auditable corpus | No personalisation by mining learner text | `learner_text_in_shared_stores > 0` |
| Retrieval quality | Chunk 200-400 tokens, overlap <= 10%, top-5 | Coherent sections with context | Chunking choices need tuning | `recall@5 < 0.85` |
| Performance | pgvector HNSW index; pre-filter before ranking | Sub-second retrieval at 1k chunks | Index build time and memory | `retrieval_p95_ms > 800` |
| Modifiability | Version + embedding model recorded | Reindex is attributable and reversible | Duplicate storage during overlap | mixed dimensions or missing model id |
| Cost | Local pgvector; no separate service | One database and one backup | Scale ceiling | corpus > 100k chunks |

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Edit chunks in place and serve immediately | Invariant protection / grounding: a half-updated lesson can serve mixed sections and cannot be rolled back | `GOV-001`, `INV-008` |
| Post-filter after top-k ranking | Published-only proof: an unpublished chunk can influence ranking or be returned if the filter is misplaced | `ARCH-003`, RP-015 |
| Separate vector service (C2) | Testability and operational fit for R1: a second service and network contract for a 1k-chunk corpus | `evaluation-table.md` C2, `option-ledger.md` C2 |
| Managed RAG platform (C3) | Privacy/licence control and testability: content leaves the team's database and retrieval is not reproducible offline | `evaluation-table.md` C3, `option-ledger.md` C3 |
| Store source text in learner rows for convenience | Privacy boundary: violates the separation between curriculum and learner writing | `SEC-004`, `INV-009` |

## Consequences

**Benefits**

- A publish is atomic and reversible; a failed ingest cannot affect learners.
- Citation provenance is reproducible from `version_id` + `chunk_id` + checksum.
- The vector index lives in the same backup and transaction boundary as content metadata.
- The `RetrievalPort` seam keeps the C2 split available if the corpus outgrows pgvector.

**Costs**

- Duplicate chunk storage while two versions overlap; bounded by retiring within one sprint.
- Reindexing is a full rebuild per embedding-model change; the evaluation replay must rerun.
- pgvector performance and index tuning become the team's responsibility.
- A licence review is a human bottleneck; a missing reviewer blocks publication.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Host lacks pgvector | at plan confirmation | Reopen this ADR; C2/C3 become live options |
| Corpus size | > 100,000 chunks | Benchmark; open ADR-002 for a split review |
| Retrieval p95 | > 800 ms for 2 weeks | Tune index/filters; benchmark C2 |
| Recall@5 | < 0.85 after two tuning rounds | Re-chunk or change embedding model; new ADR |
| Publish rollback | more than once in a sprint | Root-cause review; add a dry-run test |
| Licence/reviewer gap | any source missing | Block activation; log an evaluation finding |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial publication model accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27; `option-ledger.md` C2/C3 conditions |
