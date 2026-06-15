"""
load_data.py — Load scraped JSON files into the PostgreSQL database.

Usage:
    python load_data.py --data-dir ../data --db-url postgresql://user:pass@localhost:5432/race_analytics

For MariaDB / MySQL:
    pip install PyMySQL
    --db-url mysql+pymysql://user:pass@localhost:3306/race_analytics
"""

import argparse
import glob
import json
import logging
import os
import re
import sys
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
    DB_DRIVER = "psycopg2"
except ImportError:
    psycopg2 = None

try:
    import pymysql
    DB_DRIVER = "pymysql"
except ImportError:
    pymysql = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Database helpers
# -------------------------------------------------------------------

def get_connection(db_url: str):
    """Return a DB connection from a connection URL."""
    if "postgresql" in db_url or "postgres" in db_url:
        if psycopg2 is None:
            sys.exit("psycopg2 not installed. Run: pip install psycopg2-binary")
        import urllib.parse as up
        p = up.urlparse(db_url)
        return psycopg2.connect(
            host=p.hostname,
            port=p.port or 5432,
            dbname=p.path.lstrip("/"),
            user=p.username,
            password=p.password,
        )
    elif "mysql" in db_url or "mariadb" in db_url:
        if pymysql is None:
            sys.exit("PyMySQL not installed. Run: pip install PyMySQL")
        import urllib.parse as up
        p = up.urlparse(db_url)
        return pymysql.connect(
            host=p.hostname,
            port=p.port or 3306,
            database=p.path.lstrip("/"),
            user=p.username,
            password=p.password,
            charset="utf8mb4",
        )
    else:
        sys.exit(f"Unsupported DB URL scheme: {db_url}")


def apply_schema(conn, schema_path: str):
    """Apply the SQL schema file (idempotent — uses IF NOT EXISTS)."""
    with open(schema_path, "r") as f:
        sql = f.read()
    with conn.cursor() as cur:
        # Execute statement by statement (split on semicolons)
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
    conn.commit()
    log.info("Schema applied.")


# -------------------------------------------------------------------
# Upsert helpers
# -------------------------------------------------------------------

def upsert_edition(conn, year: int, name: str, date: str, location: str,
                   distance: float) -> int:
    """Insert or retrieve an edition row. Returns edition_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO editions (edition_name, race_year, race_date, location, distance_km)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (race_year) DO UPDATE
                SET edition_name = EXCLUDED.edition_name
            RETURNING edition_id
            """,
            (name, year, date, location, distance),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        # If no RETURNING (MariaDB), select it
        cur.execute("SELECT edition_id FROM editions WHERE race_year = %s", (year,))
        return cur.fetchone()[0]


def upsert_runner(conn, full_name: str, first_name: str, last_name: str) -> int:
    """Insert or retrieve a runner row. Returns runner_id."""
    normalised = full_name.upper().strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runners (full_name, first_name, last_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (full_name) DO NOTHING
            RETURNING runner_id
            """,
            (normalised, first_name, last_name),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT runner_id FROM runners WHERE full_name = %s", (normalised,))
        return cur.fetchone()[0]


def upsert_result(conn, edition_id: int, runner_id: int, item: dict):
    """Insert or update a result row."""
    secs = item.get("finish_time_seconds")
    dist = item.get("race_distance_km") or 10.0
    pace = round(secs / dist) if secs and dist else None

    gender_pos_raw = item.get("gender_position", "")
    gp_match = re.match(r"[MF]-(\d+)", str(gender_pos_raw), re.IGNORECASE)
    gender_pos_int = int(gp_match.group(1)) if gp_match else None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO results (
                edition_id, runner_id,
                finish_time, finish_time_secs, pace_per_km_secs,
                overall_position, gender_position, category_position,
                gender, age_group, bib_number,
                source_url, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (edition_id, runner_id) DO UPDATE SET
                finish_time      = EXCLUDED.finish_time,
                finish_time_secs = EXCLUDED.finish_time_secs,
                overall_position = EXCLUDED.overall_position
            """,
            (
                edition_id, runner_id,
                item.get("finish_time"),
                secs,
                pace,
                item.get("overall_position"),
                gender_pos_int,
                item.get("category_position"),
                item.get("gender", "U"),
                item.get("age_group"),
                item.get("bib_number"),
                item.get("source_url"),
                item.get("scraped_at"),
            ),
        )


# -------------------------------------------------------------------
# Main loader
# -------------------------------------------------------------------

def load_json_files(conn, data_dir: str):
    pattern = os.path.join(data_dir, "results_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        log.warning(f"No JSON files found matching: {pattern}")
        return

    total_inserted = 0
    for path in files:
        log.info(f"Loading {path} …")
        with open(path, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError as e:
                log.error(f"JSON parse error in {path}: {e}")
                continue

        count = 0
        for item in records:
            year = item.get("race_year")
            if not year:
                continue

            edition_id = upsert_edition(
                conn,
                year=int(year),
                name=item.get("race_edition", f"San Silvestre A Coruña {year}"),
                date=item.get("race_date"),
                location=item.get("location", "A Coruña"),
                distance=item.get("race_distance_km", 10.0),
            )

            runner_id = upsert_runner(
                conn,
                full_name=item.get("runner_name", ""),
                first_name=item.get("first_name", ""),
                last_name=item.get("last_name", ""),
            )

            upsert_result(conn, edition_id, runner_id, item)
            count += 1

        conn.commit()
        log.info(f"  → {count} records committed from {os.path.basename(path)}")
        total_inserted += count

    log.info(f"Load complete. Total records: {total_inserted}")


def main():
    parser = argparse.ArgumentParser(description="Load race JSON data into DB")
    parser.add_argument(
        "--data-dir",
        default="../data",
        help="Directory containing results_YYYY.json files",
    )
    parser.add_argument(
        "--db-url",
        required=True,
        help="Database connection URL",
    )
    parser.add_argument(
        "--schema",
        default="schema.sql",
        help="Path to schema.sql file",
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Apply schema.sql before loading data",
    )
    args = parser.parse_args()

    conn = get_connection(args.db_url)
    log.info("Connected to database.")

    if args.apply_schema:
        apply_schema(conn, args.schema)

    load_json_files(conn, args.data_dir)
    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
