"""PD model and rating-style portfolio report tables on open credit card data.

Data: UCI "Default of Credit Card Clients" (Yeh and Lien, 2009; 30,000 clients, Taiwan, 2005).
Target: default in the following month, so this is a one-month PD on card data, not a 12-month bank PD.

Steps: stratified train/test split, WoE binning fitted on train only, logistic scorecard against
gradient boosting (Gini, AUC, KS), binomial calibration test per rating grade, stability (PSI),
and star-schema CSV tables for the Power BI report in powerbi/.
"""
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "default_of_credit_card_clients.xls"
OUT = ROOT / "powerbi" / "data"
MODEL = ROOT / "excel" / "data"
URL = "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip"
SEED = 42
BINS = 6
GRADES = 8
EPS = 0.5


def load():
    if not RAW.exists():
        RAW.parent.mkdir(exist_ok=True)
        blob = urllib.request.urlopen(URL, timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next(n for n in z.namelist() if n.endswith(".xls"))
            RAW.write_bytes(z.read(name))
    df = pd.read_excel(RAW, header=1)
    df = df.rename(columns={"default payment next month": "default", "PAY_0": "PAY_1"})
    return df.set_index("ID")


def features(df):
    x = pd.DataFrame(index=df.index)
    x["limit"] = df["LIMIT_BAL"]
    x["age"] = df["AGE"]
    x["pay_last"] = df["PAY_1"]
    x["pay_worst_6m"] = df[[f"PAY_{i}" for i in range(1, 7)]].max(axis=1)
    x["months_late_6m"] = (df[[f"PAY_{i}" for i in range(1, 7)]] > 0).sum(axis=1)
    x["utilisation"] = (df["BILL_AMT1"] / df["LIMIT_BAL"]).clip(-1, 2)
    bills = df[[f"BILL_AMT{i}" for i in range(1, 7)]].sum(axis=1)
    paid = df[[f"PAY_AMT{i}" for i in range(1, 7)]].sum(axis=1)
    x["pay_ratio_6m"] = (paid / bills.where(bills > 0)).clip(0, 2).fillna(2.0)
    return x


class WoE:
    """Quantile binning with weight of evidence, fitted on training data only."""

    def fit(self, x, y):
        self.edges, self.tables, self.iv = {}, {}, {}
        for col in x:
            edges = np.unique(np.quantile(x[col], np.linspace(0, 1, BINS + 1)))
            edges[0], edges[-1] = -np.inf, np.inf
            self.edges[col] = edges
            bins = pd.cut(x[col], edges, labels=False)
            good = (y == 0).groupby(bins).sum() + EPS
            bad = (y == 1).groupby(bins).sum() + EPS
            dist_good, dist_bad = good / good.sum(), bad / bad.sum()
            woe = np.log(dist_good / dist_bad)
            self.tables[col] = woe
            self.iv[col] = float(((dist_good - dist_bad) * woe).sum())
        return self

    def transform(self, x):
        out = pd.DataFrame(index=x.index)
        for col in x:
            bins = pd.cut(x[col], self.edges[col], labels=False)
            out[col] = bins.map(self.tables[col]).astype(float)
        return out


def scorecard(woe, lr, pdo=20.0, base_score=600.0, base_odds=50.0):
    """One row per variable and bin: bounds (lower, upper], WoE, coefficient and scorecard points.

    Points follow the usual scaling: score = offset + factor * ln(good:bad odds), 20 points to double the odds and
    600 points at odds of 50:1. The intercept and offset are spread evenly over the variables.
    """
    factor = pdo / np.log(2)
    offset = base_score - factor * np.log(base_odds)
    n = len(woe.tables)
    rows = []
    for (col, table), coef in zip(woe.tables.items(), lr.coef_[0]):
        edges = woe.edges[col]
        for b, w in table.items():
            b = int(b)
            logit_part = coef * w + lr.intercept_[0] / n
            rows.append({"variable": col, "bin": int(b), "lower": float(edges[b]), "upper": float(edges[b + 1]),
                         "woe": float(w), "coef": float(coef), "intercept": float(lr.intercept_[0]),
                         "points": float(offset / n - factor * logit_part)})
    return pd.DataFrame(rows)


def gini(y, p):
    return 2 * roc_auc_score(y, p) - 1


def ks(y, p):
    fpr, tpr, _ = roc_curve(y, p)
    return float((tpr - fpr).max())


def psi(expected, actual):
    e = expected.value_counts(normalize=True).sort_index().clip(lower=1e-6)
    a = actual.value_counts(normalize=True).reindex(e.index).fillna(1e-6).clip(lower=1e-6)
    return float(((a - e) * np.log(a / e)).sum())


def main():
    df = load()
    x, y = features(df), df["default"]
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.3, stratify=y, random_state=SEED)

    woe = WoE().fit(x_tr, y_tr)
    lr = LogisticRegression(max_iter=1000).fit(woe.transform(x_tr), y_tr)
    gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=SEED).fit(x_tr, y_tr)

    p_tr = pd.Series(lr.predict_proba(woe.transform(x_tr))[:, 1], index=x_tr.index)
    p_te = pd.Series(lr.predict_proba(woe.transform(x_te))[:, 1], index=x_te.index)
    p_gb = pd.Series(gb.predict_proba(x_te)[:, 1], index=x_te.index)

    # Rating grades: quantiles of the training PD, master scale PD = mean training default rate per grade
    edges = np.unique(np.quantile(p_tr, np.linspace(0, 1, GRADES + 1)))
    edges[0], edges[-1] = 0.0, 1.0
    grade = lambda p: pd.cut(p, edges, labels=False, include_lowest=True) + 1
    g_tr, g_te = grade(p_tr), grade(p_te)
    scale = y_tr.groupby(g_tr).mean()

    rows = []
    for g, group in y_te.groupby(g_te):
        test = binomtest(int(group.sum()), len(group), float(scale[g]))
        rows.append({"grade": int(g), "pd_lower": float(edges[g - 1]), "pd_upper": float(edges[g]),
                     "master_scale_pd": float(scale[g]), "clients": len(group),
                     "defaults": int(group.sum()), "observed_rate": float(group.mean()),
                     "binomial_p": float(test.pvalue)})
    calibration = pd.DataFrame(rows)

    metrics = {
        "clients": len(df), "default_rate": float(y.mean()), "test_clients": len(y_te),
        "logit_auc": float(roc_auc_score(y_te, p_te)), "logit_gini": float(gini(y_te, p_te)),
        "logit_gini_train": float(gini(y_tr, p_tr)), "logit_ks": ks(y_te, p_te),
        "gb_auc": float(roc_auc_score(y_te, p_gb)), "gb_gini": float(gini(y_te, p_gb)), "gb_ks": ks(y_te, p_gb),
        "grade_psi_train_test": psi(g_tr, g_te),
        "grades_rejected_5pct": int((calibration["binomial_p"] < 0.05).sum()), "grades": len(calibration),
        "iv": {k: round(v, 3) for k, v in sorted(woe.iv.items(), key=lambda kv: -kv[1])},
        "logit_coef": dict(zip(x.columns, np.round(lr.coef_[0], 3).tolist())),
    }

    # Star schema for Power BI, test sample only so the report shows out-of-sample figures
    OUT.mkdir(parents=True, exist_ok=True)
    MODEL.mkdir(parents=True, exist_ok=True)
    edu = {1: "Graduate school", 2: "University", 3: "High school"}
    fact = pd.DataFrame({
        "client_id": x_te.index, "grade": g_te.values, "pd_model": p_te.round(5).values, "default": y_te.values,
        "exposure_limit": df.loc[x_te.index, "LIMIT_BAL"].values, "balance": df.loc[x_te.index, "BILL_AMT1"].values,
        "segment_id": df.loc[x_te.index, "EDUCATION"].map(edu).fillna("Other").values,
        "age_band": pd.cut(df.loc[x_te.index, "AGE"], [0, 29, 39, 49, 200],
                           labels=["under 30", "30-39", "40-49", "50 plus"]).astype(str).values,
    })
    fact.to_csv(OUT / "fact_portfolio.csv", index=False)
    calibration.to_csv(OUT / "dim_grade.csv", index=False)
    bench = fact.groupby("segment_id").agg(benchmark_default_rate=("default", "mean"), clients=("default", "size")).reset_index()
    bench.to_csv(OUT / "dim_segment.csv", index=False)
    # Model parameters for the Excel calculator, and a sample of test clients to check it against
    scorecard(woe, lr).to_csv(MODEL / "scorecard.csv", index=False)
    check = x_te.sample(25, random_state=SEED).assign(pd_model=p_te, grade=g_te)
    check.reset_index().rename(columns={"ID": "client_id"}).to_csv(MODEL / "check_clients.csv", index=False)
    (ROOT / "results.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(calibration.round(4).to_string(index=False))
    print(bench.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
