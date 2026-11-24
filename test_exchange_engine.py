"""
Pytest suite for ECE-034: Mobile Phone Exchange and Buy-Back Valuation Engine
Team E029 (Rahul S J & Rakshitha L).  Run with: python -m pytest -v
"""
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

import exchange_engine as ee
from exchange_engine import ExchangeEngine, Model

ROOT = Path(__file__).parent


def make_engine(base="20000.00", blacklist=()):
    eng = ExchangeEngine()
    eng.models["MDL-001"] = Model("MDL-001", "Brand", "Phone", D(base))
    eng.blacklist.update(blacklist)
    return eng


def req(**kw):
    row = dict(request_id="REQ-0001", request_date="2026-10-05", imei="350000000000001",
               model_code="MDL-001", purchase_month="2026-04", condition_grade="A",
               battery_health_pct="90.0", charger_present="true", box_present="true",
               new_phone_price="")
    row.update(kw)
    return row


def value(eng=None, **kw):
    return (eng or make_engine()).value_request(req(**kw))


# ---- BR-03 age bands (EC1: exactly 6/12/24/36 months) -------------------
@pytest.mark.parametrize("purchase,months,pct", [
    ("2026-10", 0, 85),    # TRAP3: same month
    ("2026-04", 6, 85),    # EC1
    ("2026-03", 7, 70),
    ("2025-10", 12, 70),   # EC1
    ("2025-09", 13, 55),
    ("2024-10", 24, 55),   # EC1
    ("2024-09", 25, 40),
    ("2023-10", 36, 40),   # EC1
    ("2021-01", 69, 40),   # older than 36 months
])
def test_br03_age_bands(purchase, months, pct):
    r = value(purchase_month=purchase)
    assert r.age_months == months
    assert r.age_factor_pct == D(pct)


def test_br03_age_crosses_year_boundary():
    assert ee.age_in_months(date(2026, 1, 15), "2025-12") == 1


# ---- BR-02 rejections and their precedence ------------------------------
def test_br02_blacklisted_rejected():
    r = value(make_engine(blacklist={"350000000000001"}))
    assert (r.status, r.reason_code) == ("REJECTED", ee.BLACKLISTED)


def test_trap2_blacklist_beats_grade_e():
    r = value(make_engine(blacklist={"350000000000001"}), condition_grade="E")
    assert r.reason_code == ee.BLACKLISTED


def test_br02_grade_e_not_accepted_keeps_age_columns():
    r = value(condition_grade="E")
    assert r.reason_code == ee.NOT_ACCEPTED
    assert r.value_after_age == D("17000.00") and r.value_after_grade is None


# ---- BR-04 grades --------------------------------------------------------
@pytest.mark.parametrize("grade,pct", [("A", 100), ("B", 75), ("C", 50), ("D", 25)])
def test_br04_grade_factors(grade, pct):
    assert value(condition_grade=grade).grade_pct == D(pct)


# ---- BR-05 deductions ----------------------------------------------------
def test_ec2_battery_exactly_80_no_deduction():
    assert value(battery_health_pct="80.0").battery_deduction == D("0")


def test_trap7_battery_79_5_deducts_500():
    assert value(battery_health_pct="79.5").battery_deduction == D("500")


def test_br05_charger_and_box_deductions():
    r = value(charger_present="false", box_present="false")
    assert (r.charger_deduction, r.box_deduction) == (D("300"), D("200"))


def test_br05_all_deductions_stack():
    r = value(purchase_month="2026-04", charger_present="false",
              box_present="false", battery_health_pct="50")
    assert r.value_after_deductions == D("17000") - D("1000")


# ---- BR-06 minimum -------------------------------------------------------
def test_ec4_exactly_500_is_accepted():
    # 8000 x 40% (age 36) x 25% (grade D) - 300 charger = 500.00
    r = value(make_engine("8000.00"), purchase_month="2023-10", condition_grade="D",
              charger_present="false")
    assert r.value_after_deductions == D("500.00")
    assert r.status == "VALUED" and r.final_valuation == D("500")


def test_br06_below_500_rejected_and_stops_before_bonus():
    r = value(make_engine("8000.00"), purchase_month="2023-10", condition_grade="D",
              charger_present="false", box_present="false", new_phone_price="50000")
    assert r.reason_code == ee.BELOW_MINIMUM
    assert r.value_after_deductions == D("300.00") and r.bonus is None


def test_br06_negative_value_is_below_minimum():
    r = value(make_engine("1000.00"), purchase_month="2023-10", condition_grade="D",
              charger_present="false", box_present="false", battery_health_pct="10")
    assert r.reason_code == ee.BELOW_MINIMUM


# ---- BR-07 bonus ---------------------------------------------------------
def test_ec5_new_phone_exactly_20000_gets_bonus():
    assert value(new_phone_price="20000.00", purchase_month="2024-10").bonus == D("2000")


def test_trap1_19999_no_bonus():
    assert value(new_phone_price="19999.00").bonus == D("0")


def test_br07_blank_new_phone_no_bonus():
    assert value(new_phone_price="").bonus == D("0")


# ---- BR-08 cap and rounding ---------------------------------------------
def test_ec3_bonus_pushed_over_70pct_cap():
    r = value(purchase_month="2026-01", new_phone_price="25000.00")  # 9 months
    assert r.value_after_deductions == D("14000.00")
    assert r.bonus == D("2000") and r.cap_70pct == D("14000.00")
    assert r.final_valuation == D("14000")


def test_br08_final_rounds_down_to_ten():
    r = value(make_engine("13000.00"), purchase_month="2026-01", condition_grade="B")
    assert r.cap_70pct == D("6825.00") and r.final_valuation == D("6820")


def test_br08_floor_to_ten_helper():
    assert ee.floor_to_ten(D("9999.99")) == D("9990")
    assert ee.floor_to_ten(D("10.00")) == D("10")


# ---- Invalid input rows (D-07) ------------------------------------------
def test_trap4_purchase_after_request_month():
    assert value(purchase_month="2026-11").reason_code == ee.INVALID_PURCHASE_DATE


def test_trap5_unknown_model():
    assert value(model_code="MDL-999").reason_code == ee.INVALID_MODEL


def test_trap6_invalid_grade_f():
    assert value(condition_grade="F").reason_code == ee.INVALID_GRADE


@pytest.mark.parametrize("field,bad", [
    ("imei", "123"), ("battery_health_pct", "101"), ("battery_health_pct", "abc"),
    ("charger_present", "yes"), ("new_phone_price", "-5"), ("purchase_month", "2026-13"),
    ("request_date", "2026-02-30"),
])
def test_invalid_fields_rejected_not_crash(field, bad):
    r = value(**{field: bad})
    assert r.status == "REJECTED"


# ---- BR-01 duplicates, BR-09 commands, outputs ---------------------------
def test_trap8_duplicate_request_valued_once(tmp_path):
    header = "request_id,request_date,imei,model_code,purchase_month,condition_grade,battery_health_pct,charger_present,box_present,new_phone_price\n"
    line = "REQ-0001,2026-10-05,350000000000001,MDL-001,2026-04,A,90.0,true,true,\n"
    f = tmp_path / "r.csv"
    f.write_text(header + line + line)
    eng = make_engine()
    eng.process_requests(f)
    assert len(eng.results) == 1


def test_missing_file_raises(tmp_path):
    with pytest.raises(ee.EngineError):
        ExchangeEngine().load_models(tmp_path / "nope.csv")


def test_unknown_command_reports_line(tmp_path):
    cmd = tmp_path / "c.txt"
    cmd.write_text("# c\nFLY_TO_MOON|x\n")
    with pytest.raises(ee.EngineError, match="line 2"):
        ee.run_commands(cmd, tmp_path / "out")


def test_sample_pack_end_to_end(tmp_path, capsys):
    eng = ee.run_commands(ROOT / "sample_commands.txt", tmp_path)
    assert len(eng.results) == 150  # 151 rows, one duplicate
    lines = (tmp_path / "valuations.csv").read_text().splitlines()
    assert lines[0].split(",") == ee.VALUATION_COLUMNS
    assert all(len(l.split(",")) == 19 for l in lines)
    reg = (tmp_path / "daily_register.csv").read_text().splitlines()
    assert reg[0].split(",") == ee.REGISTER_COLUMNS and len(reg) == 4


def test_register_counts_are_consistent(tmp_path):
    eng = ee.run_commands(ROOT / "sample_commands.txt", tmp_path)
    for row in eng.register_rows:
        total, valued, rejected = (int(x) for x in row[1:4])
        assert total == valued + rejected
