import psutil
from datetime import datetime
from datetime import UTC
from zoneinfo import ZoneInfo
from datetime import timedelta

EDT = ZoneInfo("America/New_York")


def format_scaled_unit(
    td: timedelta,
    sig: int = 2,
    orders: dict[str, int] = {
        "micros": 1,
        "millis": 1000,
        "sec": 1000,
        "min": 60,
        "hr": 60,
        "days": 24,
        "weeks": 7,
        "months": 4,
        "years": 12,
    },
):
    n = td.total_seconds() * 1000000
    for unit, magnitude in orders.items():
        n /= magnitude
        if n < 10:
            return f"{n:.{sig}f} {unit}"
