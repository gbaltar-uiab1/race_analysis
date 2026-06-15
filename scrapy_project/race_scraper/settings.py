BOT_NAME = "race_scraper"

SPIDER_MODULES = ["race_scraper.spiders"]
NEWSPIDER_MODULE = "race_scraper.spiders"

# Respectful crawling
USER_AGENT = "RaceAnalyticsBot/1.0 (academic project; contact: student@example.com)"
ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 1
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 5
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# Pipelines
ITEM_PIPELINES = {
    "race_scraper.pipelines.CleaningPipeline": 200,
    "race_scraper.pipelines.JsonWriterPipeline": 300,
}

FEEDS = {}  # We handle output ourselves in the pipeline

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
LOG_LEVEL = "INFO"
