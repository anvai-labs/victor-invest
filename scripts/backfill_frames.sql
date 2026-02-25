-- Backfill correct frame values for sec_companyfacts_processed
--
-- This script fixes incorrect frame values by calculating them from period_end_date
-- The SEC Company Facts API often doesn't populate the frame field correctly,
-- especially for companies with non-calendar fiscal years.
--
-- Author: InvestiGator Team
-- Date: 2026-02-24

-- Update frame for all entries where it's missing or incorrect
-- Calculate frame as 'CY' + calendar_year + 'Q' + calendar_quarter
UPDATE sec_companyfacts_processed
SET frame = 'CY' || EXTRACT(YEAR FROM period_end_date::date) ||
            'Q' || EXTRACT(QUARTER FROM period_end_date::date)
WHERE frame IS NULL
   OR frame = ''
   OR frame NOT LIKE 'CY%Q%';

-- Verify the update for STX
SELECT
    symbol,
    fiscal_year,
    fiscal_period,
    period_end_date,
    frame,
    filed_date,
    net_income
FROM sec_companyfacts_processed
WHERE symbol = 'STX'
  AND fiscal_year >= 2025
ORDER BY period_end_date;

-- Expected output for STX after fix:
-- fiscal_year | fiscal_period | period_end_date | frame    | filed_date  | net_income
-- 2025        | Q1            | 2024-09-27     | CY2024Q3 | 2024-10-25  | 305000000
-- 2025        | Q2            | 2024-12-27     | CY2024Q4 | 2025-01-24  | 336000000
-- 2025        | Q3            | 2025-03-27     | CY2025Q1 | 2025-05-02  | 340000000
-- 2025        | FY            | 2025-06-27     | CY2025Q2 | 2025-08-01  | 1469000000  <-- FIXED (was CY2024)
-- 2026        | Q1            | 2025-09-27     | CY2025Q3 | 2025-10-31  | 549000000
-- 2026        | Q2            | 2025-12-27     | CY2025Q4 | 2026-01-30  | 593000000
