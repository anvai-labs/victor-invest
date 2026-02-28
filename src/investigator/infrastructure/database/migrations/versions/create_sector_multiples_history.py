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

"""Create sector_multiples_history table for tracking historical sector multiples.

Revision ID: 001_create_sector_multiples_history
Create Date: 2026-02-21
"""

import logging
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()


class SectorMultiplesHistory(Base):
    """Historical sector/industry valuation multiples over time.

    Tracks how sector multiples change over time to identify swelling and shrinking trends.
    Uses FY (Fiscal Year) data aligned with real TTM for accurate historical comparison.

    Table: sector_multiples_history
    """

    __tablename__ = "sector_multiples_history"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Hierarchical columns (NEW - enables sector > industry tracking)
    sector_name = Column(String(255), nullable=True, index=True)  # Parent sector
    industry_name = Column(String(255), nullable=True, index=True)  # Industry (NULL for sector-level)

    # Legacy columns (kept for backward compatibility)
    group_name = Column(String(255), nullable=True, index=True)
    group_type = Column(String(20), nullable=True, index=True)

    # Fiscal year for this snapshot (e.g., 2023, 2024)
    fiscal_year = Column(Integer, nullable=False, index=True)

    # Date when data was "announced" (end of quarter + 1 month proxy)
    # This aligns with when FY results would be publicly available
    snapshot_date = Column(DateTime, nullable=False, index=True)

    # Calculated multiples
    pe_multiple = Column(Float, nullable=True)  # Price/Earnings
    ps_multiple = Column(Float, nullable=True)  # Price/Sales
    ev_ebitda_multiple = Column(Float, nullable=True)  # EV/EBITDA
    pb_multiple = Column(Float, nullable=True)  # Price/Book

    # Sample metadata
    sample_size = Column(Integer, nullable=False)  # Number of companies in sample

    # Percentile range used for outlier filtering
    percentile_low = Column(Float, nullable=False, default=0.05)
    percentile_high = Column(Float, nullable=False, default=0.95)

    # Additional context as JSON (renamed from 'metadata' to avoid SQLAlchemy conflict)
    additional_context = Column(Text, nullable=True)  # JSON string for additional context

    # Audit timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("sector_name", "industry_name", "fiscal_year", name="uix_sector_industry_fy"),
        UniqueConstraint("group_name", "group_type", "fiscal_year", name="uix_sector_history_fy"),
        Index("ix_sector_history_snapshot_date", "snapshot_date"),
        Index("ix_sector_history_group_type_year", "group_type", "fiscal_year"),
        {"schema": "public"},
    )

    def __repr__(self):
        return f"<SectorMultiplesHistory({self.group_type}:{self.group_name}, FY:{self.fiscal_year}, PE:{self.pe_multiple})>"


def upgrade():
    """Create the sector_multiples_history table."""
    from investigator.infrastructure.database.db import get_db_manager

    db_manager = get_db_manager()
    engine = db_manager.engine

    logger.info("Creating sector_multiples_history table...")
    Base.metadata.create_all(engine, tables=[SectorMultiplesHistory.__table__])
    logger.info("sector_multiples_history table created successfully")


def downgrade():
    """Drop the sector_multiples_history table."""
    from investigator.infrastructure.database.db import get_db_manager

    db_manager = get_db_manager()
    engine = db_manager.engine

    logger.info("Dropping sector_multiples_history table...")
    SectorMultiplesHistory.__table__.drop(engine)
    logger.info("sector_multiples_history table dropped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    upgrade()
