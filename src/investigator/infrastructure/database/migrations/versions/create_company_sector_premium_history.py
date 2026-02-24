# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create company_sector_premium_history table for tracking company premium/discount to sector.

Revision ID: 003_create_company_sector_premium_history
Create Date: 2026-02-22
"""

import logging
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()


class CompanySectorPremiumHistory(Base):
    """Historical company premium/discount to sector multiples over time.

    Tracks how individual companies trade relative to their sector/industry
    to identify mean reversion opportunities and consistent premium/discount patterns.

    For each company and period, stores:
    - Company's actual valuation multiple (P/E, P/S, P/B, EV/EBITDA)
    - Sector's median multiple for that period
    - Premium/discount percentage
    - Z-score (how many standard deviations from sector median)

    This enables:
    - Identifying companies with consistent premium (quality compounders)
    - Identifying companies with consistent discount (value opportunities)
    - Detecting mean reversion signals (significant deviations from historical premium)
    - Calculating company-specific fair value multiples

    Table: company_sector_premium_history
    """

    __tablename__ = "company_sector_premium_history"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Company identifier
    symbol = Column(String(20), nullable=False, index=True)

    # Sector/industry classification
    sector = Column(String(255), nullable=False, index=True)
    industry = Column(String(255), nullable=True, index=True)

    # Period identifier
    fiscal_year = Column(Integer, nullable=False, index=True)
    fiscal_period = Column(String(10), nullable=False, index=True)  # Q1, Q2, Q3, Q4, FY

    # Snapshot date (when data was available)
    snapshot_date = Column(DateTime, nullable=False, index=True)

    # Company's actual multiples
    pe_multiple = Column(Numeric(10, 2), nullable=True)  # Company's P/E
    ps_multiple = Column(Numeric(10, 2), nullable=True)  # Company's P/S
    pb_multiple = Column(Numeric(10, 2), nullable=True)  # Company's P/B
    ev_ebitda_multiple = Column(Numeric(10, 2), nullable=True)  # Company's EV/EBITDA

    # Sector's median multiples (for comparison)
    sector_pe_multiple = Column(Numeric(10, 2), nullable=True)
    sector_ps_multiple = Column(Numeric(10, 2), nullable=True)
    sector_pb_multiple = Column(Numeric(10, 2), nullable=True)
    sector_ev_ebitda_multiple = Column(Numeric(10, 2), nullable=True)

    # Premium/discount percentages
    # Formula: (Company Multiple - Sector Multiple) / Sector Multiple * 100
    # Positive = company trades at premium to sector
    # Negative = company trades at discount to sector
    pe_premium_pct = Column(Numeric(10, 2), nullable=True)
    ps_premium_pct = Column(Numeric(10, 2), nullable=True)
    pb_premium_pct = Column(Numeric(10, 2), nullable=True)
    ev_ebitda_premium_pct = Column(Numeric(10, 2), nullable=True)

    # Z-scores (standard deviations from sector median)
    # Measures how unusual the premium/discount is
    # Requires sector standard deviation (calculated during backfill)
    pe_z_score = Column(Numeric(10, 3), nullable=True)
    ps_z_score = Column(Numeric(10, 3), nullable=True)
    pb_z_score = Column(Numeric(10, 3), nullable=True)
    ev_ebitda_z_score = Column(Numeric(10, 3), nullable=True)

    # Sample metadata
    sector_sample_size = Column(
        Integer, nullable=True
    )  # Number of companies in sector sample

    # Additional context as JSON
    additional_context = Column(Text, nullable=True)

    # Audit timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "symbol", "fiscal_year", "fiscal_period", name="uix_company_premium_period"
        ),
        Index("ix_company_premium_sector_year", "sector", "fiscal_year"),
        Index("ix_company_premium_snapshot_date", "snapshot_date"),
        Index("ix_company_premium_symbol_date", "symbol", "snapshot_date"),
        {"schema": "public"},
    )

    def __repr__(self):
        return (
            f"<CompanySectorPremiumHistory({self.symbol}, "
            f"FY:{self.fiscal_year}, PE premium:{self.pe_premium_pct}%)>"
        )


def upgrade():
    """Create the company_sector_premium_history table."""
    from sqlalchemy import create_engine

    from investigator.config import get_config

    config = get_config()
    engine = create_engine(config.database.url)

    logger.info("Creating company_sector_premium_history table...")

    # Create the table
    CompanySectorPremiumHistory.__table__.create(engine, checkfirst=True)

    logger.info("company_sector_premium_history table created successfully")

    # Create indexes for common queries
    logger.info("Creating indexes for company_sector_premium_history...")

    from sqlalchemy import text

    with engine.connect() as conn:
        # Composite index for symbol+period lookups
        conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS ix_company_premium_symbol_period
            ON company_sector_premium_history(symbol, fiscal_year, fiscal_period)
        """)
        )

        # Index for sector-level queries
        conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS ix_company_premium_sector_period
            ON company_sector_premium_history(sector, fiscal_year, fiscal_period)
        """)
        )

        # Index for premium/discount analysis (PostgreSQL doesn't support partial indexes with IF NOT EXISTS in all versions)
        try:
            conn.execute(
                text("""
                CREATE INDEX ix_company_premium_pe_pct
                ON company_sector_premium_history(pe_premium_pct)
                WHERE pe_premium_pct IS NOT NULL
            """)
            )
        except Exception:
            # Index might already exist
            pass

    logger.info("Indexes created successfully")


def downgrade():
    """Drop the company_sector_premium_history table."""
    from sqlalchemy import create_engine

    from investigator.config import get_config

    config = get_config()
    engine = create_engine(config.database.url)

    logger.info("Dropping company_sector_premium_history table...")

    CompanySectorPremiumHistory.__table__.drop(engine, checkfirst=True)

    logger.info("company_sector_premium_history table dropped successfully")
