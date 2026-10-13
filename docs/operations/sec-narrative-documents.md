# SEC Narrative Documents

Victor Invest derives management commentary from immutable SEC source documents
stored in PostgreSQL. It does not download filing HTML, call AgentBrowser, solve a
CAPTCHA, or ask an LLM to collect the source. The split is intentional:

```text
ibkrtrading collector -> sec_filing_document -> Victor verification/extraction -> synthesis
```

`ibkrtrading` owns the SEC identity, rate limit, retries, bounded downloads, and
durable source writes. Victor's interactive analysis path is a read-only consumer.
It verifies the stored byte length, SHA-256 digest, form/document role, and
canonical SEC archive URL before parsing. A separate deterministic operator job
may write parser-versioned outcomes to Victor's derived table.

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

## Canonical narrative sections

The `sec_filing_text` tool recognizes these form-aware boundaries. Base-form
requests also consider amended filings; a 10-K/A or 10-Q/A uses the same canonical
definition and retains `is_amendment` in its provenance.

| Action | Form | `canonical_section` | Boundary |
|---|---|---|---|
| `get_business_overview` | 10-K | `10k_item_1_business` | Item 1 through the next item |
| `get_risk_factors` | 10-K | `10k_item_1a_risk_factors` | Item 1A through the next item |
| `get_mda` | 10-K | `10k_item_7_mda` | Item 7 through Item 7A |
| `get_market_risk` | 10-K | `10k_item_7a_market_risk` | Item 7A through the next item |
| `get_mda` | 10-Q | `10q_part_i_item_2_mda` | Part I, Item 2 through the next item |
| `get_market_risk` | 10-Q | `10q_part_i_item_3_market_risk` | Part I, Item 3 through the next item or part |
| `get_risk_factors` | 10-Q | `10q_part_ii_item_1a_risk_factors` | Part II, Item 1A through the next item |

Part scoping prevents a quarterly Item 2 or Item 1A in the wrong part from being
accepted. Repeated table-of-contents headings are evaluated as candidates and the
substantive body section wins. If the requested item, title, or part is absent, the
tool returns a failure instead of substituting nearby filing text. Inline XBRL tags
and HTML entities are normalized while evidence offsets continue to reference the
exact immutable source bytes.

## Materialize derivation outcomes

Apply Victor's migration to the same PostgreSQL database after the producer's
`sec_filing_document` migrations:

```bash
psql --set ON_ERROR_STOP=1 --file schema/migrations/015_add_sec_derived_sections.sql
```

Run migrations as the schema owner. For routine materialization, create a separate
least-privilege login; do not reuse the owner or the interactive reader:

```sql
GRANT USAGE ON SCHEMA public TO victor_sec_materializer;
GRANT SELECT ON TABLE public.sec_filing_document TO victor_sec_materializer;
GRANT SELECT, INSERT ON TABLE public.victor_sec_derived_section TO victor_sec_materializer;
```

Put its SQLAlchemy PostgreSQL URL in the protected runtime environment. It is
intentionally a different variable from the interactive reader:

```bash
export SEC_DERIVATION_DATABASE_URL='postgresql+psycopg2://victor_sec_materializer:<password>@<host>:5432/<database>'
python scripts/materialize_sec_sections.py --limit 25 --dry-run
python scripts/materialize_sec_sections.py --limit 25
```

Use a timezone-aware `--as-of` to materialize a historical evidence cutoff. The
job is bounded, processes oldest eligible source versions first, and prints only
counts. Re-run it until `documents` is zero. It never emits filing text or database
credentials.

Each immutable key includes accession, document role, source digest, canonical
section, and parser version. A successful row stores normalized text plus exact
source-byte offsets and digests. Missing, invalid-source, and parser-error rows
store an explicit failure code and reason. `confidence = 1.000` means the exact
form/part/item/title structural rule matched; it is not a probability that the
filing or an investment conclusion is true. A different result under the same key
is treated as a conflict rather than overwritten. A future parser version creates
new rows and preserves the old evidence.

Inspect outcomes without selecting narrative text:

```sql
SELECT parser_version, status, canonical_section, count(*) AS outcomes,
       max(derived_at) AS latest_derivation
FROM public.victor_sec_derived_section
GROUP BY parser_version, status, canonical_section
ORDER BY parser_version, canonical_section, status;
```

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
| Materializer permission denied | Grants for `victor_sec_materializer` | Restore only source/derived `SELECT` and derived `INSERT`; never grant source writes. |
| Repeated `missing` outcome | Canonical section, form, and parser version | Review the stored source fixture; fix the parser under a new version rather than editing the row. |
| Immutable derivation conflict | Existing and newly computed outcome digests | Stop and investigate nondeterminism or an unversioned parser change; never update the row in place. |

Do not log either database URL, return `content_bytes` through the API, weaken the
digest check, grant the materializer `UPDATE`/`DELETE` or source-table writes, or
add a direct SEC/browser fallback to the Victor process.
