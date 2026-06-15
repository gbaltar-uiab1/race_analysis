import scrapy


class RaceResultItem(scrapy.Item):
    # Runner identity
    runner_name = scrapy.Field()       # Full name (nombre + apellidos)
    first_name = scrapy.Field()
    last_name = scrapy.Field()

    # Race performance
    finish_time = scrapy.Field()       # "HH:MM:SS"
    finish_time_seconds = scrapy.Field()  # Numeric for analysis
    overall_position = scrapy.Field()
    gender_position = scrapy.Field()
    category_position = scrapy.Field()

    # Runner classification
    age_group = scrapy.Field()         # Raw category string from site
    gender = scrapy.Field()            # "M" or "F" (inferred from category or gender position prefix)

    # Race metadata
    race_name = scrapy.Field()         # e.g. "CARRERA PRINCIPAL"
    race_edition = scrapy.Field()      # e.g. "SAN SILVESTRE A CORUÑA 2024"
    race_year = scrapy.Field()         # Numeric year
    race_date = scrapy.Field()         # ISO date string when available
    race_distance_km = scrapy.Field()  # Numeric distance
    location = scrapy.Field()          # "A Coruña"

    # Scraper bookkeeping
    source_url = scrapy.Field()
    bib_number = scrapy.Field()
    scraped_at = scrapy.Field()
