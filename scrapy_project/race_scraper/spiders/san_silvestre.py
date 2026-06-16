import re, scrapy
from race_scraper.items import RaceResultItem

EDITIONS = [
    (2024, "https://sansilvestrecoruna.com/es/web/resultado/evento-2708"),
    (2023, "https://sansilvestrecoruna.com/es/web/resultado/evento-2663"),
    (2022, "https://sansilvestrecoruna.com/es/web/resultado/evento-2426"),
    (2021, "https://sansilvestrecoruna.com/es/web/resultado/evento-2212"),
    (2019, "https://sansilvestrecoruna.com/es/web/resultado/evento-1952"),
    (2018, "https://sansilvestrecoruna.com/es/web/resultado/evento-1639"),
    (2017, "https://sansilvestrecoruna.com/es/web/resultado/evento-1324"),
    (2016, "https://sansilvestrecoruna.com/es/web/resultado/evento-995"),
    (2015, "https://sansilvestrecoruna.com/es/web/resultado/evento-661"),
    (2014, "https://sansilvestrecoruna.com/es/web/resultado/evento-347"),
    (2012, "https://sansilvestrecoruna.com/es/web/resultado/evento--836"),
    (2011, "https://sansilvestrecoruna.com/es/web/resultado/evento--603"),
    (2010, "https://sansilvestrecoruna.com/es/web/resultado/evento--435"),
]

SKIP = ["nórdica","nordica","bastones","perro","cansilvestre","andaina",
        "marcha","infantil","benjamin","alevin","discapacidad","silla",
        "virtual","empresa"]

class SanSilvestreSpider(scrapy.Spider):
    name = "san_silvestre"
    allowed_domains = ["sansilvestrecoruna.com"]
    start_urls = []
    custom_settings = {"DOWNLOAD_DELAY": 1.5, "ROBOTSTXT_OBEY": False}

    def start_requests(self):
        for year, url in EDITIONS:
            yield scrapy.Request(url, callback=self.parse_edition, meta={"race_year": year})

    def parse_edition(self, response):
        year = response.meta["race_year"]
        for a in response.css("a[href*='/resultado/competicion']"):
            name = " ".join(a.css("*::text").getall()).strip()
            if not any(k in name.lower() for k in SKIP):
                self.logger.info(f"Year {year} main race: {name}")
                yield response.follow(a, callback=self.parse_results,
                    meta={"race_year": year, "race_name": name, "page": 1})

    def parse_results(self, response):
        year = response.meta["race_year"]
        page = response.meta["page"]
        parsed = 0
        for row in response.css("table tr.even, table tr.odd"):
            t = row.css("td.tiempo_display::text").get("").strip()
            if not re.match(r"\d+:\d{2}", t): continue
            fn = row.css("td.nombre a::text").get("").strip()
            ln = row.css("td.apellidos a::text").get("").strip()
            gp = row.css("td.get_puesto_sexo_display::text").get("").strip()
            m  = re.match(r"([MF])-\d+", gp, re.IGNORECASE)
            yield RaceResultItem(
                runner_name=f"{fn} {ln}".strip().title(),
                first_name=fn.title(), last_name=ln.title(),
                finish_time=t,
                finish_time_seconds=sum(int(x)*s for x,s in zip(t.split(":"), [3600,60,1])),
                overall_position=row.css("td.puesto::text").get("").strip(),
                gender_position=gp,
                category_position=row.css("td.get_puesto_categoria_display::text").get("").strip(),
                age_group=row.css("td.get_puesto_categoria_display::text").get("").strip(),
                gender=m.group(1).upper() if m else "U",
                race_name=response.meta["race_name"],
                race_edition=f"SAN SILVESTRE A CORUÑA {year}",
                race_year=year, race_date=f"{year}-12-31",
                race_distance_km=10.0, location="A Coruña",
                bib_number=row.css("td.dorsal::text").get("").strip(),
                source_url=response.url,
            )
            parsed += 1
        self.logger.info(f"Year {year} page {page} → {parsed} items")
        if response.css(f"a[href*='page={page+1}']"):
            yield response.follow(f"?page={page+1}", callback=self.parse_results,
                meta={**response.meta, "page": page+1})
