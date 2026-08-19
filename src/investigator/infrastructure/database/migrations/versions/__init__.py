"""Schema migrations shipped with the package.

These carry an __init__.py because production code imports the version modules
directly (see company_premium_history and sector_multiples_history), so they are
part of the importable surface rather than a bare script directory.
"""
