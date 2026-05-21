"""
Українські свята, пам'ятні дати та іменини.
Дані з вбудованого JSON-файлу.
"""
import json
import os
import logging
from datetime import date

log = logging.getLogger("myday.holidays")

_data_path = os.path.join(os.path.dirname(__file__), "holidays_data.json")

try:
    with open(_data_path, "r", encoding="utf-8") as f:
        HOLIDAYS_DB = json.load(f)
except FileNotFoundError:
    log.warning("holidays_data.json not found, using empty DB")
    HOLIDAYS_DB = {"state": {}, "notable": {}, "namedays": {}, "family_dates": {}}


def get_today_holidays(today: date = None) -> dict:
    """
    Get holidays and namedays for a given date.
    Returns dict with keys: state, notable, namedays, family_dates.
    """
    today = today or date.today()
    key = today.strftime("%m-%d")

    return {
        "state": HOLIDAYS_DB.get("state", {}).get(key, []),
        "notable": HOLIDAYS_DB.get("notable", {}).get(key, []),
        "namedays": HOLIDAYS_DB.get("namedays", {}).get(key, []),
        "family_dates": HOLIDAYS_DB.get("family_dates", {}).get(key, []),
    }


def add_family_date(month_day: str, description: str) -> bool:
    """
    Add a family date (e.g., birthday, anniversary).
    month_day format: "MM-DD" (e.g., "03-15")
    """
    if "family_dates" not in HOLIDAYS_DB:
        HOLIDAYS_DB["family_dates"] = {}

    if month_day not in HOLIDAYS_DB["family_dates"]:
        HOLIDAYS_DB["family_dates"][month_day] = []

    if description not in HOLIDAYS_DB["family_dates"][month_day]:
        HOLIDAYS_DB["family_dates"][month_day].append(description)
        _save()
        return True
    return False


def _save():
    """Save updated holidays data to disk."""
    try:
        with open(_data_path, "w", encoding="utf-8") as f:
            json.dump(HOLIDAYS_DB, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Failed to save holidays_data.json: %s", e)
