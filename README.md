# 🏃 San Silvestre Coruña — Race Analytics Platform

End-to-end data pipeline to scrape, store, analyse, and visualise 16+ years of results from the **San Silvestre Coruña** race (A Coruña, Spain).

---

## Project Structure

```
race_analytics/
├── scrapy_project/          # Phase 1 — Web scraping
│   ├── scrapy.cfg
│   └── race_scraper/
│       ├── settings.py      # Respectful crawling config
│       ├── items.py         # Data schema for scraped items
│       ├── pipelines.py     # Cleaning + JSON writer
│       └── spiders/
│           └── san_silvestre.py   # Main spider
│
├── database/                # Phase 2 — Data storage
│   ├── schema.sql           # Normalised PostgreSQL/MariaDB schema + views
│   └── load_data.py         # JSON → DB loader
│
├── analysis/                # Phase 3 — Analytics
│   └── analysis.py          # Charts + summary statistics
│       └── output/          # Generated charts & report (after running)
│
├── dashboard/               # Phase 4 — Streamlit app
│   └── app.py
│
├── data/                    # Scraped JSON files (git-ignored for large sets)
│   └── results_YYYY.json
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Scrape the data (Phase 1)

```bash
cd scrapy_project
scrapy crawl san_silvestre
```

Output JSON files land in `data/results_YYYY.json`.  
The spider respects robots.txt, applies 1.5 s delays between requests, and uses a descriptive User-Agent.

### 3. Set up the database (Phase 2)

**PostgreSQL:**
```bash
createdb race_analytics
cd database
python load_data.py \
    --db-url postgresql://postgres:password@localhost:5432/race_analytics \
    --data-dir ../data \
    --apply-schema
```

**MariaDB:**
```bash
mysql -u root -p -e "CREATE DATABASE race_analytics;"
python load_data.py \
    --db-url mysql+pymysql://root:password@localhost:3306/race_analytics \
    --data-dir ../data \
    --apply-schema
```

### 4. Run analytics (Phase 3)

```bash
cd analysis
python analysis.py --data-dir ../data --output-dir ./output
# Opens output/report.html with charts
```

### 5. Launch the dashboard (Phase 4)

```bash
cd dashboard
streamlit run app.py
```

Open your browser at `http://localhost:8501`

---

## Database Schema

```
editions   ←──┐
               │ (FK)
runners    ←──┼── results (fact table)
               │
               └── (analytics views: vw_yearly_gender_stats,
                                     vw_age_group_stats,
                                     vw_top_performers)
```

Key design decisions:
- **Runners are de-duplicated** on normalised full name (upper-case). A runner participating in multiple editions has one row in `runners` and multiple rows in `results`.
- **Duplicate result prevention** via `UNIQUE (edition_id, runner_id)` constraint with `ON CONFLICT DO UPDATE`.
- **Pre-built views** for the most common analytical queries to avoid expensive GROUP BYs in the dashboard.

### ERD (text representation)

```
editions(edition_id PK, edition_name, race_year UNIQUE, race_date, location, distance_km)
runners(runner_id PK, full_name UNIQUE, first_name, last_name)
results(result_id PK, edition_id FK, runner_id FK,
        finish_time, finish_time_secs, pace_per_km_secs,
        overall_position, gender_position, category_position,
        gender, age_group, bib_number, source_url, scraped_at)
```

---

## Dashboard Features

### 🏁 Race Analysis
- Edition selector → filters the entire view
- Finish time histogram with mean/median overlays
- Gender and age group filters
- Statistical summary (min, max, mean, median, percentiles)
- Age group breakdown bar chart
- Full results table (expandable)

### 👤 Runner Analysis
- Free-text runner search (≥3 characters)
- Career summary KPIs (editions, best/avg time, best position)
- Race history table with pace column
- Finish time progression line chart
- Highlighted position within a specific race's distribution

### 📈 Historical Trends
- Stacked bar chart: finishers by year and gender
- Female participation rate over time
- Mean/median/winner time evolution
- Average time by age group per year
- Top performers leaderboard (configurable min editions)

---

## Scraping Ethics

- `ROBOTSTXT_OBEY = True`
- `DOWNLOAD_DELAY = 1.5 s` (randomised ±0.5 s)
- `CONCURRENT_REQUESTS = 1`
- Auto-throttle enabled
- Descriptive User-Agent string identifying this as an academic project
- All data is publicly available race results

---

## .gitignore

```
__pycache__/
*.pyc
.venv/
data/results_*.json       # Large scraped datasets
analysis/output/          # Generated charts
.scrapy/
*.db
.env
```

---

## Reproducing Results

1. Clone the repo
2. `pip install -r requirements.txt`
3. `cd scrapy_project && scrapy crawl san_silvestre`
4. Run the database loader or go directly to analysis/dashboard with the JSON files

No manual steps required beyond the above. The spider auto-discovers all editions from the results index page.
