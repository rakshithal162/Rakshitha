# Decision Log

Team E029 — ECE-034 Mobile Phone Exchange and Buy-Back Valuation Engine

- **D-01 — Python:** Python 3.10+ and the standard library only; `csv`, `decimal` and `datetime` cover everything needed.
- **D-02 — Decimal money:** All money uses `Decimal`, never `float`, so values like exactly Rs 500.00 and 85% of 9,562.50 compare exactly.
- **D-03 — Age bands:** Bands are `<=6 → 85`, `<=12 → 70`, `<=24 → 55`, otherwise 40. EC1 confirms 6/12/24/36 months; REQ-0097 (40 months old) confirms older phones stay at 40%.
- **D-04 — Grade factors (INFERRED):** The data pack confirms A = 100% (EC3) and D = 25% (EC4). B = 75% and C = 50% follow the 25-point step and are not confirmed. They live in one `GRADE_PCT` table so they can be changed in one line if the brief differs.
- **D-05 — Check order:** Duplicate ID → blacklist → field validation → age → grade E → deductions → minimum → bonus/cap. Blacklist first because TRAP2 requires BLACKLISTED over NOT_ACCEPTED.
- **D-06 — Minimum before bonus:** The Rs 500 test uses value after deductions, before the bonus (EC4). `>= 500` passes; a negative value is also BELOW_MINIMUM.
- **D-07 — Reason codes for invalid rows:** `INVALID_MODEL` (TRAP5), `INVALID_GRADE` (TRAP6), `INVALID_PURCHASE_DATE` (TRAP4, also malformed months), `INVALID_INPUT` (bad IMEI, battery, booleans, price, date). A bad row is rejected, never a crash.
- **D-08 — Duplicates:** The first row for a `request_id` wins; later rows with the same ID are skipped silently across all `PROCESS_REQUESTS` calls.
- **D-09 — Rounding:** Each step rounds to 2 decimals, half up. The final value rounds down to Rs 10 only at the end.
- **D-10 — `cap_70pct` column (INTERPRETED):** Holds the value after the 70% cap, i.e. `min(value_after_deductions + bonus, 0.70 × base_price)`, matching the other running-value columns. `final_valuation` is that value rounded down to Rs 10.
- **D-11 — Rejected-row columns:** Columns computed before the rejection are filled, the rest are blank. BLACKLISTED rows show only IDs, date and model code.
- **D-12 — `bonus_count`:** Counts VALUED rows with a bonus of Rs 2,000, even if the cap then absorbed it (EC3).
- **D-13 — Percent format:** Whole percentages print as `85`, not `85.00`.
- **D-14 — Register scope:** `PRINT_REGISTER` counts unique requests by `request_date`; `rejected_count` includes invalid-input rejections.
