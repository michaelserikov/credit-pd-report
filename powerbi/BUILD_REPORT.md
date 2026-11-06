# Building the Power BI report (about 2-3 hours)

Power BI Desktop (Windows, free). Four pages on the out-of-sample test portfolio (9,000 clients): overview, calibration, discrimination and benchmark. Every number on the pages can be checked against `sql/output/` (run `python run_sql.py`).

## 1. Load
Home > Get Data > Text/CSV, one by one:
- `powerbi/data/fact_portfolio.csv` (one row per client: grade, model PD, default flag, limit, balance, segment, age band)
- `powerbi/data/dim_grade.csv` (grade bounds, master scale PD, binomial test)
- `powerbi/data/dim_segment.csv` (education segment)
- `sql/output/cap_curve.csv` (20 PD bands for the discrimination page)

Click Transform Data, not Load. In Power Query check each numeric column: if `pd_model` or `master_scale_pd` shows as text (a German locale reads the dot as a thousands separator), right-click the column > Change Type > Using Locale > Decimal Number, English (United States). Close & Apply.

## 2. Model
Model view, drag to create one-to-many relationships, single cross-filter direction:
- `dim_grade[grade]` 1 to * `fact_portfolio[grade]`
- `dim_segment[segment_id]` 1 to * `fact_portfolio[segment_id]`

`cap_curve` stays unrelated. Hide the key columns on the fact side (right-click > Hide in report view) so slicers use the dimension columns.

## 3. Measures
Home > New Measure, in table `fact_portfolio`:
```
Clients = COUNTROWS(fact_portfolio)
Defaults = SUM(fact_portfolio[default])
Observed Default Rate = DIVIDE([Defaults], [Clients])
Mean Model PD = AVERAGE(fact_portfolio[pd_model])
Master Scale PD = DIVIDE(SUMX(fact_portfolio, RELATED(dim_grade[master_scale_pd])), [Clients])
Calibration Gap = [Observed Default Rate] - [Master Scale PD]
Exposure = SUM(fact_portfolio[exposure_limit])
Exposure Share = DIVIDE([Exposure], CALCULATE([Exposure], ALL(fact_portfolio)))
Expected Defaults = SUMX(fact_portfolio, fact_portfolio[pd_model])
Defaults vs Expected = DIVIDE([Defaults], [Expected Defaults])
Benchmark Default Rate = CALCULATE([Observed Default Rate], ALL(fact_portfolio[segment_id]), ALL(dim_segment))
Gap to Benchmark = [Observed Default Rate] - [Benchmark Default Rate]
```
In table `cap_curve`:
```
Random Model = MAX(cap_curve[cumulative_client_share])
```
Format the rates as percentages with one decimal (Measure tools > Format).

## 4. Pages
1. **Portfolio overview.** Cards: Clients, Exposure, Observed Default Rate, Mean Model PD. Clustered column chart: `dim_grade[grade]` on the axis, Clients and Exposure Share. Slicers: `dim_segment[segment_id]` and `fact_portfolio[age_band]`.
2. **Calibration.** Line and clustered column chart: grade on the axis, Clients as columns, Observed Default Rate and Master Scale PD as lines. Table from `dim_grade`: grade, clients, defaults, observed_rate, master_scale_pd, binomial_p. Card: Defaults vs Expected.
3. **Discrimination.** Line chart from `cap_curve`: `cumulative_client_share` on the axis (type continuous), `cumulative_default_share` and Random Model as lines. Text box: Gini 0.505 on the test sample (the `gini` SQL query gives the same number). The 20% riskiest clients by PD hold 49% of the defaults.
4. **Benchmark.** Matrix: `dim_segment[segment_id]` in rows, `fact_portfolio[age_band]` in columns, Observed Default Rate and Gap to Benchmark as values. Conditional formatting on Gap to Benchmark (Format > Cell elements > Background color, diverging, centre 0).

## 5. Save
Save as `powerbi/credit_pd_report.pbix`, then File > Export > PDF to `powerbi/credit_pd_report.pdf`, and add two screenshots to the README.

## What to be ready to explain
- **Why Benchmark Default Rate removes the segment filter and keeps the age band.** `ALL(dim_segment)` drops the segment context, so in a matrix cell the measure is the default rate of all segments in that age band; the gap shows whether a segment is worse than its peers of the same age. The `segment_age_benchmark` SQL query computes the same with a window over `age_band`.
- **Master Scale PD against Mean Model PD.** The master scale assigns one PD per grade from training default rates; the model PD varies inside the grade. In grade 1 the model averages 8.6% against 6.4% observed and a master scale PD of 6.5%, so the grade mapping corrects the model's level in the best grade.
- **Why the binomial test is not enough.** It tests each grade separately, without a correction for eight tests, and on a random split of one period; it says nothing about stability over time.
- **RELATED in Master Scale PD.** The measure iterates the fact rows and looks up each client's grade PD through the relationship, so it stays correct under any slicer.
