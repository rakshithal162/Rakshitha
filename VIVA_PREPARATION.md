# Viva Preparation

Team E029 — ECE-034

1. **Why Decimal, not float?** Exact comparisons: Rs 500.00 must pass the minimum, and 85% of base prices must not drift. (D-02)
2. **Walk through the check order.** Duplicate → blacklist → validation → age → grade E → deductions → minimum → bonus → cap → floor. Blacklist before grade E because TRAP2.
3. **Why is the minimum checked before the bonus?** EC4 says Rs 500 "before bonus". A bonus must not rescue a worthless phone.
4. **How does the cap interact with the bonus?** EC3: 14,000 + 2,000 is capped to 70% of 20,000 = 14,000. The bonus still counts in `bonus_count`.
5. **What is the age of a phone bought this month?** 0 months, 85% band (TRAP3). A future purchase month is negative → `INVALID_PURCHASE_DATE`.
6. **Which rules are guesses?** Grade B and C factors, and the meaning of `cap_70pct`. Both are flagged in the decision log.
7. **Change a rule live: make the battery limit 85.** Edit `BATTERY_LIMIT` in `exchange_engine.py` and update `test_ec2_*`/`test_trap7_*`.
8. **Change a grade factor.** Edit `GRADE_PCT`; the tests for B and C fail until updated.
9. **How are duplicates detected?** A set of seen `request_id`s, kept across all `PROCESS_REQUESTS` calls.
10. **What happens on a malformed row?** It is rejected with an `INVALID_*` code; the run continues.
11. **How do you know it is correct without expected outputs?** 45 tests built from the planted EC/TRAP scenarios plus hand calculations in the design doc.
