from datetime import datetime


def process_booking(data: dict) -> dict:
    unit_id = str(data["unit_id"])
    check_in = datetime.strptime(data["check_in"], "%Y-%m-%d").date()
    check_out = datetime.strptime(data["check_out"], "%Y-%m-%d").date()

    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")

    nights = (check_out - check_in).days

    agent_name = data.get("agent_name")
    agent_commission = 300 * nights if agent_name else 0.0

    if unit_id in {"635", "1931"}:
        caretaker = "Ate Czarina"
        cleaning_fee = 500.0
    else:
        caretaker = "Ate Tess"
        cleaning_fee = 700.0

    amount = float(data["amount"])
    parking_fee = float(data["parking_fee"])

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
