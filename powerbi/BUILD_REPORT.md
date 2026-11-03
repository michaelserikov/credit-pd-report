# Building the Power BI report (about 1-2 hours)

## 1. Load
Get Data > Text/CSV: `data/fact_portfolio.csv`, `data/dim_grade.csv`, `data/dim_segment.csv`. Check the decimal separator in Power Query: if PDs load as text, set the locale to English (United States) when changing the type.

## 2. Model
Model view, one-to-many, single direction:
- `dim_grade[grade]` to `fact_portfolio[grade]`
- `dim_segment[segment_id]` to `fact_portfolio[segment_id]`

## 3. Measures (table `fact_portfolio`)
```
Clients = COUNTROWS(fact_portfolio)
Defaults = SUM(fact_portfolio[default])
Observed Default Rate = DIVIDE([Defaults], [Clients])
Mean Model PD = AVERAGE(fact_portfolio[pd_model])
Master Scale PD = SUMX(fact_portfolio, RELATED(dim_grade[master_scale_pd])) / [Clients]
Calibration Gap = [Observed Default Rate] - [Master Scale PD]
Exposure = SUM(fact_portfolio[exposure_limit])
Expected Defaults = SUMX(fact_portfolio, fact_portfolio[pd_model])
Benchmark Default Rate = CALCULATE([Observed Default Rate], ALL(fact_portfolio[segment_id]), ALL(dim_segment))
Gap to Benchmark = [Observed Default Rate] - [Benchmark Default Rate]
```

## 4. Pages
1. **Portfolio overview:** cards for Clients, Exposure, Observed Default Rate, Mean Model PD; column chart of Clients by grade; slicers for segment and age band.
2. **Calibration:** line and clustered column chart by grade with Observed Default Rate and Master Scale PD; table from `dim_grade` with defaults, clients and binomial p-value.
3. **Benchmark:** matrix by segment and age band with Observed Default Rate, Benchmark Default Rate and Gap to Benchmark; conditional formatting on the gap.

## 5. Save
Save as `credit_pd_report.pbix`, and export a PDF or screenshots to `powerbi/` for the README. Be ready to explain each measure, the relationships and why `Benchmark Default Rate` removes the segment filter.
