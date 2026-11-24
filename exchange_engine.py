"""
ECE-034: Mobile Phone Exchange and Buy-Back Valuation Engine
Team E029 (Rahul S J & Rakshitha L)

Usage:
    python exchange_engine.py sample_commands.txt [--out output_dir]

Reads a command file (LOAD_MODELS, LOAD_BLACKLIST, PROCESS_REQUESTS,
PRINT_REGISTER), values every exchange request, and writes
valuations.csv and daily_register.csv. See README.md and DECISION_LOG.md.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Business-rule constants (BR-xx numbers match DESIGN_DOCUMENT.md)
# --------------------------------------------------------------------------
# BR-03 age bands: (max age in months inclusive, % of base price)
AGE_BANDS = [(6, Decimal("85")), (12, Decimal("70")), (24, Decimal("55"))]
AGE_OLDEST_PCT = Decimal("40")  # 25 months and older
# BR-04 grade factors. A and D are confirmed by the sample pack (EC3, EC4);
# B and C are INFERRED (see DECISION_LOG D-04) and kept configurable here.
GRADE_PCT = {
    "A": Decimal("100"),
    "B": Decimal("75"),
    "C": Decimal("50"),
    "D": Decimal("25"),
}
NOT_ACCEPTED_GRADE = "E"  # BR-02: does not power on
# BR-05 deductions (Rs)
BATTERY_LIMIT = Decimal("80")  # strictly below -> deduction
BATTERY_DEDUCTION = Decimal("500")
CHARGER_DEDUCTION = Decimal("300")
BOX_DEDUCTION = Decimal("200")
# BR-06 minimum valuation before bonus (exactly Rs 500 is accepted)
MINIMUM_VALUE = Decimal("500")
# BR-07 new-phone bonus
BONUS_THRESHOLD = Decimal("20000")  # >= threshold
BONUS_AMOUNT = Decimal("2000")
# BR-08 cap and rounding
CAP_PCT = Decimal("70")
ROUND_TO = Decimal("10")

# Reason codes. The first three are from the brief; the rest are our own
# documented codes for invalid input rows (DECISION_LOG D-07).
BLACKLISTED = "BLACKLISTED"
NOT_ACCEPTED = "NOT_ACCEPTED"
BELOW_MINIMUM = "BELOW_MINIMUM"
INVALID_MODEL = "INVALID_MODEL"
INVALID_GRADE = "INVALID_GRADE"
INVALID_PURCHASE_DATE = "INVALID_PURCHASE_DATE"
INVALID_INPUT = "INVALID_INPUT"

VALUATION_COLUMNS = [
    "request_id", "request_date", "status", "reason_code", "model_code",
    "base_price", "age_months", "age_factor_pct", "value_after_age",
    "condition_grade", "grade_pct", "value_after_grade", "charger_deduction",
    "box_deduction", "battery_deduction", "value_after_deductions", "bonus",
    "cap_70pct", "final_valuation",
]
REGISTER_COLUMNS = [
    "request_date", "requests_total", "valued_count", "rejected_count",
    "blacklisted_count", "not_accepted_count", "below_minimum_count",
    "bonus_count", "total_valuation",
]

_CENT = Decimal("0.01")
_IMEI_RE = re.compile(r"^\d{15}$")
_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def money(value: Decimal) -> Decimal:
    """Round to 2 decimals, half up (D-09)."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def fmt_money(value: Optional[Decimal]) -> str:
    return "" if value is None else f"{money(value):.2f}"


def fmt_pct(value: Optional[Decimal]) -> str:
    """Whole percentages print without a decimal point (85, not 85.00)."""
    if value is None:
        return ""
    return str(int(value)) if value == value.to_integral_value() else f"{value.normalize():f}"


# --------------------------------------------------------------------------
# Pure rule functions (each one is unit-tested on its own)
# --------------------------------------------------------------------------
def age_in_months(request_date: date, purchase_month: str) -> int:
    """BR-03: (request year - purchase year) * 12 + (request month - purchase month)."""
    m = _MONTH_RE.match(purchase_month or "")
    if not m:
        raise ValueError(f"bad purchase_month {purchase_month!r}")
    return (request_date.year - int(m.group(1))) * 12 + (request_date.month - int(m.group(2)))


def age_factor_pct(months: int) -> Decimal:
    """BR-03: <=6 -> 85, <=12 -> 70, <=24 -> 55, older -> 40."""
    for limit, pct in AGE_BANDS:
        if months <= limit:
            return pct
    return AGE_OLDEST_PCT


def battery_deduction(battery_pct: Decimal) -> Decimal:
    """BR-05: strictly below 80% -> Rs 500; exactly 80 -> none."""
    return BATTERY_DEDUCTION if battery_pct < BATTERY_LIMIT else Decimal("0")


def bonus_for(new_phone_price: Optional[Decimal]) -> Decimal:
    """BR-07: blank -> none; >= Rs 20,000.00 -> Rs 2,000."""
    if new_phone_price is not None and new_phone_price >= BONUS_THRESHOLD:
        return BONUS_AMOUNT
    return Decimal("0")


def floor_to_ten(value: Decimal) -> Decimal:
    """BR-08: round DOWN to the nearest Rs 10."""
    return (value / ROUND_TO).to_integral_value(rounding=ROUND_DOWN) * ROUND_TO


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass
class Model:
    model_code: str
    brand: str
    model_name: str
    base_price: Decimal


@dataclass
class Result:
    """One valuations.csv row. None -> blank cell."""
    request_id: str
    request_date: str
    status: str = ""
    reason_code: str = ""
    model_code: str = ""
    base_price: Optional[Decimal] = None
    age_months: Optional[int] = None
    age_factor_pct: Optional[Decimal] = None
    value_after_age: Optional[Decimal] = None
    condition_grade: str = ""
    grade_pct: Optional[Decimal] = None
    value_after_grade: Optional[Decimal] = None
    charger_deduction: Optional[Decimal] = None
    box_deduction: Optional[Decimal] = None
    battery_deduction: Optional[Decimal] = None
    value_after_deductions: Optional[Decimal] = None
    bonus: Optional[Decimal] = None
    cap_70pct: Optional[Decimal] = None
    final_valuation: Optional[Decimal] = None

    def reject(self, code: str) -> "Result":
        self.status, self.reason_code = "REJECTED", code
        return self

    def row(self) -> list[str]:
        return [
            self.request_id, self.request_date, self.status, self.reason_code,
            self.model_code, fmt_money(self.base_price),
            "" if self.age_months is None else str(self.age_months),
            fmt_pct(self.age_factor_pct), fmt_money(self.value_after_age),
            self.condition_grade, fmt_pct(self.grade_pct),
            fmt_money(self.value_after_grade), fmt_money(self.charger_deduction),
            fmt_money(self.box_deduction), fmt_money(self.battery_deduction),
            fmt_money(self.value_after_deductions), fmt_money(self.bonus),
            fmt_money(self.cap_70pct), fmt_money(self.final_valuation),
        ]


class EngineError(Exception):
    """Fatal problem with a command or input file (not a bad request row)."""


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
@dataclass
class ExchangeEngine:
    models: dict[str, Model] = field(default_factory=dict)
    blacklist: set[str] = field(default_factory=set)
    results: list[Result] = field(default_factory=list)
    register_rows: list[list[str]] = field(default_factory=list)
    _seen_ids: set[str] = field(default_factory=set)

    # ---- loaders ---------------------------------------------------------
    def load_models(self, path: Path) -> None:
        for row in _read_csv(path, ["model_code", "brand", "model_name", "base_price"]):
            try:
                price = Decimal(row["base_price"].strip())
            except InvalidOperation:
                raise EngineError(f"{path.name}: bad base_price for {row['model_code']}")
            if price <= 0:
                raise EngineError(f"{path.name}: base_price must be > 0 for {row['model_code']}")
            code = row["model_code"].strip()
            self.models[code] = Model(code, row["brand"], row["model_name"], price)

    def load_blacklist(self, path: Path) -> None:
        for row in _read_csv(path, ["imei"]):
            self.blacklist.add(row["imei"].strip())

    # ---- valuation -------------------------------------------------------
    def process_requests(self, path: Path) -> None:
        cols = ["request_id", "request_date", "imei", "model_code", "purchase_month",
                "condition_grade", "battery_health_pct", "charger_present",
                "box_present", "new_phone_price"]
        for row in _read_csv(path, cols):
            rid = row["request_id"].strip()
            if rid in self._seen_ids:  # BR-01 / TRAP8: value a request_id once
                continue
            self._seen_ids.add(rid)
            self.results.append(self.value_request(row))

    def value_request(self, row: dict[str, str]) -> Result:
        rid = row["request_id"].strip()
        res = Result(rid, row["request_date"].strip(), model_code=row["model_code"].strip())

        # Request date must parse; everything else depends on it.
        try:
            req_date = date.fromisoformat(res.request_date)
        except ValueError:
            return res.reject(INVALID_INPUT)

        # 1. Blacklist before anything else (BR-02, TRAP2).
        if row["imei"].strip() in self.blacklist:
            return res.reject(BLACKLISTED)

        # 2. Field validation (D-07). Each failure gets its own reason code.
        model = self.models.get(res.model_code)
        if model is None:
            return res.reject(INVALID_MODEL)
        res.base_price = model.base_price

        grade = row["condition_grade"].strip().upper()
        res.condition_grade = row["condition_grade"].strip()
        if grade != NOT_ACCEPTED_GRADE and grade not in GRADE_PCT:
            return res.reject(INVALID_GRADE)

        if not _IMEI_RE.match(row["imei"].strip()):
            return res.reject(INVALID_INPUT)

        try:
            months = age_in_months(req_date, row["purchase_month"].strip())
        except ValueError:
            return res.reject(INVALID_PURCHASE_DATE)
        if months < 0:  # purchased after the request month (TRAP4)
            return res.reject(INVALID_PURCHASE_DATE)

        try:
            battery = Decimal(row["battery_health_pct"].strip())
            charger = _parse_bool(row["charger_present"])
            box = _parse_bool(row["box_present"])
            new_price = _parse_optional_price(row["new_phone_price"])
        except (InvalidOperation, ValueError):
            return res.reject(INVALID_INPUT)
        if not (Decimal("0") <= battery <= Decimal("100")):
            return res.reject(INVALID_INPUT)

        # 3. Age (BR-03).
        res.age_months = months
        res.age_factor_pct = age_factor_pct(months)
        res.value_after_age = money(model.base_price * res.age_factor_pct / 100)

        # 4. Grade E is not accepted (BR-02).
        if grade == NOT_ACCEPTED_GRADE:
            return res.reject(NOT_ACCEPTED)

        # 5. Grade (BR-04).
        res.grade_pct = GRADE_PCT[grade]
        res.value_after_grade = money(res.value_after_age * res.grade_pct / 100)

        # 6. Deductions (BR-05).
        res.charger_deduction = Decimal("0") if charger else CHARGER_DEDUCTION
        res.box_deduction = Decimal("0") if box else BOX_DEDUCTION
        res.battery_deduction = battery_deduction(battery)
        res.value_after_deductions = (
            res.value_after_grade - res.charger_deduction
            - res.box_deduction - res.battery_deduction
        )

        # 7. Minimum before bonus (BR-06). Exactly Rs 500 is accepted.
        if res.value_after_deductions < MINIMUM_VALUE:
            return res.reject(BELOW_MINIMUM)

        # 8. Bonus, 70% cap, round down to Rs 10 (BR-07, BR-08).
        res.bonus = bonus_for(new_price)
        cap_limit = money(model.base_price * CAP_PCT / 100)
        res.cap_70pct = min(res.value_after_deductions + res.bonus, cap_limit)
        res.final_valuation = floor_to_ten(res.cap_70pct)
        res.status = "VALUED"
        return res

    # ---- register --------------------------------------------------------
    def print_register(self, day: str) -> list[str]:
        try:
            date.fromisoformat(day)
        except ValueError:
            raise EngineError(f"PRINT_REGISTER: bad date {day!r}")
        rows = [r for r in self.results if r.request_date == day]
        valued = [r for r in rows if r.status == "VALUED"]

        def count(code: str) -> int:
            return sum(1 for r in rows if r.reason_code == code)

        total = sum((r.final_valuation for r in valued), Decimal("0"))
        out = [
            day, str(len(rows)), str(len(valued)), str(len(rows) - len(valued)),
            str(count(BLACKLISTED)), str(count(NOT_ACCEPTED)), str(count(BELOW_MINIMUM)),
            str(sum(1 for r in valued if r.bonus and r.bonus > 0)), fmt_money(total),
        ]
        self.register_rows.append(out)
        return out

    # ---- output ----------------------------------------------------------
    def write_outputs(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(out_dir / "valuations.csv", VALUATION_COLUMNS, [r.row() for r in self.results])
        _write_csv(out_dir / "daily_register.csv", REGISTER_COLUMNS, self.register_rows)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _parse_bool(text: str) -> bool:
    t = text.strip().lower()
    if t == "true":
        return True
    if t == "false":
        return False
    raise ValueError(text)


def _parse_optional_price(text: str) -> Optional[Decimal]:
    t = text.strip()
    if t == "":
        return None
    price = Decimal(t)
    if price <= 0:
        raise ValueError(text)
    return price


def _read_csv(path: Path, required: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise EngineError(f"file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise EngineError(f"{path.name}: missing columns {missing}")
        return [{k: (v or "") for k, v in row.items()} for row in reader]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def run_commands(command_file: Path, out_dir: Path) -> ExchangeEngine:
    """Execute a command file in file order (BR-09)."""
    engine = ExchangeEngine()
    base = command_file.resolve().parent
    for n, raw in enumerate(command_file.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        cmd, args = parts[0].upper(), parts[1:]
        try:
            if cmd in ("LOAD_MODELS", "LOAD_BLACKLIST", "PROCESS_REQUESTS"):
                if len(args) != 1:
                    raise EngineError(f"{cmd} takes 1 argument")
                target = base / args[0]
                {"LOAD_MODELS": engine.load_models,
                 "LOAD_BLACKLIST": engine.load_blacklist,
                 "PROCESS_REQUESTS": engine.process_requests}[cmd](target)
            elif cmd == "PRINT_REGISTER":
                if len(args) != 1:
                    raise EngineError("PRINT_REGISTER takes 1 argument")
                if not engine.register_rows:
                    print(",".join(REGISTER_COLUMNS))
                print(",".join(engine.print_register(args[0])))
            else:
                raise EngineError(f"unknown command {cmd!r}")
        except EngineError as exc:
            raise EngineError(f"{command_file.name} line {n}: {exc}") from None
    engine.write_outputs(out_dir)
    return engine


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ECE-034 phone buy-back valuation engine")
    ap.add_argument("commands", type=Path, help="command file")
    ap.add_argument("--out", type=Path, default=Path("output"), help="output directory")
    args = ap.parse_args(argv)
    try:
        engine = run_commands(args.commands, args.out)
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(engine.results)} valuations and {len(engine.register_rows)} "
          f"register rows to {args.out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
