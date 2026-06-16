"""
San Silvestre Coruña spider.

Navigation:
  /es/web/resultado/          → lists all eventos (editions) with real IDs
  /es/web/resultado/evento-N  → lists competicions for that edition
  /es/web/resultado/competicion-N?page=X → paginated results table

We scrape only the main foot race (skip Nordic walking, dogs, etc.).

Competicion page columns (confirmed from HTML):
  td.seleccionar              → checkbox (skip)
  td.puesto                   → overall position
  td.dorsal                   → bib number
  td.nombre                   → first name
  td.apellidos                → last name
  td.get_puesto_sexo_display  → gender position (e.g. "M-1")
  td.get_puesto_categoria_display → category position (e.g. "SNM-1")
  td.tiempo_display           → finish time (HH:MM:SS)
"""

import re
import scrapy
from race_scraper.items import RaceResultItem

SKIP_KEYWORDS = [
    "nórdica", "nordica", "bastones", "perro", "cansilvestre",
    "andaina", "marcha", "menor", "infantil", "benjamin",
    "alevin", "discapacidad", "silla", "virtual",
]

YEAR_RE = re.compile(r"20\d{2}|19\d{2}")


def extract_year(text):
    m = YEAR_RE.search(str(text))
    return int(m.group()) if m else None


def is_main_race(name):
    return not any(kw in name.lower() for kw in SKIP_KEYWORDS)


class SanSilvestreSpider(scrapy.Spider):
    name = "san_silvestre"
    allowed_domains = ["sansilvestrecoruna.com"]
    # The index page lists all editions — confirmed working with trailing slash
    start_urls = ["https://sansilvestrecoruna.com/es/web/resultado/"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "ROBOTSTXT_OBEY": True,
    }

    def parse(self, response):
        """Parse the editions index — find all evento links."""
        evento_links = response.css("a[href*='/resultado/evento']")
        self.logger.info(f"Found {len(evento_links)} edition links on index page")

        for link in evento_links:
            href = link.attrib["href"]
            text = link.css("::text").get("").strip()
            year = extract_year(text) or extract_year(href)
            # Skip virtual editions
            if "virtual" in text.lower():
                self.logger.info(f"Skipping virtual edition: {text}")
                continue
            self.logger.info(f"Queuing edition: {text} ({year}) → {href}")
            yield response.follow(
                href,
                callback=self.parse_edition,
                meta={"race_year": year, "race_edition": text.strip()},
            )

    def parse_edition(self, response):
        """Find the main race competicion link for this edition."""
        meta = response.meta
        comp_links = response.css("a[href*='/resultado/competicion']")
        self.logger.info(
            f"Edition {meta.get('race_year')}: found {len(comp_links)} competition(s)"
        )

        for link in comp_links:
            name = link.css("::text").get("").strip()
            href = link.attrib["href"]
            if is_main_race(name):
                self.logger.info(f"  → Main race: '{name}' {href}")
                yield response.follow(
                    href,
                    callback=self.parse_results,
                    meta={**meta, "race_name": name, "page": 1},
                )
            else:
                self.logger.info(f"  → Skipping: '{name}'")

    def parse_results(self, response):
        """Parse one page of results from a competicion page."""
        meta = response.meta
        race_year = meta.get("race_year")
        page = meta.get("page", 1)

        parsed = 0
        for row in response.css("table tr.even, table tr.odd"):
            finish_time = row.css("td.tiempo_display::text").get("").strip()
            if not re.match(r"\d+:\d{2}", finish_time):
                continue

            first_name   = row.css("td.nombre::text").get("").strip()
            last_name    = row.css("td.apellidos::text").get("").strip()
            overall_pos  = row.css("td.puesto::text").get("").strip()
            bib          = row.css("td.dorsal::text").get("").strip()
            gender_pos   = row.css("td.get_puesto_sexo_display::text").get("").strip()
            cat_pos      = row.css("td.get_puesto_categoria_display::text").get("").strip()

            # Gender from position prefix: "M-1" → M, "F-1" → F
            m = re.match(r"([MF])-\d+", gender_pos, re.IGNORECASE)
            gender = m.group(1).upper() if m else "U"

            yield RaceResultItem(
                runner_name=f"{first_name} {last_name}".strip().title(),
                first_name=first_name.title(),
                last_name=last_name.title(),
                finish_time=finish_time,
                overall_position=overall_pos,
                gender_position=gender_pos,
                category_position=cat_pos,
                gender=gender,
                age_group=cat_pos,
                race_name=meta.get("race_name", "CARRERA PRINCIPAL"),
                race_edition=meta.get("race_edition", f"SAN SILVESTRE A CORUÑA {race_year}"),
                race_year=race_year,
                race_date=f"{race_year}-12-31" if race_year else None,
                race_distance_km=10.0,
                location="A Coruña",
                bib_number=bib,
                source_url=response.url,
            )
            parsed += 1

        self.logger.info(f"Year {race_year} page {page} → {parsed} items")

        # Pagination — pages are listed as ?page=N
        next_href = response.css(f"a[href*='page={page + 1}']::attr(href)").get()
        if next_href:
            yield response.follow(
                next_href,
                callback=self.parse_results,
                meta={**meta, "page": page + 1},
            )
