import requests
from datetime import datetime, date
from icalendar import Calendar


def check_calendar_availability(ical_url: str, check_in_date: str, check_out_date: str) -> bool:
    try:
        response = requests.get(ical_url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Unable to fetch calendar feed: {exc}") from exc

    cal = Calendar.from_ical(response.content)

    try:
        requested_check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
        requested_check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Dates must be in YYYY-MM-DD format") from exc

    if requested_check_out <= requested_check_in:
        raise ValueError("check_out_date must be after check_in_date")

    for event in cal.walk("VEVENT"):
        start = event.get("dtstart").dt
        end = event.get("dtend").dt

        if isinstance(start, datetime):
            start_date = start.date()
        else:
            start_date = start

        if isinstance(end, datetime):
            end_date = end.date()
        else:
            end_date = end

        if start_date < requested_check_out and end_date > requested_check_in:
            return False

    return True


if __name__ == "__main__":
    sample_url = "https://example.com/calendar.ics"
    print(check_calendar_availability(sample_url, "2026-08-10", "2026-08-14"))
