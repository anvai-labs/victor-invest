# SEC Narrative Documents

Victor Invest derives management commentary from immutable SEC source documents
stored in PostgreSQL. It does not download filing HTML, call AgentBrowser, solve a
CAPTCHA, or ask an LLM to collect the source. The split is intentional:

```text
ibkrtrading collector -> sec_filing_document -> Victor verification/extraction -> synthesis
```

`ibkrtrading` owns the SEC identity, rate limit, retries, bounded downloads, and
durable writes. Victor is a read-only consumer. It verifies the stored byte length,
SHA-256 digest, form/document role, and canonical SEC archive URL before parsing.

## Configure the consumer

Prefer a PostgreSQL role that can only read the narrative table. Have the database
operator create and rotate the credential; do not commit it.

```sql
GRANT USAGE ON SCHEMA public TO victor_sec_reader;
GRANT SELECT ON TABLE public.sec_filing_document TO victor_sec_reader;
```

Set one connection URL in the protected runtime environment:

```bash
export SEC_DOCUMENT_DATABASE_URL='postgresql+psycopg2://victor_sec_reader:<password>@<host>:5432/<database>'
```

`SEC_DOCUMENT_DATABASE_URL` takes precedence. For compatibility, Victor can use
all five `SEC_DB_HOST`, `SEC_DB_PORT`, `SEC_DB_NAME`, `SEC_DB_USER`, and
`SEC_DB_PASSWORD` variables, then the configured SEC database. The consumer uses a
small pool (two base connections and two overflow connections) and requires
PostgreSQL.

## Populate source documents

Run the producer from an `ibkrtrading` checkout after its SEC migrations have been
applied. Begin with a bounded pilot:

```bash
cargo run --release --bin ibkr-trading -- sec13f migrate
cargo run --release --bin ibkr-trading -- sec-filings sync \
  --symbols AAPL,MSFT,NVDA --from-date 2025-01-01
```

The producer stores 10-K/10-Q primary documents and complete 8-K submissions. A
complete submission retains Exhibit 99.1 evidence. The default producer limit is
64 MiB; Victor rejects any row above its 256 MiB hard safety limit.

## Verify readiness

Use a read-only session and inspect freshness by form and document role:

```sql
SELECT form_type, document_kind, count(*) AS versions,
       max(available_at) AS newest_available,
       max(retrieved_at) AS newest_retrieved
FROM sec_filing_document
GROUP BY form_type, document_kind
ORDER BY form_type, document_kind;
```

Check one issuer without returning document bytes:

```sql
SELECT issuer_ticker, form_type, document_kind, accession_no,
       report_period_end, available_at, retrieved_at, byte_length,
       content_sha256
FROM sec_filing_document
WHERE issuer_ticker = 'AAPL'
ORDER BY available_at DESC, retrieved_at DESC
LIMIT 10;
```

Then run a Victor workflow that includes management discussion. Returned sources
contain the accession, source digest, availability/retrieval timestamps, parser
version, normalized-text digest, and exclusive source-byte offsets. The offsets can
be applied directly to `content_bytes` to recover the cited raw evidence.

## Point-in-time behavior

The optional tool parameter `as_of` must be an ISO 8601 date-time with a timezone.
Victor only admits rows whose `available_at` and `retrieved_at` are both at or
before that cutoff. `period` accepts `latest`, an ISO date, or `YYYY-Q1` through
`YYYY-Q4`. Invalid or timezone-free values fail closed.

This distinction prevents a document first retrieved later, including a changed
digest for an older accession, from leaking into an earlier backtest.

## Failure guide

| Symptom | Check | Action |
|---|---|---|
| Database configuration error | `SEC_DOCUMENT_DATABASE_URL` or all `SEC_DB_*` values | Supply the protected read-only credential. |
| No filing text for a symbol | Readiness queries and producer logs | Run a bounded producer sync; do not enable a Victor network fallback. |
| Digest or byte-length mismatch | `byte_length`, `content_sha256`, and PostgreSQL storage health | Quarantine the row and re-run the producer with `--force`; do not bypass verification. |
| No 8-K developments | `document_kind = 'complete_submission'` rows | Sync 8-K source documents and confirm the filing contains Item 2.02 or Exhibit 99.1. |
| Historical result unexpectedly empty | `available_at`, `retrieved_at`, and requested `as_of` | Correct the cutoff or document why the evidence was unavailable then. |
| PostgreSQL permission denied | Grants for the reader role | Restore `USAGE` and table-level `SELECT`; do not grant write privileges. |

Do not log the database URL, return `content_bytes` through the API, weaken the
digest check, or add a direct SEC/browser fallback to the Victor process.
