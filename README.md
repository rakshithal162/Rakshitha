# E029 ECE-034 Mobile Phone Exchange and Buy-Back Valuation Engine

Team E029 built a Python command-line engine that values mobile-phone exchange requests: it rejects blacklisted or unusable phones, applies age, condition, battery, charger and box adjustments, adds the new-phone bonus, caps the result at 70% of the base price, and rounds down to the nearest Rs 10. It also produces a daily valuation register.

## Team

- Rahul S J
- Rakshitha L

## Requirements

- Python 3.10 or newer (standard library only)
- `pytest` for the test suite

## Setup

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

## Run

```powershell
python exchange_engine.py sample_commands.txt --out output
```

Commands are processed in file order. Lines beginning with `#` are comments. File names are resolved relative to the command file.

```text
LOAD_MODELS      | <models.csv>
LOAD_BLACKLIST   | <blacklist.csv>
PROCESS_REQUESTS | <requests.csv>
PRINT_REGISTER   | <YYYY-MM-DD>
```

Outputs (written to `--out`, default `output/`):

- `valuations.csv` — one row per unique request, in input order, 19 columns as specified in the data-pack README.
- `daily_register.csv` — one row per `PRINT_REGISTER` command.

## Business rules

| ID | Rule |
|---|---|
| BR-01 | A `request_id` is valued once; later rows with the same ID are ignored. |
| BR-02 | Check order: blacklisted IMEI → `BLACKLISTED`; grade E → `NOT_ACCEPTED`. Blacklist always wins. |
| BR-03 | Age in months = (request year − purchase year) × 12 + (request month − purchase month). 0–6 → 85%, 7–12 → 70%, 13–24 → 55%, 25+ → 40% of base price. |
| BR-04 | Grade factor: A 100%, B 75%, C 50%, D 25% (B and C inferred; see DECISION_LOG D-04). |
| BR-05 | Deductions: battery strictly below 80% → Rs 500 (exactly 80 → none); no charger → Rs 300; no box → Rs 200. |
| BR-06 | Value after deductions below Rs 500 → `BELOW_MINIMUM`. Exactly Rs 500 is accepted. Checked before the bonus. |
| BR-07 | New phone price of Rs 20,000.00 or more → Rs 2,000 bonus. Blank or lower → none. |
| BR-08 | Value + bonus is capped at 70% of base price, then rounded **down** to the nearest Rs 10. |
| BR-09 | Commands run in file order; `PRINT_REGISTER` counts only requests with that `request_date`. |

Invalid input rows are rejected with our own codes: `INVALID_MODEL`, `INVALID_GRADE`, `INVALID_PURCHASE_DATE`, `INVALID_INPUT`.

## Validation and tests

```powershell
python -m pytest -v
```

The suite covers every planted scenario in the sample pack (EC1–EC5, TRAP1–TRAP8), each rule boundary, invalid-field handling, command errors, and an end-to-end run of the sample pack.

## Files

- `exchange_engine.py` — engine and command-line entry point.
- `test_exchange_engine.py` — pytest suite.
- `sample_commands.txt`, `sample_data/` — the sample data pack and a runnable command file.
- `output/` — `valuations.csv` and `daily_register.csv` generated from the sample pack.
- `DESIGN_DOCUMENT.md` — design and business-rule register.
- `output/pdf/E029_ECE034_Design_Document.pdf` — design document for submission.
- `DECISION_LOG.md` — design decisions and rationale.
- `VIVA_PREPARATION.md` — viva questions with answer points.
- `DEMO_SCRIPT.md` — five-minute screen-recording outline.
