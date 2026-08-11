"""
InvestiGator CLI Entry Point

Enables running InvestiGator as a module:
    python -m investigator [command] [options]
"""

# Previously this inserted the repo root into sys.path and imported a top-level
# `cli_orchestrator` module. That works from a clone and fails from an install:
# the wheel ships `investigator*` and `victor_invest*` only, so `python -m
# investigator` raised ModuleNotFoundError for anyone who pip-installed. The
# packaged CLI is the same click group.
from investigator.cli.orchestrator import cli

if __name__ == "__main__":
    cli()
