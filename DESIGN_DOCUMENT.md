---
title: "E029-ECE-034 – Design Document & Business Rule Register"
---

**Team E029:** Rahul S J, Rakshitha L  
**Problem:** ECE-034 Mobile Phone Exchange and Buy-Back Valuation Engine

# 1. Overview

A command-line engine reads a model catalogue, an IMEI blacklist and exchange requests, values each request, and writes `valuations.csv` and `daily_register.csv`.

# 2. Entities

| Entity | Fields | Source |
|---|---|---|
| Model | model_code (PK), brand, model_name, base_price | models.csv |
| BlacklistEntry | imei, reason, listed_on | blacklist.csv |
| Request | request_id (PK), request_date, imei, model_code (FK), purchase_month, condition_grade, battery_health_pct, charger_present, box_present, new_phone_price | requests.csv |
| Result | one row per unique request with 19 output columns | valuations.csv |
| RegisterRow | one row per date: counts and total valuation | daily_register.csv |

Relationships: a Request references one Model and may match one BlacklistEntry by IMEI; each Request yields exactly one Result; RegisterRow aggregates Results by request_date.

# 3. Request state diagram

```
RECEIVED --duplicate id--> SKIPPED
RECEIVED --IMEI blacklisted--> REJECTED(BLACKLISTED)
        --bad model/grade/IMEI/date/fields--> REJECTED(INVALID_*)
        --grade E--> REJECTED(NOT_ACCEPTED)
        --value after deductions < 500--> REJECTED(BELOW_MINIMUM)
        --otherwise--> VALUED
```

# 4. Valuation pipeline

1. value_after_age = base_price × age_factor
2. value_after_grade = value_after_age × grade_pct
3. value_after_deductions = value_after_grade − charger − box − battery
4. Reject if value_after_deductions < 500
5. cap_70pct = min(value_after_deductions + bonus, 0.70 × base_price)
6. final_valuation = cap_70pct rounded down to the nearest Rs 10

# 5. Business rule register

| ID | Rule | Test coverage |
|---|---|---|
| BR-01 | Value each request_id once | TRAP8 |
| BR-02 | Blacklist first, then grade E | TRAP2, br02 tests |
| BR-03 | Age bands 85/70/55/40 | EC1, TRAP3 |
| BR-04 | Grade A 100, B 75, C 50, D 25 | br04 tests |
| BR-05 | Battery < 80 → 500; no charger → 300; no box → 200 | EC2, TRAP7 |
| BR-06 | Minimum Rs 500 before bonus | EC4 |
| BR-07 | New phone ≥ 20,000 → +2,000 | EC5, TRAP1 |
| BR-08 | 70% cap, round down to Rs 10 | EC3 |
| BR-09 | Commands in file order | end-to-end test |

# 6. Invalid input handling

Invalid rows are rejected with `INVALID_MODEL`, `INVALID_GRADE`, `INVALID_PURCHASE_DATE` or `INVALID_INPUT` (TRAP4–TRAP6). Missing files and unknown commands stop the run with a message naming the command-file line.

# 7. Assumptions to confirm against the brief

- Grade B = 75% and C = 50% (inferred, D-04).
- `cap_70pct` holds the capped value, not the cap limit (D-10).

# 8. Module layout

`exchange_engine.py`: pure rule functions (`age_in_months`, `age_factor_pct`, `battery_deduction`, `bonus_for`, `floor_to_ten`), `ExchangeEngine` (loading, valuation, register, output), and `run_commands` / `main`.
