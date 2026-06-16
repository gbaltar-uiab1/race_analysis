import json
import re
import os
from datetime import datetime
from itemadapter import ItemAdapter


class CleaningPipeline:
    """
    Validates and normalises scraped items.
    Drops items with missing critical fields.
    """

    REQUIRED_FIELDS = ["finish_time", "race_year"]

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)

        # --- Drop items missing critical fields ---
        for field in self.REQUIRED_FIELDS:
            if not adapter.get(field):
                spider.logger.warning(
                    f"Dropping item missing '{field}': {dict(adapter)}"
                )
                from scrapy.exceptions import DropItem
                raise DropItem(f"Missing required field: {field}")

        # --- Normalise finish time ---
        raw_time = adapter.get("finish_time", "")
        seconds = self._time_to_seconds(raw_time)
        if seconds is not None:
            adapter["finish_time_seconds"] = seconds
        else:
            from scrapy.exceptions import DropItem
            raise DropItem(f"Unparseable finish time: {raw_time}")

        # --- Clean runner name ---
        name = adapter.get("runner_name", "").strip().title()
        adapter["runner_name"] = name

        # --- Infer gender from gender position prefix (e.g. "M-1" → Male) ---
        if not adapter.get("gender"):
            g_pos = adapter.get("gender_position", "") or ""
            if str(g_pos).startswith("M"):
                adapter["gender"] = "M"
            elif str(g_pos).startswith("F") or str(g_pos).startswith("W"):
                adapter["gender"] = "F"
            else:
                # Fall back to category string
                cat = adapter.get("age_group", "").upper()
                if "FEM" in cat or "FEMENIN" in cat:
                    adapter["gender"] = "F"
                elif "MASC" in cat or "MASCULIN" in cat:
                    adapter["gender"] = "M"
                else:
                    adapter["gender"] = "U"  # Unknown

        # --- Normalise positions to integers ---
        for pos_field in ["overall_position", "finish_time_seconds", "race_year", "bib_number"]:
            val = adapter.get(pos_field)
            if val is not None:
                try:
                    adapter[pos_field] = int(val)
                except (ValueError, TypeError):
                    pass

        # --- Default location ---
        if not adapter.get("location"):
            adapter["location"] = "A Coruña"

        # --- Timestamp ---
        adapter["scraped_at"] = datetime.utcnow().isoformat()

        return item

    @staticmethod
    def _time_to_seconds(time_str):
        """Convert 'HH:MM:SS' or 'MM:SS' to total seconds. Returns None on failure."""
        if not time_str:
            return None
        parts = str(time_str).strip().split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return None
        return None


class JsonWriterPipeline:
    """
    Writes items to a JSON Lines file (one JSON object per line).
    File is partitioned by race year for manageability.
    """

    def open_spider(self, spider):
        os.makedirs("data", exist_ok=True)
        self.files = {}

    def close_spider(self, spider):
        for f in self.files.values():
            f.write("\n]")
            f.close()
        spider.logger.info(
            f"JsonWriterPipeline closed {len(self.files)} output file(s)."
        )

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        year = adapter.get("race_year", "unknown")

        if year not in self.files:
            path = f"data/results_{year}.json"
            f = open(path, "w", encoding="utf-8")
            f.write("[")
            self.files[year] = f
            self.files[year]._first = True

        f = self.files[year]
        if not f._first:
            f.write(",\n")
        else:
            f._first = False

        json.dump(dict(adapter), f, ensure_ascii=False)
        return item
