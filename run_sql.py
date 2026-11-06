"""Run the report queries in sql/report_queries.sql on the Power BI tables with DuckDB.

Each query becomes sql/output/<name>.csv. The same tables feed the Power BI report, so the SQL results are a check
on the report's measures.

    python run_sql.py
"""
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent
DATA = ROOT / "powerbi" / "data"
QUERIES = ROOT / "sql" / "report_queries.sql"
OUT = ROOT / "sql" / "output"


def queries(path: Path = QUERIES) -> dict[str, str]:
    """Split the file at its "-- name:" lines."""
    parts = re.split(r"^-- name: *(\w+) *$", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return {name: body.strip().rstrip(";") for name, body in zip(parts[1::2], parts[2::2])}


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for table in ("fact_portfolio", "dim_grade", "dim_segment"):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_csv_auto('{(DATA / f'{table}.csv').as_posix()}')")
    return con


def run() -> dict:
    con = connect()
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, sql in queries().items():
        frame = con.execute(sql).df()
        frame.to_csv(OUT / f"{name}.csv", index=False, float_format="%.6g")
        results[name] = frame
    return results


if __name__ == "__main__":
    for name, frame in run().items():
        print(f"\n== {name}")
        print(frame.to_string(index=False))
