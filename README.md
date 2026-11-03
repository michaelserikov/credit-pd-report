# PD model and portfolio report on open credit data

A probability-of-default scorecard with a rating-style report, built on the open UCI "Default of Credit Card Clients" data (30,000 clients, Taiwan, 2005; Yeh and Lien, 2009). The target is default in the following month, so this is a one-month PD on card data, not a 12-month bank PD. Research study on public data.

## Method
- Stratified 70/30 split; weight-of-evidence binning fitted on training data only.
- Logistic scorecard against gradient boosting as a challenger.
- Eight rating grades from training-score quantiles, with a master scale from training default rates.
- Out-of-sample binomial test per grade and a population stability index between train and test.
- Star-schema CSV tables and a build guide for a Power BI report (`powerbi/`).

## Results (test sample, 9,000 clients)
| | Gini | AUC | KS |
|---|---|---|---|
| Logistic scorecard (WoE) | 0.505 | 0.753 | 0.391 |
| Gradient boosting | 0.547 | 0.773 | 0.415 |

- Training Gini of the scorecard is 0.535, so the out-of-sample drop is about 0.03.
- No grade is rejected by the binomial test at 5%, without a correction for multiple tests. Observed default rates rise from 6.4% in grade 1 to 65.5% in grade 8. Grades 3 and 4 have nearly the same master scale PD (12.0% and 13.1%), so the scale separates them weakly.
- Grade PSI between train and test is 0.001. Both samples come from the same period and split, so this is not evidence of stability over time.

## Limits
One-month horizon, one portfolio and one period, random rather than out-of-time split, no LGD or EAD, no macro link. Payment status variables dominate (information value 0.89 for the latest status).

## Run
```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python run_pd.py
```
