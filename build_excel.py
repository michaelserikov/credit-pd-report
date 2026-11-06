"""Excel PD calculator built from the fitted scorecard: formulas only, no macros.

Sheets: Calculator (enter one client, get WoE per variable, points, score, PD, grade and master scale PD), Scorecard
(bins, WoE, coefficients, points), MasterScale (grade bounds and PDs) and Check (25 test clients: the Excel PD next to
the Python PD). A bin is (lower, upper], as in pandas.cut, and comparisons are numeric, so values on a bin edge land in
the same bin as in Python.

    python build_excel.py      # after run_pd.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName

ROOT = Path(__file__).parent
DATA = ROOT / "excel" / "data"
OUT = ROOT / "excel" / "pd_calculator.xlsx"
BIG = 1e300
LABELS = {
    "limit": "Credit limit (NT$)",
    "age": "Age (years)",
    "pay_last": "Repayment status, last month (-2 to 8)",
    "pay_worst_6m": "Worst repayment status, 6 months",
    "months_late_6m": "Months late, last 6 (0 to 6)",
    "utilisation": "Utilisation, last bill / limit",
    "pay_ratio_6m": "Paid / billed, 6 months (0 to 2)",
}
BOLD = Font(bold=True)
INPUT = PatternFill("solid", fgColor="FFF2CC")


def name(wb, label, ref):
    wb.defined_names[label] = DefinedName(label, attr_text=ref)


def woe_term(var_cell: str, value_cell: str, column: str) -> str:
    """Sum over the scorecard rows of the variable whose bin (lower, upper] contains the value."""
    return f"SUMPRODUCT((sc_var={var_cell})*(sc_lower<{value_cell})*(sc_upper>={value_cell})*{column})"


def build() -> Path:
    sc = pd.read_csv(DATA / "scorecard.csv").replace([np.inf, -np.inf], [BIG, -BIG])
    grades = pd.read_csv(ROOT / "powerbi" / "data" / "dim_grade.csv")
    check = pd.read_csv(DATA / "check_clients.csv")
    variables = list(dict.fromkeys(sc["variable"]))

    wb = Workbook()
    calc = wb.active
    calc.title = "Calculator"

    # Scorecard
    ws = wb.create_sheet("Scorecard")
    cols = ["variable", "bin", "lower", "upper", "woe", "coef", "intercept", "points"]
    ws.append(cols)
    for row in sc[cols].itertuples(index=False):
        ws.append(list(row))
    last = len(sc) + 1
    for col, letter in zip(cols, "ABCDEFGH"):
        name(wb, "sc_var" if col == "variable" else f"sc_{col}", f"Scorecard!${letter}$2:${letter}${last}")
    ws["J1"], ws["J2"] = "Bins are (lower, upper]; +/-1E300 stands for infinity.", "Points: 20 points double the odds, 600 points at 50:1."
    for c in ws[1]:
        c.font = BOLD

    # Master scale
    ms = wb.create_sheet("MasterScale")
    ms.append(["grade", "pd_lower", "pd_upper", "master_scale_pd", "test_clients", "test_defaults", "observed_rate", "binomial_p"])
    for r in grades.itertuples(index=False):
        ms.append([r.grade, r.pd_lower, r.pd_upper, r.master_scale_pd, r.clients, r.defaults, r.observed_rate, r.binomial_p])
    g_last = len(grades) + 1
    name(wb, "ms_grade", f"MasterScale!$A$2:$A${g_last}")
    name(wb, "ms_upper", f"MasterScale!$C$2:$C${g_last}")
    name(wb, "ms_pd", f"MasterScale!$D$2:$D${g_last}")
    for c in ms[1]:
        c.font = BOLD

    # Calculator: one client
    calc["A1"] = "PD calculator, logistic WoE scorecard (UCI credit card data, one-month PD)"
    calc["A1"].font = Font(bold=True, size=13)
    calc["A2"] = "Enter values in the yellow cells. Example: test client " + str(int(check.loc[0, "client_id"]))
    calc.append([])
    calc.append(["Variable", "Description", "Value", "Bin", "WoE", "Coefficient", "Logit contribution", "Points"])
    for c in calc[4]:
        c.font = BOLD
    first = 5
    for i, v in enumerate(variables):
        r = first + i
        calc[f"A{r}"], calc[f"B{r}"], calc[f"C{r}"] = v, LABELS[v], float(check.loc[0, v])
        calc[f"C{r}"].fill = INPUT
        calc[f"D{r}"] = f"=SUMPRODUCT((sc_var=A{r})*(sc_upper<C{r}))"
        calc[f"E{r}"] = "=" + woe_term(f"A{r}", f"C{r}", "sc_woe")
        calc[f"F{r}"] = f"=SUMPRODUCT((sc_var=A{r})*(sc_bin=D{r})*sc_coef)"
        calc[f"G{r}"] = f"=E{r}*F{r}"
        calc[f"H{r}"] = "=" + woe_term(f"A{r}", f"C{r}", "sc_points")
    end = first + len(variables) - 1
    out = end + 2
    rows = [
        ("Intercept", "=INDEX(sc_intercept,1)"),
        ("Logit (log-odds of default)", f"=B{out}+SUM(G{first}:G{end})"),
        ("PD, one month", f"=1/(1+EXP(-B{out + 1}))"),
        ("Score (points)", f"=SUM(H{first}:H{end})"),
        ("Grade", f"=SUMPRODUCT(--(ms_upper<B{out + 2}))+1"),
        ("Master scale PD", f"=INDEX(ms_pd,B{out + 4})"),
    ]
    for k, (label, formula) in enumerate(rows):
        calc[f"A{out + k}"], calc[f"B{out + k}"] = label, formula
        calc[f"A{out + k}"].font = BOLD
    calc[f"B{out + 2}"].number_format = "0.00%"
    calc[f"B{out + 5}"].number_format = "0.00%"
    calc[f"A{out + 7}"] = "Python PD for the example client"
    calc[f"B{out + 7}"] = float(check.loc[0, "pd_model"])
    calc[f"B{out + 7}"].number_format = "0.00%"
    for col, width in zip("ABCDEFGH", (30, 40, 14, 6, 10, 12, 18, 10)):
        calc.column_dimensions[col].width = width

    # Check: 25 test clients
    ck = wb.create_sheet("Check")
    header = ["client_id"] + variables + ["pd_python", "grade_python", "pd_excel", "grade_excel", "abs_diff", "grade_match"]
    ck.append(header)
    for c in ck[1]:
        c.font = BOLD
    vcols = {v: chr(ord("B") + i) for i, v in enumerate(variables)}
    pd_col = chr(ord("B") + len(variables))
    g_col, x_col, xg_col, d_col, m_col = (chr(ord(pd_col) + k) for k in range(1, 6))
    for i, r in enumerate(check.itertuples(index=False), start=2):
        ck.append([r.client_id] + [getattr(r, v) for v in variables] + [r.pd_model, r.grade])
        terms = "+".join(woe_term(f"{vcols[v]}$1", f"{vcols[v]}{i}", "sc_woe*sc_coef") for v in variables)
        ck[f"{x_col}{i}"] = f"=1/(1+EXP(-(INDEX(sc_intercept,1)+{terms})))"
        ck[f"{xg_col}{i}"] = f"=SUMPRODUCT(--(ms_upper<{x_col}{i}))+1"
        ck[f"{d_col}{i}"] = f"=ABS({x_col}{i}-{pd_col}{i})"
        ck[f"{m_col}{i}"] = f"=IF({xg_col}{i}={g_col}{i},1,0)"
    n = len(check) + 1
    ck[f"A{n + 2}"], ck[f"B{n + 2}"] = "Largest absolute PD difference", f"=MAX({d_col}2:{d_col}{n})"
    ck[f"A{n + 3}"], ck[f"B{n + 3}"] = "Grades matching", f"=SUM({m_col}2:{m_col}{n})"
    ck[f"A{n + 4}"], ck[f"B{n + 4}"] = "Clients", len(check)
    name(wb, "check_max_diff", f"Check!$B${n + 2}")
    name(wb, "check_grades_matching", f"Check!$B${n + 3}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build())
