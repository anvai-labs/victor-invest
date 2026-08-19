"""Cross-company analysis services.

This package previously had no __init__.py, and `peer_comparison` existed here,
in `investigator/analysis/`, and in the unpackaged `patterns/analysis/` -- three
655-line copies differing only in a scipy import alias. The ambiguity was not
merely untidy: it stopped mypy resolving module names without namespace-package
guesswork, and the only live consumer imported the copy the wheel does not ship.
"""
