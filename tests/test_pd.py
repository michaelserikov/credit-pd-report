import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_pd import WoE, features, gini, ks, psi  # noqa: E402


def raw_frame():
    data = {"LIMIT_BAL": [1000, 2000], "AGE": [30, 40]}
    for i in range(1, 7):
        data[f"PAY_{i}"] = [2, -1]
        data[f"BILL_AMT{i}"] = [500, 0]
        data[f"PAY_AMT{i}"] = [50, 0]
    return pd.DataFrame(data)


def test_features_count_late_months_and_ratios():
    x = features(raw_frame())
    assert x.loc[0, "months_late_6m"] == 6
    assert x.loc[1, "months_late_6m"] == 0
    assert x.loc[0, "pay_worst_6m"] == 2
    assert x.loc[0, "utilisation"] == pytest.approx(0.5)
    assert x.loc[0, "pay_ratio_6m"] == pytest.approx(0.1)


def test_pay_ratio_without_bills_is_capped():
    assert features(raw_frame()).loc[1, "pay_ratio_6m"] == 2.0


def test_woe_sign_and_no_missing_on_new_values():
    rng = np.random.default_rng(0)
    x = pd.DataFrame({"a": rng.normal(size=4000)})
    y = pd.Series((x["a"] + rng.normal(size=4000) > 1).astype(int))
    woe = WoE().fit(x, y)
    table = woe.tables["a"]
    assert table.iloc[0] > table.iloc[-1]
    assert woe.iv["a"] > 0.1
    out = woe.transform(pd.DataFrame({"a": [-100.0, 100.0]}))
    assert out["a"].notna().all()


def test_gini_ks_perfect_and_random():
    y = np.array([0, 0, 1, 1])
    assert gini(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert ks(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert gini(y, np.array([0.5, 0.5, 0.5, 0.5])) == pytest.approx(0.0)


def test_psi_zero_for_same_distribution_and_positive_for_shift():
    a = pd.Series([1, 1, 2, 2, 3, 3])
    assert psi(a, a) == pytest.approx(0.0)
    assert psi(a, pd.Series([1, 1, 1, 1, 1, 3])) > 0.1
