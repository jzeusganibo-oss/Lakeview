from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def process_booking(data: dict) -> dict:
    unit_id = str(data["unit_id"])
    check_in = datetime.strptime(data["check_in"], "%Y-%m-%d").date()
    check_out = datetime.strptime(data["check_out"], "%Y-%m-%d").date()

    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")

    nights = (check_out - check_in).days

    amount = float(data["amount"])
    parking_fee = float(data["parking_fee"])

    agent_name = data.get("agent_name")
    agent_commission = 0.0
    if agent_name:
        agent_commission += 100.0
        if parking_fee > 0:
            agent_commission += 50.0

    if unit_id in {"635", "1931", "105"}:
        caretaker = "Ate Czarina"
        cleaning_fee = 500.0
    else:
        caretaker = "Ate Tess"
        cleaning_fee = 700.0

    owner_net_profit = (amount + parking_fee) - agent_commission - cleaning_fee

    booking_id = (
        f"BK-{unit_id}-{check_in.strftime('%Y%m%d')}-{check_out.strftime('%Y%m%d')}"
    )

    return {
        "booking_id": booking_id,
        "unit_id": unit_id,
        "check_in": data["check_in"],
        "check_out": data["check_out"],
        "number_of_nights": nights,
        "agent_commission": agent_commission,
        "caretaker": caretaker,
        "cleaning_fee": cleaning_fee,
        "owner_net_profit": owner_net_profit,
    }


def append_booking(booking_summary: dict):
    credentials = Credentials.from_service_account_file(
        "credentials.json",
        scopes=SCOPES,
    )
    client = gspread.authorize(credentials)

    spreadsheet = client.open("Tagaytay_Lakeview_Staycation_Accounting_2026")
    worksheet = spreadsheet.get_worksheet(0)

    row = [
        booking_summary.get("booking_id", ""),
        booking_summary.get("unit_id", ""),
        booking_summary.get("number_of_nights", ""),
        booking_summary.get("gross_revenue", ""),
        booking_summary.get("agent_name", ""),
        booking_summary.get("agent_commission", ""),
        booking_summary.get("caretaker", ""),
        booking_summary.get("cleaning_fee", ""),
        booking_summary.get("owner_net", ""),
        booking_summary.get("status", "Pending"),
    ]

    worksheet.append_row(row)
    return row


if __name__ == "__main__":
    sample_data = {
        "unit_id": "635",
        "check_in": "2026-08-10",
        "check_out": "2026-08-14",
        "amount": 5000.0,
        "parking_fee": 300.0,
        "agent_name": "Juan",
    }

    booking_result = process_booking(sample_data)
    booking_result["gross_revenue"] = sample_data["amount"] + sample_data["parking_fee"]
    booking_result["owner_net"] = booking_result["owner_net_profit"]
    booking_result["agent_name"] = sample_data["agent_name"]
    booking_result["status"] = "Pending"

    print(booking_result)
