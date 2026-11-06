"""The SQL layer, the Excel calculator and the VBA test logic reproduce the Python model on the committed tables."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import binom, binomtest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_sql  # noqa: E402

DATA = ROOT / "powerbi" / "data"


@pytest.fixture(scope="module")
def sql():
    con = run_sql.connect()
    return {name: con.execute(q).df() for name, q in run_sql.queries().items()}


def test_sql_grade_summary_matches_grade_table(sql):
    grades = pd.read_csv(DATA / "dim_grade.csv")
    s = sql["grade_summary"]
    assert s["clients"].tolist() == grades["clients"].tolist()
    assert s["defaults"].astype(int).tolist() == grades["defaults"].tolist()
    assert s["cumulative_exposure_share"].iloc[-1] == pytest.approx(1.0)


def test_sql_gini_matches_python():
    con = run_sql.connect()
    gini = con.execute(run_sql.queries()["gini"]).fetchone()[0]
    expected = json.loads((ROOT / "results.json").read_text())["logit_gini"]
    assert gini == pytest.approx(expected, abs=2e-3)  # PDs in the table are rounded to five decimals


def test_benchmark_is_rate_of_all_segments_in_the_age_band(sql):
    fact = pd.read_csv(DATA / "fact_portfolio.csv")
    b = sql["segment_age_benchmark"]
    for band, rate in fact.groupby("age_band")["default"].mean().items():
        assert b.loc[b["age_band"] == band, "benchmark_rate"].unique() == pytest.approx([rate])


def test_cap_curve_ends_at_one_and_is_increasing(sql):
    cap = sql["cap_curve"]
    assert cap["cumulative_default_share"].is_monotonic_increasing
    assert cap["cumulative_default_share"].iloc[-1] == pytest.approx(1.0)


def scorecard_pd(row: pd.Series, sc: pd.DataFrame) -> float:
    """The Excel formula in Python: sum of WoE times coefficient over the bins (lower, upper] holding the values."""
    logit = sc["intercept"].iloc[0]
    for var, part in sc.groupby("variable", sort=False):
        hit = part[(part["lower"] < row[var]) & (part["upper"] >= row[var])]
        assert len(hit) == 1
        logit += float(hit["woe"].iloc[0] * hit["coef"].iloc[0])
    return 1 / (1 + np.exp(-logit))


def test_scorecard_table_reproduces_model_pd():
    sc = pd.read_csv(ROOT / "excel" / "data" / "scorecard.csv")
    check = pd.read_csv(ROOT / "excel" / "data" / "check_clients.csv")
    for _, row in check.iterrows():
        assert scorecard_pd(row, sc) == pytest.approx(row["pd_model"], abs=1e-12)


def vba_binomial_p(k: int, n: int, p: float) -> float:
    """Line by line the loop in excel/PortfolioTools.bas."""
    observed = binom.pmf(k, n, p)
    total = sum(binom.pmf(i, n, p) for i in range(n + 1) if binom.pmf(i, n, p) <= observed * (1 + 1e-7))
    return min(total, 1.0)


def test_vba_binomial_rule_matches_scipy():
    grades = pd.read_csv(DATA / "dim_grade.csv")
    for r in grades.itertuples():
        assert vba_binomial_p(r.defaults, r.clients, r.master_scale_pd) == pytest.approx(
            binomtest(r.defaults, r.clients, r.master_scale_pd).pvalue, rel=1e-6)
