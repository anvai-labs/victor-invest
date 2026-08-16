"""Outbound notifications: alerting and email delivery.

These lived in the repo-only utils/ tree, which the wheel does not ship, so the
imports in synthesizer.py raised ModuleNotFoundError for anyone who installed
rather than cloned. They are infrastructure -- outbound side effects -- so they
sit here.
"""
