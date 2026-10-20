import os
import logging

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

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

        try:
            _write_dashboard_tab(spreadsheet, build_analytics_summary(records))
        except Exception:
            pass
    except Exception:
        pass

    return booking_row


def _auto_settle_overdue_balances(records: list[dict]) -> list[dict]:
    """If 24h+ have passed since check-in with no balance payment method set,
    assume the guest paid the balance in cash to the unit's caretaker."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    for record in records:
        if str(record.get("status") or "").strip().lower() != "pending":
            continue
        if str(record.get("balance_payment_method") or "").strip():
            continue
        try:
            balance = float(record.get("balance") or 0)
        except (TypeError, ValueError):
            balance = 0.0
        if balance <= 0:
            continue
        try:
            check_in = datetime.strptime(str(record.get("check_in"))[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if now < check_in + timedelta(hours=24):
            continue

        caretaker = record.get("caretaker") or "Ate Tess"
        record["balance_payment_method"] = caretaker
        record["paid_balance"] = balance
        record["balance"] = 0
        record["status"] = "Fully Paid"
        try:
            update_booking(record.get("booking_id", ""), record)
        except Exception:
            logger.exception("failed auto-settling overdue balance for %s", record.get("booking_id"))

    return records


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

        records = _auto_settle_overdue_balances(records)

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
        try:
            _write_dashboard_tab(spreadsheet, build_analytics_summary(ws.get_all_records()))
        except Exception:
            pass
        return True
    except Exception:
        return False


def delete_booking(booking_id: str) -> bool:
    """Delete a booking row (and its matching Agent Payroll / Caretaker Ledger entries) by booking_id.

    Returns True if the Bookings row was found and deleted.
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

    def _delete_matching_row(worksheet_name: str) -> bool:
        try:
            ws = spreadsheet.worksheet(worksheet_name)
        except Exception:
            return False
        try:
            values = ws.get_all_values()
            if not values:
                return False
            headers = [h.strip() for h in values[0]]
            if "booking_id" not in headers:
                return False
            id_idx = headers.index("booking_id")
            for i, row in enumerate(values[1:], start=2):
                if len(row) > id_idx and row[id_idx] == booking_id:
                    ws.delete_rows(i)
                    return True
        except Exception:
            return False
        return False

    deleted = _delete_matching_row("Bookings")
    # best-effort cleanup of related payroll/caretaker rows so deleted bookings
    # don't leave stale entries behind
    _delete_matching_row("Agent Payroll")
    _delete_matching_row("Caretaker Ledger")

    if deleted:
        try:
            ws = spreadsheet.worksheet("Bookings")
            _write_dashboard_tab(spreadsheet, build_analytics_summary(ws.get_all_records()))
        except Exception:
            pass

    return deleted


def cancel_booking(booking_id: str) -> bool:
    """Mark a booking as 'Cancelled'. The reservation fee already collected is kept
    (no refund policy), so only the status is changed and the remaining balance is
    cleared to zero since no further payment will be collected.

    Returns True if a matching row was found and updated.
    """
    from gspread.utils import rowcol_to_a1

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

    def _zero_ledger_amount(worksheet_name: str, amount_column: str) -> None:
        # Best-effort: cancelled bookings never get cleaned/commissioned, so the
        # matching Agent Payroll / Caretaker Ledger entries should not be paid out.
        try:
            ws = spreadsheet.worksheet(worksheet_name)
            values = ws.get_all_values()
            if not values:
                return
            headers = [h.strip() for h in values[0]]
            if "booking_id" not in headers or amount_column not in headers or "status" not in headers:
                return
            id_idx = headers.index("booking_id")
            amount_idx = headers.index(amount_column)
            status_idx = headers.index("status")
            for i, row in enumerate(values[1:], start=2):
                if len(row) > id_idx and row[id_idx] == booking_id:
                    updates = [
                        {"range": rowcol_to_a1(i, amount_idx + 1), "values": [[0]]},
                        {"range": rowcol_to_a1(i, status_idx + 1), "values": [["Cancelled"]]},
                    ]
                    ws.batch_update(updates, value_input_option="USER_ENTERED")
        except Exception:
            pass

    try:
        ws = spreadsheet.worksheet("Bookings")
    except Exception:
        return False

    try:
        values = ws.get_all_values()
        if not values:
            return False
        headers = [h.strip() for h in values[0]]
        if "booking_id" not in headers or "status" not in headers:
            return False
        id_idx = headers.index("booking_id")
        status_idx = headers.index("status")
        balance_idx = headers.index("balance") if "balance" in headers else None
        cleaning_idx = headers.index("cleaning_fee") if "cleaning_fee" in headers else None
        commission_idx = headers.index("agent_commission") if "agent_commission" in headers else None
        owner_net_idx = headers.index("owner_net") if "owner_net" in headers else None
        gross_idx = headers.index("gross_revenue") if "gross_revenue" in headers else None
        reservation_idx = headers.index("reservation_fee") if "reservation_fee" in headers else None

        for i, row in enumerate(values[1:], start=2):
            if len(row) > id_idx and row[id_idx] == booking_id:
                updates = [{"range": rowcol_to_a1(i, status_idx + 1), "values": [["Cancelled"]]}]
                if balance_idx is not None:
                    updates.append({"range": rowcol_to_a1(i, balance_idx + 1), "values": [[0]]})
                # No cleaning happens and no commission is earned for a cancelled stay.
                if cleaning_idx is not None:
                    updates.append({"range": rowcol_to_a1(i, cleaning_idx + 1), "values": [[0]]})
                if commission_idx is not None:
                    updates.append({"range": rowcol_to_a1(i, commission_idx + 1), "values": [[0]]})
                # The guest never paid the balance, so the only income kept is the
                # non-refundable reservation fee — gross revenue must reflect that.
                reservation_value = 0.0
                if reservation_idx is not None:
                    try:
                        reservation_value = float(row[reservation_idx]) if len(row) > reservation_idx and row[reservation_idx] != "" else 0.0
                    except Exception:
                        reservation_value = 0.0
                if gross_idx is not None:
                    updates.append({"range": rowcol_to_a1(i, gross_idx + 1), "values": [[reservation_value]]})
                if owner_net_idx is not None:
                    updates.append({"range": rowcol_to_a1(i, owner_net_idx + 1), "values": [[reservation_value]]})
                ws.batch_update(updates, value_input_option="USER_ENTERED")
                _zero_ledger_amount("Agent Payroll", "agent_commission")
                _zero_ledger_amount("Caretaker Ledger", "cleaning_fee")
                try:
                    _write_dashboard_tab(spreadsheet, build_analytics_summary(ws.get_all_records()))
                except Exception:
                    pass
                return True
    except Exception:
        return False

    return False


def _write_dashboard_tab(spreadsheet, summary: dict) -> None:
    """Write the same monthly/per-unit/receivables breakdown shown on the web
    Analytics page into a 'Dashboard' worksheet tab, so the Google Sheet mirrors it."""
    from datetime import datetime

    try:
        ws = spreadsheet.worksheet("Dashboard")
    except Exception:
        ws = spreadsheet.add_worksheet(title="Dashboard", rows=200, cols=10)

    rows = [
        ["Lakeview Staycation \u2014 Analytics Dashboard (auto-generated)"],
        [f"Last updated: {datetime.utcnow().isoformat()}"],
        [],
        ["Monthly Summary"],
        ["Month", "Bookings", "Gross Revenue", "Agent Commission", "Cleaning Fee", "Net Income"],
    ]
    for m in summary.get("monthly", []):
        rows.append([m["month"], m["bookings"], m["gross_revenue"], m["agent_commission"], m["cleaning_fee"], m["owner_net"]])

    rows += [[], ["Gross and Net per Unit"], ["Unit", "Bookings", "Gross Revenue", "Net Income"]]
    for u in summary.get("per_unit", []):
        rows.append([u["unit_id"], u["bookings"], u["gross_revenue"], u["owner_net"]])

    rows += [[], ["Receivables by Caretaker"], ["Caretaker", "Bookings", "Cash Collected", "Cleaning Fee Owed", "Net Receivable"]]
    for r in summary.get("receivables", []):
        rows.append([r["caretaker"], r["bookings"], r["cash_collected"], r["cleaning_fee_owed"], r["total_receivable"]])

    try:
        ws.clear()
        ws.update("A1", rows, value_input_option="USER_ENTERED")
    except Exception:
        pass


def normalize_caretaker_name(name: str | None) -> str:
    text = (name or "").strip()
    if not text:
        return "Unknown"
    key = text.lower()
    mapping = {
        "czarina": "Ate Czarina",
        "ate czarina": "Ate Czarina",
        "tess": "Ate Tess",
        "ate tess": "Ate Tess",
    }
    return mapping.get(key, text)


def build_analytics_summary(records: list[dict]) -> dict:
    def _to_float(value):
        try:
            return float(value)
        except Exception:
            return 0.0

    from datetime import date, datetime

    today = date.today()

    def _parse_date(value):
        try:
            ds = str(value).strip()
            if len(ds) >= 10:
                ds = ds[:10]
            return datetime.strptime(ds, "%Y-%m-%d").date()
        except Exception:
            return None

    monthly = {}
    per_unit = {}
    receivables = {}
    bookings_detail = []

    for row in records:
        dstr = row.get("check_in") or row.get("created_at") or row.get("timestamp")
        if not dstr:
            continue
        try:
            ds = str(dstr).strip()
            if len(ds) >= 10:
                ds = ds[:10]
            from datetime import datetime
            dt = datetime.strptime(ds, "%Y-%m-%d")
        except Exception:
            continue

        key = f"{dt.year:04d}-{dt.month:02d}"
        gross = _to_float(row.get("gross_revenue", 0))
        status = str(row.get("status") or "").strip().lower()
        checked_out_date = _parse_date(row.get("check_out"))
        already_checked_out = checked_out_date is not None and checked_out_date <= today

        # A cancelled guest never pays the remaining balance, so the only income
        # actually kept is the non-refundable reservation fee, not the full amount.
        if status == "cancelled":
            gross = _to_float(row.get("reservation_fee", 0))

        # A cancelled stay never gets cleaned and never earns the agent a
        # commission; an upcoming stay hasn't been cleaned/commissioned yet
        # either — both only "apply" once the guest has actually checked out.
        if status == "cancelled" or not already_checked_out:
            agent_commission = 0.0
            cleaning_fee = 0.0
        else:
            agent_commission = _to_float(row.get("agent_commission", 0))
            cleaning_fee = _to_float(row.get("cleaning_fee", 0))
        owner_net = gross - agent_commission - cleaning_fee

        unit_id = str(row.get("unit_id") or "Unknown").strip() or "Unknown"
        caretaker = normalize_caretaker_name(row.get("caretaker"))


        # Cash collected directly by the caretaker (matches the "N" column in the
        # legacy 2025.xlsx ledger): the reservation deposit and/or balance payment
        # when routed through her instead of GCash/BDO.
        payment_method = normalize_caretaker_name(row.get("payment_method")) if row.get("payment_method") else ""
        balance_payment_method = normalize_caretaker_name(row.get("balance_payment_method")) if row.get("balance_payment_method") else ""
        cash_collected = 0.0
        if payment_method == caretaker:
            cash_collected += _to_float(row.get("reservation_fee", 0))
        if balance_payment_method == caretaker:
            cash_collected += _to_float(row.get("paid_balance", 0))

        monthly.setdefault(key, {
            "month": key,
            "bookings": 0,
            "gross_revenue": 0.0,
            "agent_commission": 0.0,
            "cleaning_fee": 0.0,
            "owner_net": 0.0,
            "net_income": 0.0,
        })
        monthly[key]["bookings"] += 1
        monthly[key]["gross_revenue"] += gross
        monthly[key]["agent_commission"] += agent_commission
        monthly[key]["cleaning_fee"] += cleaning_fee
        monthly[key]["owner_net"] += owner_net
        monthly[key]["net_income"] += owner_net

        per_unit.setdefault(unit_id, {
            "unit_id": unit_id,
            "bookings": 0,
            "gross_revenue": 0.0,
            "owner_net": 0.0,
            "net_income": 0.0,
        })
        per_unit[unit_id]["bookings"] += 1
        per_unit[unit_id]["gross_revenue"] += gross
        per_unit[unit_id]["owner_net"] += owner_net
        per_unit[unit_id]["net_income"] += owner_net

        receivables.setdefault(caretaker, {
            "caretaker": caretaker,
            "bookings": 0,
            "cleaning_fee_owed": 0.0,
            "cash_collected": 0.0,
            "total_receivable": 0.0,
        })
        receivables[caretaker]["bookings"] += 1
        receivables[caretaker]["cleaning_fee_owed"] += cleaning_fee
        receivables[caretaker]["cash_collected"] += cash_collected
        # Receivable from caretaker = cash she collected on the owner's behalf,
        # net of the cleaning fee owed to her (mirrors the xlsx Q column: N + O + P).
        receivables[caretaker]["total_receivable"] += cash_collected - cleaning_fee

        bookings_detail.append({
            "booking_id": row.get("booking_id", ""),
            "unit_id": unit_id,
            "check_in": row.get("check_in", ""),
            "check_out": row.get("check_out", ""),
            "agent_name": row.get("agent_name", ""),
            "gross_revenue": gross,
            "cleaning_fee": cleaning_fee,
            "agent_commission": agent_commission,
            "owner_net": owner_net,
            "reservation_fee": _to_float(row.get("reservation_fee", 0)),
            "payment_method": row.get("payment_method", ""),
            "paid_balance": _to_float(row.get("paid_balance", 0)),
            "balance_payment_method": row.get("balance_payment_method", ""),
        })

    return {
        "monthly": sorted(monthly.values(), key=lambda x: x["month"]),
        "per_unit": sorted(per_unit.values(), key=lambda x: x["unit_id"]),
        "receivables": sorted(receivables.values(), key=lambda x: x["caretaker"]),
        "bookings": sorted(bookings_detail, key=lambda x: str(x["check_in"]), reverse=True),
    }


def get_analytics(last_n_months: int = 12) -> dict:
    """Compute monthly, per-unit, and caretaker receivable aggregates from the Bookings worksheet."""
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

    try:
        bookings_ws = spreadsheet.worksheet("Bookings")
    except Exception:
        bookings_ws = spreadsheet.get_worksheet(0)

    records = []
    try:
        records = bookings_ws.get_all_records()
    except Exception:
        records = []

    records = _auto_settle_overdue_balances(records)

    summary = build_analytics_summary(records)

    now = datetime.utcnow()
    months_list = []
    for i in range(last_n_months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y:04d}-{m:02d}"
        stats = next((item for item in summary["monthly"] if item["month"] == key), {
            "month": key,
            "bookings": 0,
            "gross_revenue": 0.0,
            "agent_commission": 0.0,
            "cleaning_fee": 0.0,
            "owner_net": 0.0,
        })
        months_list.append(stats)

    history = []
    try:
        analytics_ws = spreadsheet.worksheet("Analytics")
        vals = analytics_ws.get_all_records()
        history = vals
    except Exception:
        history = []

    return {
        "monthly": months_list,
        "per_unit": summary["per_unit"],
        "receivables": summary["receivables"],
        "bookings": summary["bookings"],
        "history": history,
    }


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

    records = []
    try:
        values = ws.get_all_values()
        if not values or len(values) == 0:
            return []
        headers = [c.strip() for c in values[0]]
        data_rows = values[1:]
        for row in data_rows:
            record = {headers[i] if i < len(headers) else f"col_{i}": (row[i] if i < len(row) else "") for i in range(len(headers))}
            records.append(record)
    except Exception:
        return []

    try:
        bookings = get_all_bookings()
        booking_lookup = {str(b.get("booking_id", "")).strip(): b for b in bookings}
    except Exception:
        booking_lookup = {}
    for record in records:
        booking = booking_lookup.get(str(record.get("booking_id", "")).strip(), {})
        record["unit_id"] = booking.get("unit_id", "")
        record["check_in"] = booking.get("check_in", "")
        record["check_out"] = booking.get("check_out", "")

    return records


def update_agent_payroll_status(booking_ids: list[str], new_status: str) -> int:
    """Bulk-update the status column for rows matching the given booking_ids in 'Agent Payroll'.

    Returns the number of rows updated.
    """
    if not booking_ids:
        return 0
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
        return 0

    try:
        values = ws.get_all_values()
        if not values:
            return 0
        headers = [h.strip() for h in values[0]]
        if "booking_id" not in headers or "status" not in headers:
            return 0
        id_idx = headers.index("booking_id")
        status_idx = headers.index("status")
        wanted = set(booking_ids)

        updates = []
        for i, row in enumerate(values[1:], start=2):
            if len(row) > id_idx and row[id_idx] in wanted:
                cell = gspread.utils.rowcol_to_a1(i, status_idx + 1)
                updates.append({"range": cell, "values": [[new_status]]})

        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
        return len(updates)
    except Exception:
        return 0


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
