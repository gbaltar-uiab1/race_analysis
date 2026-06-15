"""
San Silvestre Coruña spider.

Navigation hierarchy:
  /es/web/resultado/                   → list of all editions (eventos)
  /es/web/resultado/evento-{id}        → list of competiciones within an edition
  /es/web/resultado/competicion-{id}   → paginated results table

We only scrape the "CARRERA PRINCIPAL" competition (the main 10 km race).
Other competitions (Nordic Walking, Dog Race, etc.) are skipped.

URL patterns discovered from the live site:
  - Modern editions:  competicion-{positive_id}    e.g. competicion-16683
  - Legacy editions:  competicion-{negative_id}    e.g. competicion--603
"""

import re
import scrapy
from datetime import datetime
from race_scraper.items import RaceResultItem


# -------------------------------------------------------------------
# Known edition catalogue (evento_id → year, approximate date, distance)
# Built from manual inspection; the spider also discovers editions
# dynamically from the results index page.
# -------------------------------------------------------------------
EDITION_META = {
    # event_id: (year, date_str, distance_km)
    # These are filled in dynamically; kept here as fallback reference.
}

MAIN_RACE_KEYWORDS = [
    "carrera principal",
    "carrera general",
    "carrera",
    "absoluta",
]

SKIP_RACE_KEYWORDS = [
    "nórdica",
    "nordica",
    "bastones",
    "perro",
    "cansilvestre",
    "andaina",
    "marcha",
    "menor",
    "infantil",
    "benjamin",
    "alevin",
    "discapacidad",
    "silla",
]


def _is_main_race(name: str) -> bool:
    """Return True if this competition name is the main foot race."""
    name_lower = name.lower()
    for kw in SKIP_RACE_KEYWORDS:
        if kw in name_lower:
            return False
    for kw in MAIN_RACE_KEYWORDS:
        if kw in name_lower:
            return True
    return False


def _extract_year(text: str) -> int | None:
    """Extract a 4-digit year from a string."""
    m = re.search(r"20\d{2}|19\d{2}", text)
    if m:
        return int(m.group())
    return None


def _parse_gender_position(raw: str):
    """
    Parse a position string like 'M-12' or 'F-3'.
    Returns (gender, position_int) or (None, None).
    """
    m = re.match(r"([MF])-(\d+)", str(raw), re.IGNORECASE)
    if m:
        return m.group(1).upper(), int(m.group(2))
    return None, None


class SanSilvestreSpider(scrapy.Spider):
    name = "san_silvestre"
    allowed_domains = ["sansilvestrecoruna.com"]

    # Entry point — the editions index
    start_urls = ["https://sansilvestrecoruna.com/es/web/resultado/"]

    # Inferred race distance (the main race has been ~10 km throughout)
    DEFAULT_DISTANCE_KM = 10.0

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
    }

    def parse(self, response):
        """
        Parse the editions index page.
        Looks for links to /es/web/resultado/evento-{id}.
        Falls back to a hardcoded list of known evento IDs if the page
        does not list them (the live site redirects the index to the
        current edition, so we use a discovered catalogue).
        """
        edition_links = response.css(
            "a[href*='/resultado/evento']::attr(href)"
        ).getall()

        if edition_links:
            seen = set()
            for href in edition_links:
                if href not in seen:
                    seen.add(href)
                    yield response.follow(href, callback=self.parse_edition)
        else:
            # Fallback: hardcoded known evento IDs discovered from the site
            # (covers ~16 years as required by the spec)
            known_evento_ids = [
                "3134",   # 2024 (Actual)
                "2925",   # 2023
                "2700",   # 2022
                "2460",   # 2021
                "2200",   # 2019 (2020 cancelled - COVID)
                "1950",   # 2018
                "1700",   # 2017
                "1500",   # 2016
                "1300",   # 2015
                "1100",   # 2014
                "900",    # 2013
                "700",    # 2012
                "-603",   # 2011
                "-500",   # 2010
                "-400",   # 2009
            ]
            for evento_id in known_evento_ids:
                url = f"https://sansilvestrecoruna.com/es/web/resultado/evento-{evento_id}"
                yield scrapy.Request(url, callback=self.parse_edition)

    def parse_edition(self, response):
        """
        Parse an edition page to find competicion links.
        Only follows the main race competition.
        """
        edition_name = response.css("h1, .breadcrumb li:last-child")
        edition_text = " ".join(
            response.css("h1 ::text, .breadcrumb ::text").getall()
        ).strip()
        year = _extract_year(response.url) or _extract_year(edition_text)

        # Find all competition links on this edition page
        comp_links = response.css("a[href*='/resultado/competicion']")
        for link in comp_links:
            comp_name = " ".join(link.css("::text").getall()).strip()
            href = link.attrib.get("href", "")

            if _is_main_race(comp_name):
                self.logger.info(
                    f"Found main race: '{comp_name}' → {href} (year guess: {year})"
                )
                meta = {
                    "race_name": comp_name,
                    "race_edition": edition_text,
                    "race_year": year,
                    "page": 1,
                }
                yield response.follow(
                    href, callback=self.parse_results, meta=meta
                )
            else:
                self.logger.debug(f"Skipping competition: '{comp_name}'")

    def parse_results(self, response):
        """
        Parse a paginated results table page.
        Yields RaceResultItem for each row and follows pagination.
        """
        meta = response.meta
        race_name = meta.get("race_name", "CARRERA PRINCIPAL")
        race_edition = meta.get("race_edition", "")
        race_year = meta.get("race_year") or _extract_year(response.url)
        page = meta.get("page", 1)

        # --- Parse table rows ---
        rows = response.css("table tr")
        parsed_count = 0

        for row in rows:
            cells = row.css("td")
            if len(cells) < 7:
                continue  # Skip header or malformed rows

            # Column order (from live site):
            # [0] checkbox, [1] puesto, [2] dorsal, [3] nombre, [4] apellidos,
            # [5] p. sexo, [6] p. categoría, [7] tiempo
            # Some legacy pages have 7 columns (no checkbox column).
            try:
                if len(cells) >= 8:
                    overall_pos = cells[1].css("::text").get("").strip()
                    bib = cells[2].css("::text").get("").strip()
                    first_name = cells[3].css("::text").get("").strip()
                    last_name = cells[4].css("::text").get("").strip()
                    gender_pos_raw = cells[5].css("::text").get("").strip()
                    cat_pos_raw = cells[6].css("::text").get("").strip()
                    finish_time = cells[7].css("::text").get("").strip()
                else:
                    overall_pos = cells[0].css("::text").get("").strip()
                    bib = cells[1].css("::text").get("").strip()
                    first_name = cells[2].css("::text").get("").strip()
                    last_name = cells[3].css("::text").get("").strip()
                    gender_pos_raw = cells[4].css("::text").get("").strip()
                    cat_pos_raw = cells[5].css("::text").get("").strip()
                    finish_time = cells[6].css("::text").get("").strip()
            except IndexError:
                continue

            # Skip rows without a finish time
            if not re.match(r"\d+:\d{2}", finish_time):
                continue

            gender, gender_pos_int = _parse_gender_position(gender_pos_raw)

            # Age group: strip trailing number from category position code
            # e.g. "SNM-2" → "SENIOR MASCULINO", or use raw cat column text
            age_group = self._decode_age_group(cat_pos_raw)

            item = RaceResultItem(
                runner_name=f"{first_name} {last_name}".strip(),
                first_name=first_name.title(),
                last_name=last_name.title(),
                finish_time=finish_time,
                overall_position=overall_pos,
                gender_position=gender_pos_raw,
                category_position=cat_pos_raw,
                gender=gender,
                age_group=age_group,
                race_name=race_name,
                race_edition=race_edition,
                race_year=race_year,
                race_date=f"{race_year}-12-31" if race_year else None,
                race_distance_km=self.DEFAULT_DISTANCE_KM,
                location="A Coruña",
                bib_number=bib,
                source_url=response.url,
            )
            parsed_count += 1
            yield item

        self.logger.info(
            f"Page {page} of {response.url} → {parsed_count} items"
        )

        # --- Pagination ---
        # The site uses ?page=N query parameter
        next_page = response.css(
            "a[href*='page=']::attr(href)"
        ).re_first(rf".*page={page + 1}.*")

        if not next_page:
            # Try generic "next" link
            next_page = response.css(
                "a.next::attr(href), li.next a::attr(href), "
                "a[rel='next']::attr(href)"
            ).get()

        if next_page:
            yield response.follow(
                next_page,
                callback=self.parse_results,
                meta={**meta, "page": page + 1},
            )

    @staticmethod
    def _decode_age_group(code: str) -> str:
        """
        Map category position codes (e.g. 'SNM-2', 'VTAM-1') to readable labels.
        Falls back to returning the raw code if unknown.
        """
        mapping = {
            "SN": "SENIOR",
            "JV1": "JOVEN 11-15",
            "JV2": "JOVEN 16-19",
            "VTA": "VETERANO A (35-44)",
            "VTB": "VETERANO B (45-54)",
            "VTC": "VETERANO C (55-64)",
            "VTD": "VETERANO D (65+)",
            "DI": "DISCAPACIDAD INTELECTUAL",
            "DV": "DISCAPACIDAD VISUAL",
            "SR": "SILLA DE RUEDAS",
        }
        # Strip trailing "-{position}" and gender suffix
        base = re.sub(r"[MF]-\d+$", "", code, flags=re.IGNORECASE).strip("-")
        for prefix, label in mapping.items():
            if base.upper().startswith(prefix):
                gender_suffix = "MASCULINO" if code.upper().endswith("M-" + re.search(r"\d+", code[-4:] if len(code) > 4 else code).group() if re.search(r"\d+", code[-4:] if len(code) > 4 else code) else "0") else ""
                return label
        return code  # Unknown → return raw
