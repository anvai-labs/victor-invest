import logging

from investigator.domain.services.industry_classifier import IndustryClassifier


def _classifier_without_sources():
    classifier = IndustryClassifier.__new__(IndustryClassifier)
    classifier.sic_map = {}
    classifier.symbol_overrides = {}
    classifier.russell1000_overrides = {}
    classifier.db_engine = None
    classifier._query_database_industry = lambda _symbol: (None, None, None)
    return classifier


def test_classify_unclassified_logs_info_not_warning(caplog):
    classifier = _classifier_without_sources()

    with caplog.at_level(logging.INFO, logger="investigator.domain.services.industry_classifier"):
        sector, industry = classifier.classify("TEST")

    assert sector is None
    assert industry is None
    matching = [r for r in caplog.records if "Unable to classify TEST - no SIC code or profile data" in r.message]
    assert any(r.levelno == logging.INFO for r in matching)
    assert not any(r.levelno >= logging.WARNING for r in matching)
