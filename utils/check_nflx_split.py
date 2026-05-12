#!/usr/bin/env python3
"""Check if NFLX split is in database."""

import os

from sqlalchemy import create_engine, text

# Get database URL from environment or config
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    # Fallback to constructing from individual vars
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_DATABASE", "sec_database")
    db_user = os.environ.get("DB_USERNAME", "vijaysingh")
    db_pass = os.environ.get("DB_PASSWORD", "")
    db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

engine = create_engine(db_url)

with engine.connect() as conn:
    # Check for NFLX splits
    result = conn.execute(
        text(
            "SELECT symbol, split_date, split_ratio, description FROM stock_splits WHERE symbol = 'NFLX' ORDER BY split_date"
        )
    )
    rows = result.fetchall()
    if rows:
        print("NFLX splits found:")
        for row in rows:
            print(f"  {row[0]} | {row[1]} | {row[2]}x | {row[3]}")
    else:
        print("⚠️  No splits found for NFLX in database")

    # Check all splits in database
    print("\nAll splits in database:")
    result = conn.execute(text("SELECT symbol, split_date, split_ratio FROM stock_splits ORDER BY symbol, split_date"))
    for row in result.fetchall():
        print(f"  {row[0]} | {row[1]} | {row[2]}x")
