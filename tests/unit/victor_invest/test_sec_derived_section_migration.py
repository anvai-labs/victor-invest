from pathlib import Path


def test_sec_derived_section_migration_is_append_only_and_source_keyed() -> None:
    migration = (Path(__file__).parents[3] / "schema" / "migrations" / "015_add_sec_derived_sections.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS public.victor_sec_derived_section" in migration
    assert "FOREIGN KEY (accession_no, document_kind, content_sha256)" in migration
    assert "REFERENCES public.sec_filing_document (accession_no, document_kind, content_sha256)" in migration
    assert "PRIMARY KEY (accession_no, document_kind, content_sha256, canonical_section, parser_version)" in migration
    assert "status IN ('success', 'missing', 'invalid_source', 'parse_error')" in migration
    assert "10q_part_ii_item_1a_risk_factors" in migration
    assert "confidence >= 0 AND confidence <= 1" in migration
    assert "ON DELETE CASCADE" not in migration
