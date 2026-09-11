-- Migration 015: Persist immutable Victor SEC canonical-section outcomes.
-- Apply this migration to the database that owns sec_filing_document.

CREATE TABLE IF NOT EXISTS public.victor_sec_derived_section (
    accession_no TEXT NOT NULL,
    document_kind TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    canonical_section TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    status TEXT NOT NULL,
    heading TEXT,
    source_start_byte BIGINT,
    source_end_byte BIGINT,
    normalized_text_sha256 TEXT,
    normalized_text TEXT,
    truncated BOOLEAN,
    confidence NUMERIC(4, 3),
    confidence_basis TEXT,
    failure_code TEXT,
    failure_reason TEXT,
    derived_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (accession_no, document_kind, content_sha256, canonical_section, parser_version),
    FOREIGN KEY (accession_no, document_kind, content_sha256)
        REFERENCES public.sec_filing_document (accession_no, document_kind, content_sha256),
    CONSTRAINT victor_sec_derived_section_source_digest
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT victor_sec_derived_section_text_digest
        CHECK (normalized_text_sha256 IS NULL OR normalized_text_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT victor_sec_derived_section_status
        CHECK (status IN ('success', 'missing', 'invalid_source', 'parse_error')),
    CONSTRAINT victor_sec_derived_section_canonical_name
        CHECK (canonical_section IN (
            '10k_item_1_business',
            '10k_item_1a_risk_factors',
            '10k_item_7_mda',
            '10k_item_7a_market_risk',
            '10q_part_i_item_2_mda',
            '10q_part_i_item_3_market_risk',
            '10q_part_ii_item_1a_risk_factors'
        )),
    CONSTRAINT victor_sec_derived_section_offsets
        CHECK (
            (source_start_byte IS NULL AND source_end_byte IS NULL)
            OR (source_start_byte >= 0 AND source_end_byte > source_start_byte)
        ),
    CONSTRAINT victor_sec_derived_section_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT victor_sec_derived_section_outcome_shape
        CHECK (
            (
                status = 'success'
                AND heading IS NOT NULL
                AND source_start_byte IS NOT NULL
                AND source_end_byte IS NOT NULL
                AND normalized_text_sha256 IS NOT NULL
                AND normalized_text IS NOT NULL
                AND truncated = FALSE
                AND confidence IS NOT NULL
                AND confidence_basis IS NOT NULL
                AND failure_code IS NULL
                AND failure_reason IS NULL
            )
            OR
            (
                status <> 'success'
                AND heading IS NULL
                AND source_start_byte IS NULL
                AND source_end_byte IS NULL
                AND normalized_text_sha256 IS NULL
                AND normalized_text IS NULL
                AND truncated IS NULL
                AND confidence IS NULL
                AND confidence_basis IS NULL
                AND failure_code IS NOT NULL
                AND failure_reason IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_victor_sec_derived_section_status
    ON public.victor_sec_derived_section (parser_version, status, canonical_section);

COMMENT ON TABLE public.victor_sec_derived_section IS
    'Append-only Victor outcomes derived from immutable SEC filing documents';
COMMENT ON COLUMN public.victor_sec_derived_section.confidence IS
    'Confidence in deterministic structural-rule match, not analyst truth probability';
