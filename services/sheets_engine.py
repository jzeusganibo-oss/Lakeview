import os

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_gspread_client() -> gspread.Client:
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            "Google credentials file not found. Set GOOGLE_APPLICATION_CREDENTIALS or place credentials.json in the project root."
        )

    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def _open_or_create_spreadsheet(client: gspread.Client, name: str, owner_email: str | None = None):
    """Open an existing spreadsheet or create it if missing.

    If created and `owner_email` is provided the sheet will be shared with that address.
    Returns (spreadsheet, created_bool).
    """
    created = False
    try:
        spreadsheet = client.open(name)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(name)
        created = True
        if owner_email:
            try:
                spreadsheet.share(owner_email, perm_type="user", role="writer")
            except Exception:
                # sharing is best-effort; caller can share manually if this fails
                pass

        # ensure header row exists
        try:
            ws = spreadsheet.get_worksheet(0)
            headers = [
                "booking_id",
                "unit_id",
                "number_of_nights",
                "gross_revenue",
                "agent_name",
                "agent_commission",
                "caretaker",
                "cleaning_fee",
                "owner_net",
                "status",
            ]
            # set headers explicitly on row 1
            try:
                ws.update("A1", [headers], value_input_option="USER_ENTERED")
            except Exception:
                ws.append_row(headers)
        except Exception:
            pass

    else:
        # opened existing sheet; ensure headers are present
        try:
            ws = spreadsheet.get_worksheet(0)
            values = ws.get_all_values()
            if not values:
                headers = [
                    "booking_id",
                    "unit_id",
                    "number_of_nights",
                    "gross_revenue",
                    "agent_name",
                    "agent_commission",
                    "caretaker",
                    "cleaning_fee",
                    "owner_net",
                    "status",
                ]
                ws.append_row(headers)
        except Exception:
            pass

    return spreadsheet, created


def append_booking(booking_summary: dict):
    """Append a booking row to the configured Google Sheet.

    Environment variables:
    - GOOGLE_APPLICATION_CREDENTIALS: path to service account JSON (defaults to credentials.json)
    - SPREADSHEET_NAME: spreadsheet name to open/create
    - GOOGLE_SHEET_OWNER_EMAIL: optional email to share created spreadsheet with
    """
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    owner_email = os.getenv("GOOGLE_SHEET_OWNER_EMAIL")

    # If an explicit spreadsheet ID is provided, open by key. If a URL was provided
    # in SPREADSHEET_NAME, try extracting the ID from the URL and open by key.
    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None:
        # attempt to parse an ID from SPREADSHEET_NAME if it looks like a URL
        if "docs.google.com" in spreadsheet_name:
            import re

            m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
            if m:
                try:
                    spreadsheet = client.open_by_key(m.group(1))
                except Exception:
                    spreadsheet = None

    if spreadsheet is None:
        # fallback to open-or-create by name
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name, owner_email=owner_email)
    worksheet = spreadsheet.get_worksheet(0)

    # Ensure dedicated worksheets exist for bookings, payroll, caretaker ledger, and analytics
    def _ensure_worksheet(title: str, headers: list[str]):
        try:
            ws = spreadsheet.worksheet(title)
        except Exception:
            # create with a sensible size
            try:
                ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=20)
            except Exception:
                ws = spreadsheet.get_worksheet(0)
        # ensure headers are present on the first row
        try:
            values = ws.get_all_values()
            if not values:
                try:
                    ws.update("A1", [headers], value_input_option="USER_ENTERED")
                except Exception:
                    ws.append_row(headers, value_input_option="USER_ENTERED")
            else:
                first = [c.strip() for c in values[0]]
                # if headers differ, overwrite row 1 with our headers
                if first != [h.strip() for h in headers]:
                    try:
                        ws.update("A1", [headers], value_input_option="USER_ENTERED")
                    except Exception:
                        pass
        except Exception:
            pass

    bookings_headers = [
        "booking_id",
        "unit_id",
        "check_in",
        "check_out",
        "number_of_nights",
        "amount",
        "parking_fee",
        "gross_revenue",
        "agent_name",
        "agent_commission",
        "caretaker",
        "cleaning_fee",
        "owner_net",
        "status",
        "created_at",
        "reservation_fee",
        "payment_method",
        "balance",
        "balance_payment_method",
        "paid_balance",
    ]

    payroll_headers = ["timestamp", "booking_id", "agent_name", "agent_commission", "status"]
    caretaker_headers = ["timestamp", "booking_id", "caretaker", "cleaning_fee", "status"]
    analytics_headers = [
        "timestamp",
        "total_bookings",
        "total_gross_revenue",
        "total_agent_commission",
        "total_cleaning_fee",
        "total_owner_net",
    ]

    bookings_ws = None
    try:
        _ensure_worksheet("Bookings", bookings_headers)
        bookings_ws = spreadsheet.worksheet("Bookings")
    except Exception:
        bookings_ws = worksheet

    _ensure_worksheet("Agent Payroll", payroll_headers)
    _ensure_worksheet("Caretaker Ledger", caretaker_headers)
    _ensure_worksheet("Analytics", analytics_headers)

    # Prepare and append booking row
    from datetime import datetime

    created_at = booking_summary.get("created_at") or datetime.utcnow().isoformat()

    booking_row = [
        booking_summary.get("booking_id", ""),
        booking_summary.get("unit_id", ""),
        booking_summary.get("check_in", ""),
        booking_summary.get("check_out", ""),
        booking_summary.get("number_of_nights", ""),
        booking_summary.get("amount", ""),
        booking_summary.get("parking_fee", ""),
        booking_summary.get("gross_revenue", ""),
        booking_summary.get("agent_name", ""),
        booking_summary.get("agent_commission", ""),
        booking_summary.get("caretaker", ""),
        booking_summary.get("cleaning_fee", ""),
        booking_summary.get("owner_net", ""),
        booking_summary.get("status", "Pending"),
        created_at,
        booking_summary.get("reservation_fee", ""),
        booking_summary.get("payment_method", ""),
        booking_summary.get("balance", ""),
        booking_summary.get("balance_payment_method", ""),
        booking_summary.get("paid_balance", ""),
    ]

    try:
        bookings_ws.append_row(booking_row, value_input_option="USER_ENTERED")
    except Exception:
        # best-effort: append to first worksheet
        try:
            worksheet.append_row(booking_row, value_input_option="USER_ENTERED")
        except Exception:
            pass

    # Append payroll entry
    try:
        payroll_ws = spreadsheet.worksheet("Agent Payroll")
        payroll_row = [created_at, booking_summary.get("booking_id", ""), booking_summary.get("agent_name", ""), booking_summary.get("agent_commission", ""), booking_summary.get("status", "Pending")]
        payroll_ws.append_row(payroll_row, value_input_option="USER_ENTERED")
    except Exception:
        pass

    # Append caretaker ledger entry
    try:
        caretaker_ws = spreadsheet.worksheet("Caretaker Ledger")
        caretaker_row = [created_at, booking_summary.get("booking_id", ""), booking_summary.get("caretaker", ""), booking_summary.get("cleaning_fee", ""), booking_summary.get("status", "Pending")]
        caretaker_ws.append_row(caretaker_row, value_input_option="USER_ENTERED")
    except Exception:
        pass

    # Compute simple analytics and append summary row for history
    try:
        analytics_ws = spreadsheet.worksheet("Analytics")
        # read bookings and compute aggregates
        records = bookings_ws.get_all_records()
        total_bookings = len(records)
        def _to_float(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        total_gross = sum(_to_float(r.get("gross_revenue", 0)) for r in records)
        total_agent_commission = sum(_to_float(r.get("agent_commission", 0)) for r in records)
        total_cleaning_fee = sum(_to_float(r.get("cleaning_fee", 0)) for r in records)
        total_owner_net = sum(_to_float(r.get("owner_net", 0)) for r in records)

        analytics_row = [
            created_at,
            total_bookings,
            total_gross,
            total_agent_commission,
            total_cleaning_fee,
            total_owner_net,
        ]
        analytics_ws.append_row(analytics_row, value_input_option="USER_ENTERED")
    except Exception:
        pass

    return booking_row


def get_all_bookings(unit_id: str | None = None) -> list[dict]:
    """Return all bookings from the configured spreadsheet as a list of dicts.

    Requires the spreadsheet to exist or will create it if missing.
    """
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")

    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None:
        if "docs.google.com" in spreadsheet_name:
            import re

            m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
            if m:
                try:
                    spreadsheet = client.open_by_key(m.group(1))
                except Exception:
                    spreadsheet = None

    if spreadsheet is None:
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name)

    try:
        bookings_ws = spreadsheet.worksheet("Bookings")
    except Exception:
        bookings_ws = spreadsheet.get_worksheet(0)

    try:
        values = bookings_ws.get_all_values()
        if not values:
            return []
        # expected headers in the bookings sheet (same order used when appending)
        expected_headers = [
            "booking_id",
            "unit_id",
            "check_in",
            "check_out",
            "number_of_nights",
            "amount",
            "parking_fee",
            "gross_revenue",
            "agent_name",
            "agent_commission",
            "caretaker",
            "cleaning_fee",
            "owner_net",
            "status",
            "created_at",
        ]

        # If the first row looks like headers, use it; otherwise fall back to expected_headers
        first_row = values[0]
        if all(isinstance(h, str) and h.strip() for h in first_row) and any(h in first_row for h in expected_headers):
            headers = [h.strip() for h in first_row]
            data_rows = values[1:]
        else:
            headers = expected_headers
            data_rows = values

        records = []
        for row in data_rows:
            record = {headers[i] if i < len(headers) else f"col_{i}": (row[i] if i < len(row) else "") for i in range(len(headers))}
            records.append(record)

        if unit_id:
            unit_str = str(unit_id).strip()
            records = [r for r in records if str(r.get("unit_id", "")).strip() == unit_str]

        return records
    except Exception:
        return []


def update_booking(booking_id: str, updated_fields: dict) -> bool:
    """Update an existing row in the Bookings worksheet identified by booking_id.

    Preserves the original created_at timestamp. Returns True if a matching row was found and updated.
    """
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")

    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None:
        if "docs.google.com" in spreadsheet_name:
            import re

            m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
            if m:
                try:
                    spreadsheet = client.open_by_key(m.group(1))
                except Exception:
                    spreadsheet = None

    if spreadsheet is None:
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name)

    try:
        ws = spreadsheet.worksheet("Bookings")
    except Exception:
        return False

    try:
        values = ws.get_all_values()
        if not values:
            return False
        headers = [h.strip() for h in values[0]]
        id_idx = headers.index("booking_id") if "booking_id" in headers else 0

        row_number = None
        existing_row = None
        for i, row in enumerate(values[1:], start=2):
            if len(row) > id_idx and row[id_idx] == booking_id:
                row_number = i
                existing_row = row
                break

        if row_number is None:
            return False

        created_at = ""
        if "created_at" in headers:
            created_idx = headers.index("created_at")
            created_at = existing_row[created_idx] if len(existing_row) > created_idx else ""

        existing_status = "Pending"
        if "status" in headers:
            status_idx = headers.index("status")
            existing_status = existing_row[status_idx] if len(existing_row) > status_idx else "Pending"

        new_row = [
            booking_id,
            updated_fields.get("unit_id", ""),
            updated_fields.get("check_in", ""),
            updated_fields.get("check_out", ""),
            updated_fields.get("number_of_nights", ""),
            updated_fields.get("amount", ""),
            updated_fields.get("parking_fee", ""),
            updated_fields.get("gross_revenue", ""),
            updated_fields.get("agent_name", ""),
            updated_fields.get("agent_commission", ""),
            updated_fields.get("caretaker", ""),
            updated_fields.get("cleaning_fee", ""),
            updated_fields.get("owner_net", ""),
            updated_fields.get("status") or existing_status,
            created_at,
            updated_fields.get("reservation_fee", ""),
            updated_fields.get("payment_method", ""),
            updated_fields.get("balance", ""),
            updated_fields.get("balance_payment_method", ""),
            updated_fields.get("paid_balance", ""),
        ]
        ws.update(f"A{row_number}", [new_row], value_input_option="USER_ENTERED")
        return True
    except Exception:
        return False


def get_analytics(last_n_months: int = 12) -> dict:
    """Compute simple monthly aggregates from the Bookings worksheet.

    Returns a dict with:
      - monthly: list of {month: 'YYYY-MM', bookings: int, gross_revenue: float, agent_commission: float, cleaning_fee: float}
      - history: rows from the Analytics worksheet (if present)
    """
    from datetime import datetime
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")

    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None:
        if "docs.google.com" in spreadsheet_name:
            import re

            m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
            if m:
                try:
                    spreadsheet = client.open_by_key(m.group(1))
                except Exception:
                    spreadsheet = None

    if spreadsheet is None:
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name)

    # Read bookings
    try:
        bookings_ws = spreadsheet.worksheet("Bookings")
    except Exception:
        bookings_ws = spreadsheet.get_worksheet(0)

    def _to_float(v):
        try:
            return float(v)
        except Exception:
            return 0.0

    monthly = {}
    try:
        records = bookings_ws.get_all_records()
        for r in records:
            # Prefer check_in, fall back to created_at
            dstr = r.get("check_in") or r.get("created_at") or r.get("timestamp")
            try:
                if not dstr:
                    continue
                # accept YYYY-MM-DD or ISO formats
                ds = dstr.strip()
                if len(ds) >= 10:
                    ds = ds[:10]
                dt = datetime.strptime(ds, "%Y-%m-%d")
            except Exception:
                continue
            key = f"{dt.year:04d}-{dt.month:02d}"
            entry = monthly.get(key) or {"bookings": 0, "gross_revenue": 0.0, "agent_commission": 0.0, "cleaning_fee": 0.0}
            entry["bookings"] += 1
            entry["gross_revenue"] += _to_float(r.get("gross_revenue", 0))
            entry["agent_commission"] += _to_float(r.get("agent_commission", 0))
            entry["cleaning_fee"] += _to_float(r.get("cleaning_fee", 0))
            monthly[key] = entry
    except Exception:
        monthly = {}

    # build last_n_months ordered list
    now = datetime.utcnow()
    months_list = []
    for i in range(last_n_months - 1, -1, -1):
        # compute year/month offset without external deps
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y:04d}-{m:02d}"
        stats = monthly.get(key, {"bookings": 0, "gross_revenue": 0.0, "agent_commission": 0.0, "cleaning_fee": 0.0})
        months_list.append({"month": key, **stats})

    # read analytics history if exists
    history = []
    try:
        analytics_ws = spreadsheet.worksheet("Analytics")
        vals = analytics_ws.get_all_records()
        history = vals
    except Exception:
        history = []

    return {"monthly": months_list, "history": history}


def share_spreadsheet_with_emails(emails: list[str]):
    """Share the configured spreadsheet with the provided email addresses.

    Reads `SPREADSHEET_ID` or parses an ID from `SPREADSHEET_NAME` (same as append_booking).
    Returns a dict mapping email -> True/False indicating success.
    """
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")

    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None and "docs.google.com" in spreadsheet_name:
        import re

        m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
        if m:
            try:
                spreadsheet = client.open_by_key(m.group(1))
            except Exception:
                spreadsheet = None

    if spreadsheet is None:
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name)

    results = {}
    for email in emails:
        try:
            spreadsheet.share(email, perm_type="user", role="writer")
            results[email] = True
        except Exception:
            results[email] = False


def get_agent_payroll() -> list[dict]:
    """Return all rows from the 'Agent Payroll' worksheet as list of dicts.

    If the worksheet or spreadsheet is missing, it will be created with headers.
    """
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")

    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None:
        if "docs.google.com" in spreadsheet_name:
            import re

            m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
            if m:
                try:
                    spreadsheet = client.open_by_key(m.group(1))
                except Exception:
                    spreadsheet = None

    if spreadsheet is None:
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name)

    try:
        ws = spreadsheet.worksheet("Agent Payroll")
    except Exception:
        # ensure worksheet exists and return empty list
        try:
            ws = spreadsheet.add_worksheet(title="Agent Payroll", rows=1000, cols=20)
            ws.update("A1", [["timestamp", "booking_id", "agent_name", "agent_commission", "status"]], value_input_option="USER_ENTERED")
            return []
        except Exception:
            return []

    try:
        values = ws.get_all_values()
        if not values or len(values) == 0:
            return []
        headers = [c.strip() for c in values[0]]
        data_rows = values[1:]
        records = []
        for row in data_rows:
            record = {headers[i] if i < len(headers) else f"col_{i}": (row[i] if i < len(row) else "") for i in range(len(headers))}
            records.append(record)
        return records
    except Exception:
        return []


def get_caretaker_ledger() -> list[dict]:
    """Return all rows from the 'Caretaker Ledger' worksheet as list of dicts.

    If the worksheet or spreadsheet is missing, it will be created with headers.
    """
    client = _get_gspread_client()
    spreadsheet_name = os.getenv("SPREADSHEET_NAME", "Tagaytay_Lakeview_Staycation_Accounting_2026")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")

    spreadsheet = None
    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = None

    if spreadsheet is None:
        if "docs.google.com" in spreadsheet_name:
            import re

            m = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_name)
            if m:
                try:
                    spreadsheet = client.open_by_key(m.group(1))
                except Exception:
                    spreadsheet = None

    if spreadsheet is None:
        spreadsheet, _ = _open_or_create_spreadsheet(client, spreadsheet_name)

    try:
        ws = spreadsheet.worksheet("Caretaker Ledger")
    except Exception:
        # ensure worksheet exists and return empty list
        try:
            ws = spreadsheet.add_worksheet(title="Caretaker Ledger", rows=1000, cols=20)
            ws.update("A1", [["timestamp", "booking_id", "caretaker", "cleaning_fee", "status"]], value_input_option="USER_ENTERED")
            return []
        except Exception:
            return []

    try:
        values = ws.get_all_values()
        if not values or len(values) == 0:
            return []
        headers = [c.strip() for c in values[0]]
        data_rows = values[1:]
        records = []
        for row in data_rows:
            record = {headers[i] if i < len(headers) else f"col_{i}": (row[i] if i < len(row) else "") for i in range(len(headers))}
            records.append(record)
        return records
    except Exception:
        return []

    return results
