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

"""Add sector_name and industry_name columns to sector_multiples_history table.

This enables tracking the hierarchy:
- Sector-level aggregates: sector_name='Financials', industry_name=NULL
- Industry-level aggregates: sector_name='Financials', industry_name='Credit Services'

Revision ID: 002_add_sector_industry_columns
Create Date: 2026-02-28
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
    text,
)
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()


class SectorMultiplesHistory(Base):
    """Model for sector_multiples_history table with new columns."""

    __tablename__ = "sector_multiples_history"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # NEW: Hierarchical columns
    sector_name = Column(String(255), nullable=True, index=True)  # Parent sector (NULL for old records)
    industry_name = Column(String(255), nullable=True, index=True)  # Industry (NULL for sector-level)

    # Legacy columns (kept for backward compatibility during migration)
    group_name = Column(String(255), nullable=True, index=True)
    group_type = Column(String(20), nullable=True, index=True)

    fiscal_year = Column(Integer, nullable=False, index=True)
    snapshot_date = Column(DateTime, nullable=False, index=True)

    pe_multiple = Column(Float, nullable=True)
    ps_multiple = Column(Float, nullable=True)
    ev_ebitda_multiple = Column(Float, nullable=True)
    pb_multiple = Column(Float, nullable=True)

    sample_size = Column(Integer, nullable=False)
    percentile_low = Column(Float, nullable=False, default=0.05)
    percentile_high = Column(Float, nullable=False, default=0.95)
    additional_context = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("sector_name", "industry_name", "fiscal_year", name="uix_sector_industry_fy"),
        Index("ix_sector_history_snapshot_date", "snapshot_date"),
        Index("ix_sector_history_group_type_year", "group_type", "fiscal_year"),
        {"schema": "public"},
    )


def upgrade():
    """Add sector_name and industry_name columns to sector_multiples_history table."""
    from investigator.infrastructure.database.db import get_db_manager

    db_manager = get_db_manager()
    engine = db_manager.engine

    logger.info("Adding sector_name and industry_name columns to sector_multiples_history...")

    with engine.begin() as conn:
        # Drop old unique constraint
        try:
            conn.execute(text("ALTER TABLE sector_multiples_history DROP CONSTRAINT IF EXISTS uix_sector_history_fy"))
            logger.info("Dropped old unique constraint uix_sector_history_fy")
        except Exception as e:
            logger.warning(f"Could not drop old constraint (may not exist): {e}")

        # Add new columns
        conn.execute(text("ALTER TABLE sector_multiples_history ADD COLUMN IF NOT EXISTS sector_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE sector_multiples_history ADD COLUMN IF NOT EXISTS industry_name VARCHAR(255)"))

        # Create indexes on new columns
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_sector_history_sector_name ON sector_multiples_history(sector_name)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_sector_history_industry_name ON sector_multiples_history(industry_name)"
            )
        )

        # Backfill existing data: derive sector_name and industry_name from group_name/group_type
        conn.execute(
            text("""
            UPDATE sector_multiples_history
            SET
                sector_name = CASE WHEN group_type = 'sector' THEN group_name ELSE NULL END,
                industry_name = CASE WHEN group_type = 'industry' THEN group_name ELSE NULL END
            WHERE sector_name IS NULL
        """)
        )

        # Add new unique constraint
        try:
            conn.execute(
                text("""
                ALTER TABLE sector_multiples_history
                ADD CONSTRAINT uix_sector_industry_fy
                UNIQUE (sector_name, industry_name, fiscal_year)
            """)
            )
            logger.info("Added new unique constraint uix_sector_industry_fy")
        except Exception as e:
            logger.warning(f"Could not add new unique constraint: {e}")

    logger.info("Migration completed successfully")


def downgrade():
    """Remove sector_name and industry_name columns from sector_multiples_history table."""
    from investigator.infrastructure.database.db import get_db_manager

    db_manager = get_db_manager()
    engine = db_manager.engine

    logger.info("Removing sector_name and industry_name columns...")

    with engine.begin() as conn:
        # Drop new unique constraint
        try:
            conn.execute(text("ALTER TABLE sector_multiples_history DROP CONSTRAINT IF EXISTS uix_sector_industry_fy"))
        except Exception as e:
            logger.warning(f"Could not drop new constraint: {e}")

        # Drop indexes
        try:
            conn.execute(text("DROP INDEX IF EXISTS ix_sector_history_sector_name"))
            conn.execute(text("DROP INDEX IF EXISTS ix_sector_history_industry_name"))
        except Exception as e:
            logger.warning(f"Could not drop indexes: {e}")

        # Drop columns
        conn.execute(text("ALTER TABLE sector_multiples_history DROP COLUMN IF EXISTS sector_name"))
        conn.execute(text("ALTER TABLE sector_multiples_history DROP COLUMN IF EXISTS industry_name"))

        # Restore old unique constraint
        try:
            conn.execute(
                text("""
                ALTER TABLE sector_multiples_history
                ADD CONSTRAINT uix_sector_history_fy
                UNIQUE (group_name, group_type, fiscal_year)
            """)
            )
        except Exception as e:
            logger.warning(f"Could not restore old constraint: {e}")

    logger.info("Rollback completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    upgrade()
