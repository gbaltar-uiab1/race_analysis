-- =============================================================
-- San Silvestre Coruña — Race Analytics Database Schema
-- Compatible with PostgreSQL 14+ and MariaDB 10.6+
-- =============================================================

-- ---------------------------------------------------------------
-- 1. EDITIONS  (one row per year the race was held)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS editions (
    edition_id   SERIAL PRIMARY KEY,
    edition_name VARCHAR(200) NOT NULL,
    race_year    SMALLINT    NOT NULL UNIQUE,
    race_date    DATE,
    location     VARCHAR(100) DEFAULT 'A Coruña',
    distance_km  NUMERIC(5,2) DEFAULT 10.00,
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------
-- 2. RUNNERS  (one row per unique person)
-- De-duplicated on normalised full name (case-insensitive).
-- A runner who participates in multiple editions has one row here
-- and multiple rows in results.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runners (
    runner_id   SERIAL PRIMARY KEY,
    full_name   VARCHAR(200) NOT NULL,
    first_name  VARCHAR(100),
    last_name   VARCHAR(150),
    UNIQUE (full_name)  -- normalised, upper-cased before insert
);

CREATE INDEX IF NOT EXISTS idx_runners_name ON runners (full_name);

-- ---------------------------------------------------------------
-- 3. RESULTS  (one row per runner × edition)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS results (
    result_id         SERIAL PRIMARY KEY,
    edition_id        INT           NOT NULL REFERENCES editions(edition_id),
    runner_id         INT           NOT NULL REFERENCES runners(runner_id),

    -- Performance
    finish_time       CHAR(8)       NOT NULL,   -- "HH:MM:SS"
    finish_time_secs  INT           NOT NULL,   -- total seconds (for arithmetic)
    pace_per_km_secs  INT,                      -- seconds per km

    -- Positions
    overall_position  INT,
    gender_position   INT,
    category_position VARCHAR(30),              -- e.g. "VTA-3"

    -- Classification
    gender            CHAR(1)       CHECK (gender IN ('M','F','U')),
    age_group         VARCHAR(100),
    bib_number        INT,

    -- Metadata
    source_url        TEXT,
    scraped_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (edition_id, runner_id)              -- one result per runner per edition
);

CREATE INDEX IF NOT EXISTS idx_results_edition   ON results (edition_id);
CREATE INDEX IF NOT EXISTS idx_results_runner    ON results (runner_id);
CREATE INDEX IF NOT EXISTS idx_results_year      ON results (edition_id);
CREATE INDEX IF NOT EXISTS idx_results_gender    ON results (gender);
CREATE INDEX IF NOT EXISTS idx_results_age_group ON results (age_group);

-- ---------------------------------------------------------------
-- 4. ANALYTICS VIEWS  (pre-computed for dashboard performance)
-- ---------------------------------------------------------------

-- Average and median finish time by year and gender
CREATE OR REPLACE VIEW vw_yearly_gender_stats AS
SELECT
    e.race_year,
    r.gender,
    COUNT(*)                                     AS participant_count,
    ROUND(AVG(r.finish_time_secs))               AS avg_time_secs,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY r.finish_time_secs)::INT       AS median_time_secs,
    MIN(r.finish_time_secs)                      AS min_time_secs,
    MAX(r.finish_time_secs)                      AS max_time_secs
FROM results r
JOIN editions e ON e.edition_id = r.edition_id
WHERE r.finish_time_secs IS NOT NULL
GROUP BY e.race_year, r.gender
ORDER BY e.race_year, r.gender;

-- Average finish time by age group
CREATE OR REPLACE VIEW vw_age_group_stats AS
SELECT
    e.race_year,
    r.age_group,
    r.gender,
    COUNT(*)                         AS participant_count,
    ROUND(AVG(r.finish_time_secs))   AS avg_time_secs
FROM results r
JOIN editions e ON e.edition_id = r.edition_id
WHERE r.age_group IS NOT NULL
GROUP BY e.race_year, r.age_group, r.gender
ORDER BY e.race_year, r.age_group;

-- Top performers: runners with best average time across ≥2 editions
CREATE OR REPLACE VIEW vw_top_performers AS
SELECT
    rn.full_name,
    COUNT(*)                              AS editions_count,
    ROUND(AVG(rs.finish_time_secs))       AS avg_time_secs,
    MIN(rs.finish_time_secs)              AS best_time_secs,
    rs.gender
FROM results rs
JOIN runners rn ON rn.runner_id = rs.runner_id
WHERE rs.finish_time_secs IS NOT NULL
GROUP BY rn.full_name, rn.runner_id, rs.gender
HAVING COUNT(*) >= 2
ORDER BY avg_time_secs;
