# AI-Lanaguage-App

## Content ingestion (FR-CORP-001)

The lesson corpus is an offline, human-reviewed artifact. New sources start as
`review_status: "draft"` in `content/manifest.yaml`; after review, change them
to `"published"` and run:

```powershell
python scripts/ingest_content.py --manifest content/manifest.yaml --dry-run --report reports/ingest-plan.json
python scripts/ingest_content.py --manifest content/manifest.yaml --report reports/ingest.json
```

A real ingest requires `ADMIN_DATABASE_URL` in the local environment. Never
commit it and never set it on the Render web service. Without an embedding
file, chunks are stored with `embedding = NULL` and retrieval uses the
deterministic lexical ranking in `RetrievalAdapter`.

See `content/manifest.example.yaml` for the manifest format.