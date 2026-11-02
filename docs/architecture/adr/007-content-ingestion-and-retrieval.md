# ADR-007: Offline content ingestion with published-only retrieval and citation provenance

- **Status:** Accepted
- **Date:** 2026-10-27
- **Supersedes:** -
- **Decision owner:** Member 2 (AI & RAG) with Member 3 (Backend & Data)
- **Related requirements:** FR-CORP-001, INV-CITE-001, NFR-QUAL-003, INV-SCOPE-006, NFR-QUAL-001
- **Related artifacts:** `docs/architecture/invariants.md` INV-CITE-001, `runtime-policy-catalog.md`, `configuration-governance.md`, `option-ledger.md` (C2/C3)
- **Review triggers:** `citation_reject_total > 0`; a chunk served whose `review_status != 'published'`; corpus `> 100,000` chunks; retrieval p95 `> 800 ms` for 2 weeks; `recall@5 < 0.85` after two tuning rounds.

## Context

The product's trust claim depends on one property that is easy to state and hard to keep: every citation resolves to a real, reviewed, published lesson section, and the runtime never serves unreviewed material.

The corpus is small but edited by humans. The runtime service must not be able to mutate the corpus; ingestion is an offline, human-run administrative step. The team has one PostgreSQL instance (with pgvector) and no separate search cluster.

## Decision

Treat the approved corpus as a **read-only artifact at runtime**:

- Ingestion happens only through the offline admin command `scripts/ingest_content.py` (`FR-CORP-001`), which validates, chunks, embeds and indexes approved lesson documents and emits an audit report.
- The runtime application connects with a **read-only** vector credential; insert/update/delete raise permission-denied (`INV-SEC-001`).
- Retrieval serves **only chunks marked published/approved** (`review_status = 'published'`), filtered before ranking (`INV-SCOPE-006`).
- Every displayed citation must resolve to an id in the retrieved published set; otherwise the answer is discarded and the system abstains (`INV-CITE-001`, `NFR-QUAL-003`).

The vector index is `pgvector` inside the same PostgreSQL instance, behind `RetrievalAdapter`, so a future split (C2) is a seam change rather than a rewrite.

## Rationale

- A read-only runtime credential is the only way to prove the corpus cannot be mutated by a compromised or buggy request path.
- Filtering on `published` before ranking is the only way to prove that unreviewed text cannot be ranked or displayed.
- Keeping ingestion offline means a bad ingest is an operational event, not a learner-visible outage.
- Checking citation ids against the retrieved published set is the one-line predicate that makes grounding provable.
- pgvector keeps one backup and one transaction boundary for R1. The cost is scale, not correctness; the reconsideration trigger is explicit.

## Corpus model

| Object | Fields | Rule |
|---|---|---|
| `content_sources` | `source_id`, title, language, level, topic, review_status, created_at | A source is served only when `review_status = 'published'` |
| `content_chunks` | `chunk_id`, `source_id`, section, ordinal, text, token_count, embedding | A chunk belongs to one published source; written only by ingestion |
| `content_audit` | event, source_id, actor, at | Append-only; every ingest recorded |

## Ingestion flow

1. **Dry run:** `scripts/ingest_content.py --manifest content/manifest.yaml --dry-run` validates fields, duplicates, language and empty text; it writes a report and no rows.
2. **Ingest:** extract, clean, split into 200-400 token sections with <= 10% overlap, embed with the pinned model, write chunks for approved sources.
3. **Validate:** chunk count > 0, no empty/oversized chunks, unique `chunk_id`, embedding dimension matches the index. Failures abort the ingest with a report.
4. **Serve:** `RetrievalAdapter` selects from `content_chunks` joined to `content_sources` where `review_status='published'` and the language/level/topic match, then ranks.
5. **Cite:** `CitationValidator` rejects any `source_id` not in the retrieved set; the answer abstains.

## Responsibility map

| Element | Responsibility | Implemented in |
|---|---|---|
| `IngestPipeline` | Validate, chunk, embed and index approved sources offline; emit audit report | `scripts/ingest_content.py` |
| `VectorClient` | Read-only vector access at runtime; writes denied | `src/backend/database/vector_client.py` |
| `RetrievalAdapter` | Published-only, language/level/topic pre-filter; ranking and dedupe | `src/backend/ai_companion/retrieval_adapter.py` |
| `CitationValidator` | Reject citations not in the retrieved published set | `src/backend/safety_boundary/citation_validator.py` |

## Quality attribute tradeoffs

| Attribute | Tactic | Buys | Costs | Metric that would invalidate |
|---|---|---|---|---|
| Grounding | Published-only filter + citation validation | No unreviewed or fabricated citation | Answers without a retrieved source must abstain | `citation_validity < 100%` |
| Integrity | Read-only runtime credential | Corpus cannot be mutated by a request path | Reindexing needs a separate offline run | `runtime_vector_write_attempt_total > 0` |
| Retrieval quality | Chunk 200-400 tokens, overlap <= 10%, top-5 | Coherent sections with context | Chunking choices need tuning | `recall@5 < 0.85` |
| Performance | pgvector HNSW index; pre-filter before ranking | Sub-second retrieval at 1k chunks | Index build time and memory | `retrieval_p95_ms > 800` |
| Cost | Local pgvector; no separate service | One database and one backup | Scale ceiling | corpus > 100k chunks |

## Alternatives considered

| Option | Failed criterion | Evidence |
|---|---|---|
| Runtime-writable corpus | Integrity: a request path could mutate served content; no read-only proof | `INV-SEC-001` |
| Post-filter after top-k ranking | Published-only proof: an unpublished chunk can influence ranking or be returned if the filter is misplaced | `INV-SCOPE-006`, `INV-CITE-001` |
| Serve unreviewed drafts | Grounding: unreviewed text could be quoted as curriculum authority | `INV-CITE-001`, `NFR-QUAL-003` |
| Separate vector service (C2) | Testability and operational fit for R1: a second service and network contract for a 1k-chunk corpus | `evaluation-table.md` C2, `option-ledger.md` C2 |
| Managed RAG platform (C3) | Privacy/licence control and testability: content leaves the team's database and retrieval is not reproducible offline | `evaluation-table.md` C3, `option-ledger.md` C3 |

## Consequences

**Benefits**

- The corpus is provably read-only at runtime; a bad request cannot corrupt it.
- Citation provenance is checkable against the retrieved published set.
- The vector index lives in the same backup and transaction boundary as content metadata.
- The `RetrievalAdapter` seam keeps the C2 split available if the corpus outgrows pgvector.

**Costs**

- Reindexing requires a separate offline run by a maintainer.
- pgvector performance and index tuning become the team's responsibility.
- Filtering by `published` constrains the answerable question space.

## Review triggers

| Trigger | Threshold | Action |
|---|---|---|
| Host lacks pgvector | at plan confirmation | Reopen this ADR; C2/C3 become live options |
| Corpus size | > 100,000 chunks | Benchmark; open ADR-002 for a split review |
| Retrieval p95 | > 800 ms for 2 weeks | Tune index/filters; benchmark C2 |
| Recall@5 | < 0.85 after two tuning rounds | Re-chunk or change embedding model; new ADR |
| Runtime write attempt | any occurrence | Treat as INV-SEC-001 failure; block release |

## Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-10-27 | Initial decision accepted at baseline R1 | `evaluation-logbook.md` 2026-10-27 |
| 2026-11-02 | Rescoped to the SSOT subset (ingest CLI, read-only vector store, published-only retrieval, citation provenance); version-lifecycle content removed as not SSOT-backed | This consolidation; `trace-matrix.md` FR-CORP-001 / INV-CITE-001 rows |
