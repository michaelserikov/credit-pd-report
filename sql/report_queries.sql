-- Portfolio report queries on the Power BI tables (DuckDB SQL; views fact_portfolio, dim_grade, dim_segment).
-- Each query starts with a "-- name:" line; run_sql.py runs them all and writes sql/output/<name>.csv.

-- name: grade_summary
-- Clients, defaults and exposure per grade, with each grade's share of exposure and the cumulative share from the
-- best grade down (window functions).
SELECT
    f.grade,
    COUNT(*) AS clients,
    SUM(f."default") AS defaults,
    AVG(f."default") AS observed_rate,
    AVG(f.pd_model) AS mean_model_pd,
    ANY_VALUE(g.master_scale_pd) AS master_scale_pd,
    SUM(f.exposure_limit) AS exposure,
    SUM(f.exposure_limit) / SUM(SUM(f.exposure_limit)) OVER () AS exposure_share,
    SUM(SUM(f.exposure_limit)) OVER (ORDER BY f.grade) / SUM(SUM(f.exposure_limit)) OVER () AS cumulative_exposure_share
FROM fact_portfolio AS f
JOIN dim_grade AS g USING (grade)
GROUP BY f.grade
ORDER BY f.grade;

-- name: calibration_check
-- Observed against master scale default rate per grade: normal approximation z score next to the exact binomial
-- p-value computed in Python.
SELECT
    grade,
    clients,
    defaults,
    observed_rate,
    master_scale_pd,
    (defaults - clients * master_scale_pd) / SQRT(clients * master_scale_pd * (1 - master_scale_pd)) AS z_score,
    binomial_p
FROM dim_grade
ORDER BY grade;

-- name: segment_age_benchmark
-- Default rate by segment and age band against the rate of all segments in the same age band, the same logic as the
-- Benchmark Default Rate measure in Power BI, which removes the segment filter and keeps the age band.
WITH cells AS (
    SELECT segment_id, age_band, COUNT(*) AS clients, SUM("default") AS defaults
    FROM fact_portfolio
    GROUP BY segment_id, age_band
)
SELECT
    segment_id,
    age_band,
    clients,
    defaults / clients AS observed_rate,
    SUM(defaults) OVER (PARTITION BY age_band) / SUM(clients) OVER (PARTITION BY age_band) AS benchmark_rate,
    defaults / clients
        - SUM(defaults) OVER (PARTITION BY age_band) / SUM(clients) OVER (PARTITION BY age_band) AS gap_to_benchmark
FROM cells
ORDER BY segment_id, age_band;

-- name: cap_curve
-- Cumulative accuracy profile in 20 bands of model PD, riskiest first: share of clients against share of defaults.
WITH banded AS (
    SELECT "default", NTILE(20) OVER (ORDER BY pd_model DESC, client_id) AS band
    FROM fact_portfolio
),
bands AS (
    SELECT band, COUNT(*) AS clients, SUM("default") AS defaults FROM banded GROUP BY band
)
SELECT
    band,
    clients,
    defaults,
    SUM(clients) OVER (ORDER BY band) / SUM(clients) OVER () AS cumulative_client_share,
    SUM(defaults) OVER (ORDER BY band) / SUM(defaults) OVER () AS cumulative_default_share
FROM bands
ORDER BY band;

-- name: gini
-- Gini = 2 AUC - 1, with AUC as the Mann-Whitney statistic over distinct PD values (ties count one half).
WITH levels AS (
    SELECT pd_model, SUM("default") AS bad, SUM(1 - "default") AS good
    FROM fact_portfolio
    GROUP BY pd_model
),
ordered AS (
    SELECT good, bad, COALESCE(SUM(bad) OVER (ORDER BY pd_model ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS bad_below
    FROM levels
)
SELECT
    2 * SUM(good * ((SELECT SUM(bad) FROM levels) - bad_below - bad + bad / 2.0))
        / ((SELECT SUM(bad) FROM levels) * (SELECT SUM(good) FROM levels)) - 1 AS gini
FROM ordered;

-- name: largest_exposures
-- Ten largest credit limits with grade and PD, and their share of total exposure.
SELECT
    client_id,
    grade,
    pd_model,
    exposure_limit,
    exposure_limit / (SELECT SUM(exposure_limit) FROM fact_portfolio) AS exposure_share
FROM fact_portfolio
ORDER BY exposure_limit DESC, client_id
LIMIT 10;
