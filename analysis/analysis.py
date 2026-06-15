"""
analysis.py — San Silvestre Coruña race analytics.

Run from the /analysis directory:
    python analysis.py --data-dir ../data --output-dir ./output

Generates:
  - Participation trends (CSV + charts)
  - Gender participation over time
  - Mean/median/min/max finish times per year
  - Average times by age group and gender
  - Top performers across multiple editions
  - Summary HTML report
"""

import argparse
import glob
import json
import os
import sys
import warnings

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

warnings.filterwarnings("ignore")

LOCATION = "A Coruña"
PALETTE = {"M": "#2196F3", "F": "#E91E63", "U": "#9E9E9E"}


# -------------------------------------------------------------------
# Data loading
# -------------------------------------------------------------------

def load_all_json(data_dir: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(data_dir, "results_*.json")))
    if not files:
        sys.exit(f"No results_*.json files found in: {data_dir}")

    frames = []
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
                frames.append(pd.DataFrame(records))
            except Exception as e:
                print(f"[WARN] Could not load {path}: {e}")

    df = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(df):,} records from {len(files)} files.")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    # Numeric conversions
    df["race_year"] = pd.to_numeric(df["race_year"], errors="coerce").astype("Int64")
    df["finish_time_seconds"] = pd.to_numeric(
        df.get("finish_time_seconds"), errors="coerce"
    )
    df["overall_position"] = pd.to_numeric(
        df.get("overall_position"), errors="coerce"
    ).astype("Int64")
    df["race_distance_km"] = pd.to_numeric(
        df.get("race_distance_km"), errors="coerce"
    ).fillna(10.0)

    # Drop rows without year or finish time
    df = df.dropna(subset=["race_year", "finish_time_seconds"])
    df["race_year"] = df["race_year"].astype(int)

    # Pace in seconds per km
    df["pace_secs_per_km"] = (
        df["finish_time_seconds"] / df["race_distance_km"]
    ).round()

    # Normalise gender
    df["gender"] = df["gender"].str.upper().fillna("U")
    df.loc[~df["gender"].isin(["M", "F"]), "gender"] = "U"

    return df.sort_values(["race_year", "overall_position"])


# -------------------------------------------------------------------
# Formatting helpers
# -------------------------------------------------------------------

def secs_to_mmss(secs) -> str:
    if pd.isna(secs):
        return "-"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _save(fig, output_dir: str, name: str):
    path = os.path.join(output_dir, name)
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


# -------------------------------------------------------------------
# Analysis functions
# -------------------------------------------------------------------

def participation_trends(df: pd.DataFrame, output_dir: str) -> pd.DataFrame:
    """Total participation and gender split per year."""
    by_year_gender = (
        df.groupby(["race_year", "gender"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ["M", "F", "U"]:
        if col not in by_year_gender.columns:
            by_year_gender[col] = 0

    by_year_gender["Total"] = by_year_gender[["M", "F", "U"]].sum(axis=1)
    by_year_gender["pct_female"] = (
        by_year_gender["F"] / by_year_gender["Total"] * 100
    ).round(1)

    # --- Chart: total participation ---
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(by_year_gender["race_year"], by_year_gender["Total"],
           color="#546E7A", alpha=0.85)
    ax.set_xlabel("Year")
    ax.set_ylabel("Finishers")
    ax.set_title("San Silvestre Coruña — Participation per Edition")
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    plt.xticks(rotation=45)
    _save(fig, output_dir, "01_participation_total.png")

    # --- Chart: male/female stacked bars ---
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(by_year_gender["race_year"], by_year_gender["M"],
           label="Male", color=PALETTE["M"], alpha=0.85)
    ax.bar(by_year_gender["race_year"], by_year_gender["F"],
           bottom=by_year_gender["M"],
           label="Female", color=PALETTE["F"], alpha=0.85)
    ax.set_xlabel("Year")
    ax.set_ylabel("Finishers")
    ax.set_title("Participation by Gender per Edition")
    ax.legend()
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    plt.xticks(rotation=45)
    _save(fig, output_dir, "02_participation_gender.png")

    # --- Chart: % female ---
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(by_year_gender["race_year"], by_year_gender["pct_female"],
            marker="o", color=PALETTE["F"])
    ax.set_xlabel("Year")
    ax.set_ylabel("% Female finishers")
    ax.set_title("Female Participation Rate Over Time")
    ax.yaxis.set_major_formatter(ticker.PercentFormatter())
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    plt.xticks(rotation=45)
    _save(fig, output_dir, "03_female_pct.png")

    by_year_gender.to_csv(
        os.path.join(output_dir, "participation_by_year.csv"), index=False
    )
    return by_year_gender


def time_trends(df: pd.DataFrame, output_dir: str) -> pd.DataFrame:
    """Mean, median, min, max finish times per year."""
    stats = (
        df.groupby("race_year")["finish_time_seconds"]
        .agg(
            mean="mean",
            median="median",
            minimum="min",
            maximum="max",
            count="count",
        )
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(stats["race_year"], stats["mean"] / 60,
            marker="o", label="Mean", color="#1565C0")
    ax.plot(stats["race_year"], stats["median"] / 60,
            marker="s", linestyle="--", label="Median", color="#388E3C")
    ax.fill_between(
        stats["race_year"],
        stats["minimum"] / 60,
        stats["maximum"] / 60,
        alpha=0.12, color="steelblue", label="Min–Max range",
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Finish time (minutes)")
    ax.set_title("Finish Time Evolution — San Silvestre Coruña")
    ax.legend()
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    plt.xticks(rotation=45)
    _save(fig, output_dir, "04_time_trends.png")

    # Gender split time trends
    g_stats = (
        df[df["gender"].isin(["M", "F"])]
        .groupby(["race_year", "gender"])["finish_time_seconds"]
        .agg(mean="mean", median="median")
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(11, 5))
    for gender, color in [("M", PALETTE["M"]), ("F", PALETTE["F"])]:
        sub = g_stats[g_stats["gender"] == gender]
        label = "Male" if gender == "M" else "Female"
        ax.plot(sub["race_year"], sub["mean"] / 60,
                marker="o", color=color, label=f"{label} mean")
        ax.plot(sub["race_year"], sub["median"] / 60,
                linestyle="--", color=color, alpha=0.5,
                label=f"{label} median")
    ax.set_xlabel("Year")
    ax.set_ylabel("Finish time (minutes)")
    ax.set_title("Mean & Median Finish Times by Gender")
    ax.legend()
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    plt.xticks(rotation=45)
    _save(fig, output_dir, "05_time_by_gender.png")

    stats.to_csv(os.path.join(output_dir, "time_stats_by_year.csv"), index=False)
    return stats


def age_group_analysis(df: pd.DataFrame, output_dir: str) -> pd.DataFrame:
    """Average finish times by age group and gender."""
    ag_stats = (
        df[df["gender"].isin(["M", "F"])]
        .groupby(["age_group", "gender"])["finish_time_seconds"]
        .agg(mean="mean", count="count")
        .reset_index()
        .dropna(subset=["age_group"])
    )
    ag_stats = ag_stats[ag_stats["count"] >= 10]  # Filter thin slices

    fig, ax = plt.subplots(figsize=(13, 6))
    ag_m = ag_stats[ag_stats["gender"] == "M"].sort_values("mean")
    ag_f = ag_stats[ag_stats["gender"] == "F"].sort_values("mean")
    categories = ag_m["age_group"].tolist()
    x = np.arange(len(categories))
    width = 0.4

    ax.bar(x - width / 2, ag_m["mean"] / 60, width,
           label="Male", color=PALETTE["M"], alpha=0.85)
    ax.bar(x + width / 2,
           ag_f.set_index("age_group").reindex(categories)["mean"] / 60,
           width, label="Female", color=PALETTE["F"], alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Average finish time (minutes)")
    ax.set_title("Average Finish Time by Age Group and Gender")
    ax.legend()
    _save(fig, output_dir, "06_avg_time_age_group.png")

    ag_stats.to_csv(
        os.path.join(output_dir, "age_group_stats.csv"), index=False
    )
    return ag_stats


def top_performers(df: pd.DataFrame, output_dir: str,
                   min_editions: int = 2, top_n: int = 20) -> pd.DataFrame:
    """Runners with best average time across ≥ min_editions races."""
    perf = (
        df.groupby("runner_name")
        .agg(
            editions=("race_year", "nunique"),
            avg_time_secs=("finish_time_seconds", "mean"),
            best_time_secs=("finish_time_seconds", "min"),
            worst_time_secs=("finish_time_seconds", "max"),
            gender=("gender", "first"),
        )
        .reset_index()
    )
    perf = (
        perf[perf["editions"] >= min_editions]
        .sort_values("avg_time_secs")
        .head(top_n)
    )
    perf["avg_time"] = perf["avg_time_secs"].apply(secs_to_mmss)
    perf["best_time"] = perf["best_time_secs"].apply(secs_to_mmss)

    # Chart
    fig, ax = plt.subplots(figsize=(12, 7))
    colors = perf["gender"].map(PALETTE).fillna(PALETTE["U"])
    bars = ax.barh(perf["runner_name"], perf["avg_time_secs"] / 60,
                   color=colors, alpha=0.85)
    ax.invert_yaxis()
    ax.set_xlabel("Average finish time (minutes)")
    ax.set_title(f"Top {top_n} Performers by Average Time (≥{min_editions} editions)")
    for bar, editions in zip(bars, perf["editions"]):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{int(editions)} ed.", va="center", fontsize=7)
    _save(fig, output_dir, "07_top_performers.png")

    perf.to_csv(os.path.join(output_dir, "top_performers.csv"), index=False)
    return perf


# -------------------------------------------------------------------
# HTML report
# -------------------------------------------------------------------

def build_html_report(output_dir: str, stats: dict):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>San Silvestre Coruña — Analytics Report</title>
  <style>
    body {{ font-family: sans-serif; max-width: 960px; margin: 2rem auto; color: #333; }}
    h1 {{ color: #1565C0; }}
    h2 {{ border-bottom: 2px solid #eee; padding-bottom: .3rem; margin-top: 2rem; }}
    img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; margin: .5rem 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }}
    th {{ background: #1565C0; color: #fff; padding: .5rem .8rem; text-align: left; }}
    td {{ padding: .4rem .8rem; border-bottom: 1px solid #eee; }}
    tr:nth-child(even) td {{ background: #f9f9f9; }}
  </style>
</head>
<body>
  <h1>🏃 San Silvestre Coruña — Race Analytics Report</h1>
  <p>Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p>
  <p>Total records analysed: <strong>{stats['total_records']:,}</strong> |
     Editions: <strong>{stats['editions']}</strong> |
     Years: <strong>{stats['years']}</strong></p>

  <h2>1. Participation Trends</h2>
  <img src="01_participation_total.png" alt="Participation per year"/>
  <img src="02_participation_gender.png" alt="Gender split"/>
  <img src="03_female_pct.png" alt="Female participation rate"/>

  <h2>2. Finish Time Evolution</h2>
  <img src="04_time_trends.png" alt="Time trends"/>
  <img src="05_time_by_gender.png" alt="Time by gender"/>

  <h2>3. Age Group Performance</h2>
  <img src="06_avg_time_age_group.png" alt="Age group average times"/>

  <h2>4. Top Performers</h2>
  <img src="07_top_performers.png" alt="Top performers"/>

</body>
</html>"""
    path = os.path.join(output_dir, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report written: {path}")


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Race data analytics")
    parser.add_argument("--data-dir", default="../data")
    parser.add_argument("--output-dir", default="./output")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    df_raw = load_all_json(args.data_dir)
    df = clean(df_raw)

    print("\n=== Participation Trends ===")
    participation_trends(df, args.output_dir)

    print("\n=== Time Trends ===")
    time_trends(df, args.output_dir)

    print("\n=== Age Group Analysis ===")
    age_group_analysis(df, args.output_dir)

    print("\n=== Top Performers ===")
    top_performers(df, args.output_dir)

    stats = {
        "total_records": len(df),
        "editions": df["race_year"].nunique(),
        "years": sorted(df["race_year"].unique().tolist()),
    }
    build_html_report(args.output_dir, stats)
    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
