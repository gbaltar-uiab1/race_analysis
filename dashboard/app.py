"""
dashboard/app.py — San Silvestre Coruña Race Analytics Dashboard

Run:
    cd dashboard
    streamlit run app.py

Expects JSON data files in ../data/results_*.json
"""

import glob
import json
import os
import re
import sys

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# -------------------------------------------------------------------
# Page config
# -------------------------------------------------------------------
st.set_page_config(
    page_title="San Silvestre Coruña — Race Analytics",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PALETTE = {"M": "#2196F3", "F": "#E91E63", "U": "#9E9E9E"}


# -------------------------------------------------------------------
# Data loading (cached)
# -------------------------------------------------------------------

@st.cache_data(show_spinner="Loading race data…")
def load_data(data_dir: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(data_dir, "results_*.json")))
    if not files:
        return pd.DataFrame()

    frames = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                records = json.load(f)
            frames.append(pd.DataFrame(records))
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Numeric conversions
    df["race_year"] = pd.to_numeric(df.get("race_year"), errors="coerce").astype("Int64")
    df["finish_time_seconds"] = pd.to_numeric(df.get("finish_time_seconds"), errors="coerce")
    df["overall_position"] = pd.to_numeric(df.get("overall_position"), errors="coerce").astype("Int64")
    df["race_distance_km"] = pd.to_numeric(df.get("race_distance_km"), errors="coerce").fillna(10.0)

    df = df.dropna(subset=["race_year", "finish_time_seconds"])
    df["race_year"] = df["race_year"].astype(int)
    df["gender"] = df.get("gender", "U").fillna("U").str.upper()
    df.loc[~df["gender"].isin(["M", "F"]), "gender"] = "U"

    df["pace_secs_per_km"] = (df["finish_time_seconds"] / df["race_distance_km"]).round()
    df["runner_name"] = df.get("runner_name", "").fillna("").str.strip().str.title()
    df["age_group"] = df.get("age_group", "").fillna("Unknown").str.strip()

    return df.sort_values(["race_year", "overall_position"])


def secs_to_hms(secs) -> str:
    if pd.isna(secs):
        return "-"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def secs_to_pace(secs) -> str:
    if pd.isna(secs):
        return "-"
    secs = int(secs)
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d} /km"


# -------------------------------------------------------------------
# App
# -------------------------------------------------------------------

df = load_data(DATA_DIR)

if df.empty:
    st.error(
        "⚠️ No data found. Please run the Scrapy spider first:\n\n"
        "```\ncd scrapy_project\nscrapy crawl san_silvestre\n```"
    )
    st.stop()

years = sorted(df["race_year"].unique().tolist())
genders = {"All": None, "Male": "M", "Female": "F"}

# -------------------------------------------------------------------
# Sidebar navigation
# -------------------------------------------------------------------
st.sidebar.image(
    "https://sansilvestrecoruna.com/media/sansilvestrecoruna.com/site-logos/"
    "LOGO_SAN_SILVESTRE_1_tinta_AMARILLO_O4l7Tok.png",
    width=200,
)
st.sidebar.markdown("## Navigation")
view = st.sidebar.radio(
    "Select view",
    ["🏁 Race Analysis", "👤 Runner Analysis", "📈 Historical Trends"],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Dataset:** {len(df):,} results | {len(years)} editions\n\n"
    f"**Years:** {min(years)} – {max(years)}"
)

# ===================================================================
# VIEW 1 — RACE ANALYSIS
# ===================================================================
if view == "🏁 Race Analysis":
    st.title("🏁 Race Analysis")
    st.caption("Explore results for a specific edition of San Silvestre Coruña")

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_year = st.selectbox("Select edition (year)", years[::-1])
    with col2:
        gender_label = st.selectbox("Gender filter", list(genders.keys()))
    with col3:
        age_groups = ["All"] + sorted(
            df[df["race_year"] == selected_year]["age_group"].unique().tolist()
        )
        selected_ag = st.selectbox("Age group filter", age_groups)

    # Filter data
    race_df = df[df["race_year"] == selected_year].copy()
    if genders[gender_label]:
        race_df = race_df[race_df["gender"] == genders[gender_label]]
    if selected_ag != "All":
        race_df = race_df[race_df["age_group"] == selected_ag]

    if race_df.empty:
        st.warning("No data for the selected filters.")
        st.stop()

    # --- KPI cards ---
    t = race_df["finish_time_seconds"]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Finishers", f"{len(race_df):,}")
    k2.metric("Winner", secs_to_hms(t.min()))
    k3.metric("Last finisher", secs_to_hms(t.max()))
    k4.metric("Average", secs_to_hms(t.mean()))
    k5.metric("Median", secs_to_hms(t.median()))

    st.divider()

    col_hist, col_stats = st.columns([2, 1])

    with col_hist:
        st.subheader("Finish Time Distribution")
        fig = px.histogram(
            race_df,
            x="finish_time_seconds",
            nbins=60,
            color="gender",
            color_discrete_map=PALETTE,
            labels={"finish_time_seconds": "Finish time (seconds)", "gender": "Gender"},
            barmode="overlay",
            opacity=0.7,
        )
        # Add mean line
        fig.add_vline(
            x=t.mean(), line_dash="dash", line_color="#FF6F00",
            annotation_text=f"Mean {secs_to_hms(t.mean())}",
            annotation_position="top right",
        )
        fig.add_vline(
            x=t.median(), line_dash="dot", line_color="#2E7D32",
            annotation_text=f"Median {secs_to_hms(t.median())}",
            annotation_position="top left",
        )
        fig.update_layout(height=400, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_stats:
        st.subheader("Statistics")
        percentiles = [10, 25, 50, 75, 90]
        pct_df = pd.DataFrame({
            "Percentile": [f"P{p}" for p in percentiles],
            "Time": [secs_to_hms(np.percentile(t.dropna(), p)) for p in percentiles],
        })
        st.dataframe(pct_df, use_container_width=True, hide_index=True)

        if genders[gender_label] is None:
            st.markdown("**Gender split**")
            g_split = race_df["gender"].value_counts().rename(
                index={"M": "Male", "F": "Female", "U": "Unknown"}
            )
            st.dataframe(g_split.rename("Count"), use_container_width=True)

    # Age group breakdown
    st.subheader("Average Time by Age Group")
    ag_avg = (
        race_df.groupby("age_group")["finish_time_seconds"]
        .mean()
        .sort_values()
        .reset_index()
    )
    fig2 = px.bar(
        ag_avg,
        x="age_group",
        y="finish_time_seconds",
        labels={"age_group": "Age group", "finish_time_seconds": "Avg time (secs)"},
    )
    fig2.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=80))
    st.plotly_chart(fig2, use_container_width=True)

    # Full results table
    with st.expander("📋 Full results table", expanded=False):
        display_cols = [c for c in [
            "overall_position", "runner_name", "gender",
            "age_group", "finish_time", "bib_number"
        ] if c in race_df.columns]
        st.dataframe(
            race_df[display_cols].reset_index(drop=True),
            use_container_width=True,
            height=400,
        )


# ===================================================================
# VIEW 2 — RUNNER ANALYSIS
# ===================================================================
elif view == "👤 Runner Analysis":
    st.title("👤 Runner Analysis")
    st.caption("Search for a runner and explore their performance history")

    # Runner search
    all_runners = sorted(df["runner_name"].dropna().unique().tolist())
    search_term = st.text_input(
        "Search runner name", placeholder="Type a name (min. 3 characters)…"
    )

    if len(search_term) < 3:
        st.info("Enter at least 3 characters to search for a runner.")
        st.stop()

    matches = [r for r in all_runners if search_term.upper() in r.upper()]
    if not matches:
        st.warning(f"No runner found matching '{search_term}'.")
        st.stop()

    selected_runner = st.selectbox(
        f"Found {len(matches)} runner(s) — select one:", matches
    )

    runner_df = df[df["runner_name"] == selected_runner].sort_values("race_year")

    # KPI summary
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Editions completed", len(runner_df))
    k2.metric("Best time", secs_to_hms(runner_df["finish_time_seconds"].min()))
    k3.metric("Avg time", secs_to_hms(runner_df["finish_time_seconds"].mean()))
    k4.metric("Best overall position", int(runner_df["overall_position"].dropna().min()) if not runner_df["overall_position"].dropna().empty else "-")

    st.divider()

    # Race history table
    st.subheader("Race History")
    history_cols = [c for c in [
        "race_year", "finish_time", "pace_secs_per_km",
        "overall_position", "gender_position", "age_group"
    ] if c in runner_df.columns]
    hist_display = runner_df[history_cols].copy()
    if "pace_secs_per_km" in hist_display.columns:
        hist_display["pace"] = hist_display["pace_secs_per_km"].apply(secs_to_pace)
        hist_display = hist_display.drop(columns=["pace_secs_per_km"])
    st.dataframe(hist_display, use_container_width=True, hide_index=True)

    # Progress chart
    if len(runner_df) > 1:
        st.subheader("Finish Time Progression")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=runner_df["race_year"],
            y=runner_df["finish_time_seconds"] / 60,
            mode="lines+markers+text",
            text=runner_df["finish_time"],
            textposition="top center",
            marker=dict(size=10, color="#1565C0"),
            line=dict(color="#1565C0", width=2),
            name=selected_runner,
        ))
        fig.update_layout(
            xaxis_title="Year",
            yaxis_title="Finish time (minutes)",
            height=350,
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Position within distribution for a selected race
    st.subheader("Position Within Race Distribution")
    runner_years = runner_df["race_year"].tolist()
    sel_year = st.selectbox("Select race year to compare", runner_years[::-1])

    year_df = df[df["race_year"] == sel_year]
    runner_time = runner_df[runner_df["race_year"] == sel_year]["finish_time_seconds"].values
    if len(runner_time) == 0:
        st.warning("No result found for that year.")
    else:
        runner_time = runner_time[0]
        fig3 = px.histogram(
            year_df,
            x="finish_time_seconds",
            nbins=60,
            labels={"finish_time_seconds": "Finish time (seconds)"},
            color_discrete_sequence=["#B0BEC5"],
            opacity=0.7,
            title=f"{sel_year} finish time distribution with {selected_runner} highlighted",
        )
        fig3.add_vline(
            x=runner_time, line_color="#D32F2F", line_width=2.5,
            annotation_text=f"► {selected_runner}  ({secs_to_hms(runner_time)})",
            annotation_position="top right",
            annotation_font_color="#D32F2F",
        )
        pct_rank = (year_df["finish_time_seconds"] < runner_time).mean() * 100
        fig3.add_annotation(
            x=runner_time, y=0,
            text=f"Top {100 - pct_rank:.0f}%",
            showarrow=True, arrowhead=2, bgcolor="#FFCDD2",
            yanchor="bottom",
        )
        fig3.update_layout(height=380, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig3, use_container_width=True)
        st.caption(
            f"**{selected_runner}** finished in **{secs_to_hms(runner_time)}**, "
            f"faster than {pct_rank:.1f}% of finishers in {sel_year}."
        )


# ===================================================================
# VIEW 3 — HISTORICAL TRENDS
# ===================================================================
else:
    st.title("📈 Historical Trends")
    st.caption("Participation, timing, and performance trends across all editions")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Participation", "Finish Times", "Age Groups", "Top Performers"
    ])

    # --- Tab 1: Participation ---
    with tab1:
        yearly = (
            df.groupby(["race_year", "gender"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        for g in ["M", "F", "U"]:
            if g not in yearly.columns:
                yearly[g] = 0
        yearly["Total"] = yearly[["M", "F", "U"]].sum(axis=1)

        fig = go.Figure()
        fig.add_bar(x=yearly["race_year"], y=yearly["M"],
                    name="Male", marker_color=PALETTE["M"])
        fig.add_bar(x=yearly["race_year"], y=yearly["F"],
                    name="Female", marker_color=PALETTE["F"])
        fig.update_layout(barmode="stack", title="Finishers by Year and Gender",
                          xaxis_title="Year", yaxis_title="Finishers", height=420)
        st.plotly_chart(fig, use_container_width=True)

        yearly["pct_female"] = (yearly["F"] / yearly["Total"] * 100).round(1)
        fig2 = px.line(
            yearly, x="race_year", y="pct_female",
            markers=True, title="Female Participation Rate (%)",
            labels={"pct_female": "% Female", "race_year": "Year"},
        )
        fig2.update_traces(line_color=PALETTE["F"])
        fig2.update_layout(height=320)
        st.plotly_chart(fig2, use_container_width=True)

    # --- Tab 2: Finish Times ---
    with tab2:
        time_stats = (
            df.groupby("race_year")["finish_time_seconds"]
            .agg(Mean="mean", Median="median", Min="min", Max="max")
            .reset_index()
        )

        fig = go.Figure()
        fig.add_scatter(x=time_stats["race_year"], y=time_stats["Mean"] / 60,
                        mode="lines+markers", name="Mean", line=dict(color="#1565C0"))
        fig.add_scatter(x=time_stats["race_year"], y=time_stats["Median"] / 60,
                        mode="lines+markers", name="Median",
                        line=dict(color="#388E3C", dash="dash"))
        fig.add_scatter(x=time_stats["race_year"], y=time_stats["Min"] / 60,
                        mode="lines+markers", name="Winner",
                        line=dict(color="#F57F17", dash="dot"))
        fig.update_layout(
            title="Finish Time Trends (minutes)",
            xaxis_title="Year", yaxis_title="Time (minutes)", height=420,
        )
        st.plotly_chart(fig, use_container_width=True)

        g_time = (
            df[df["gender"].isin(["M", "F"])]
            .groupby(["race_year", "gender"])["finish_time_seconds"]
            .mean()
            .reset_index()
        )
        fig2 = px.line(
            g_time, x="race_year", y="finish_time_seconds",
            color="gender", color_discrete_map=PALETTE,
            markers=True,
            labels={"finish_time_seconds": "Avg time (secs)", "race_year": "Year",
                    "gender": "Gender"},
            title="Average Finish Time by Gender",
        )
        fig2.update_layout(height=350)
        st.plotly_chart(fig2, use_container_width=True)

    # --- Tab 3: Age Groups ---
    with tab3:
        ag_year = st.selectbox("Select year for age group breakdown", years[::-1])
        ag_df = (
            df[(df["race_year"] == ag_year) & (df["gender"].isin(["M", "F"]))]
            .groupby(["age_group", "gender"])["finish_time_seconds"]
            .agg(count="count", mean="mean")
            .reset_index()
        )
        fig = px.bar(
            ag_df[ag_df["count"] >= 5],
            x="age_group", y="mean", color="gender",
            color_discrete_map=PALETTE, barmode="group",
            labels={"mean": "Avg finish time (secs)", "age_group": "Age Group"},
            title=f"Average Finish Time by Age Group — {ag_year}",
        )
        fig.update_layout(height=420, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    # --- Tab 4: Top performers ---
    with tab4:
        min_ed = st.slider("Minimum editions", 2, 5, 2)
        top_n = st.slider("Show top N runners", 10, 30, 15)

        perf = (
            df.groupby("runner_name")
            .agg(
                editions=("race_year", "nunique"),
                avg_secs=("finish_time_seconds", "mean"),
                best_secs=("finish_time_seconds", "min"),
                gender=("gender", "first"),
            )
            .reset_index()
        )
        perf = (
            perf[perf["editions"] >= min_ed]
            .sort_values("avg_secs")
            .head(top_n)
        )
        perf["Avg Time"] = perf["avg_secs"].apply(secs_to_hms)
        perf["Best Time"] = perf["best_secs"].apply(secs_to_hms)

        fig = px.bar(
            perf[::-1],
            x="avg_secs", y="runner_name",
            orientation="h",
            color="gender", color_discrete_map=PALETTE,
            labels={"avg_secs": "Avg time (secs)", "runner_name": "Runner"},
            title=f"Top {top_n} Runners by Average Finish Time (≥{min_ed} editions)",
            text="Avg Time",
        )
        fig.update_layout(height=600, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)

        display_df = perf.rename(columns={
            "runner_name": "Runner", "editions": "Editions",
            "gender": "Gender",
        })[["Runner", "Gender", "Editions", "Avg Time", "Best Time"]]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
