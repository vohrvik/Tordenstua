"""Publish an ICS feed with Tordenstua meetings in weekday hours, Oslo time.

FullCalendar's original calendar.ics is not modified. Expand recurring
occurrences and omit all-day events, cancellations and non-work-hour meetings.
"""
from __future__ import annotations
import hashlib
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar, Event

OSLO = ZoneInfo("Europe/Oslo")
START_HOUR = 7
END_HOUR = 17
DAYS_IN_PAST = 14
DAYS_IN_FUTURE = 110

def local_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=OSLO) if value.tzinfo is None else value.astimezone(OSLO)
    return datetime.combine(value, time.min, OSLO)

def main(input_file: str, output_file: str) -> None:
    source = Calendar.from_ical(Path(input_file).read_bytes())
    now = datetime.now(OSLO)
    search_start = datetime.combine(now.date() - timedelta(days=DAYS_IN_PAST), time.min, OSLO)
    search_end = datetime.combine(now.date() + timedelta(days=DAYS_IN_FUTURE), time.min, OSLO)
    occurrences = recurring_ical_events.of(source).between(search_start, search_end)

    output = Calendar()
    output.add("prodid", "-//Tordenstua Zigno Workday ICS//NO")
    output.add("version", "2.0")
    output.add("calscale", "GREGORIAN")
    output.add("method", "PUBLISH")
    output.add("x-wr-calname", "Tordenstua 07-17")

    seen = set()
    stamp = datetime.now(timezone.utc)
    count = 0
    for item in occurrences:
        if str(item.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start_field = item.get("DTSTART")
        if start_field is None:
            continue
        raw_start = start_field.dt
        if isinstance(raw_start, date) and not isinstance(raw_start, datetime):
            continue
        start = local_datetime(raw_start)
        if item.get("DTEND") is not None:
            end = local_datetime(item["DTEND"].dt)
        elif item.get("DURATION") is not None:
            end = start + item.decoded("DURATION")
        else:
            end = start + timedelta(hours=1)
        if end <= start:
            continue

        uid = str(item.get("UID", "missing-uid"))
        title = " ".join(str(item.get("SUMMARY", "Uten tittel")).split())
        location = " ".join(str(item.get("LOCATION", "")).split())
        day = max(search_start.date(), start.date())
        final_day = min((search_end - timedelta(days=1)).date(),
                        (end - timedelta(microseconds=1)).date())
        while day <= final_day:
            if day.weekday() < 5:
                start_of_day = datetime.combine(day, time(START_HOUR), OSLO)
                end_of_day = datetime.combine(day, time(END_HOUR), OSLO)
                visible_start = max(start, start_of_day)
                visible_end = min(end, end_of_day)
                if visible_start < visible_end:
                    event_uid = (hashlib.sha256(
                        f"{uid}|{start.isoformat()}|{day.isoformat()}".encode("utf-8")
                    ).hexdigest()[:24] + "@tordenstua-zigno")
                    if event_uid not in seen:
                        seen.add(event_uid)
                        event = Event()
                        event.add("uid", event_uid)
                        event.add("dtstamp", stamp)
                        event.add("dtstart", visible_start.astimezone(timezone.utc))
                        event.add("dtend", visible_end.astimezone(timezone.utc))
                        event.add("summary", title)
                        if location:
                            event.add("location", location)
                        output.add_component(event)
                        count += 1
            day += timedelta(days=1)

    Path(output_file).write_bytes(output.to_ical())
    verified = Calendar.from_ical(Path(output_file).read_bytes())
    actual = len(verified.walk("VEVENT"))
    if actual != count:
        raise RuntimeError(f"Validation mismatch: {count} generated, {actual} parsed")
    print(f"Generated {output_file}: {count} weekday events between 07:00 and 17:00")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: make_zigno_ics.py SOURCE.ics TARGET.ics")
    main(sys.argv[1], sys.argv[2])
