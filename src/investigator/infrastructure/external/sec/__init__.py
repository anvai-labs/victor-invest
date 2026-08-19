"""SEC external data sources: insider transactions and institutional holdings.

Every sibling under external/ had an __init__.py; this one did not, so the
modules here were only reachable as a namespace package. That is why
`investigator.infrastructure.external.sec.institutional_holdings` could not be
resolved by name.
"""
