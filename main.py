import os
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware

from services.calculator import process_booking
from services.sheets_engine import append_booking
from services.sheets_engine import get_all_bookings
from services.sheets_engine import get_agent_payroll
from services.sheets_engine import get_caretaker_ledger
from services.sheets_engine import get_analytics
from services.sheets_engine import update_booking
import json
from typing import Optional


app = FastAPI()
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(base_dir))

# configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_UNITS = {"635", "1931", "1127", "1228", "1230"}
ALLOWED_PAYMENT_METHODS = {"Cash", "GCash", "Bank Transfer", "PayMaya", "Other"}
ALLOWED_BALANCE_PAYMENT_METHODS = {"GCash", "Bank", "Czarina", "Tess"}

# Add CORS middleware to allow browser requests from localhost/127.0.0.1 during development
app.add_middleware(
    CORSMiddleware,
    # For local development allow all origins to avoid CORS issues in varied browser environments
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    expected_username = os.getenv("ADMIN_USERNAME", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "admin")

    if credentials.username != expected_username or credentials.password != expected_password:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials


def _load_employee_keys() -> dict:
    """Load employee API keys mapping from employee_keys.json or EMPLOYEE_KEYS env var.

    File format (employee_keys.json): {"key1":"Alice", "key2":"Bob"}
    Env format (EMPLOYEE_KEYS): key1:Alice,key2:Bob
    """
    import os
    keys = {}
    try:
        path = os.path.join(Path(__file__).resolve().parent, 'employee_keys.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                keys = json.load(f)
                return keys or {}
    except Exception:
        logger.exception('failed loading employee_keys.json')

    env = os.getenv('EMPLOYEE_KEYS')
    if env:
        try:
            for part in env.split(','):
                if not part.strip():
                    continue
                k, _, name = part.partition(':')
                keys[k.strip()] = name.strip() or k.strip()
        except Exception:
            logger.exception('failed parsing EMPLOYEE_KEYS')

    return keys


def _load_agents() -> dict:
    """Load booking-agent login credentials from agents.json.

    File format (agents.json): {"username": {"password": "...", "name": "Display Name"}}
    Agents can create/view bookings but are never treated as admin.
    """
    agents = {}
    try:
        path = os.path.join(Path(__file__).resolve().parent, 'agents.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                agents = json.load(f)
    except Exception:
        logger.exception('failed loading agents.json')
    return agents or {}


def get_actor(x_api_key: Optional[str] = Header(None), credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    """Dependency to determine caller: admin (Basic auth), agent (Basic auth), or employee (X-API-Key).

    Returns a dict with keys: type ('admin'|'employee'), name, identifier
    """
    # Try API key first
    keys = _load_employee_keys()
    if x_api_key:
        name = keys.get(x_api_key)
        if name:
            return {"type": "employee", "name": name, "key": x_api_key}
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Try admin Basic auth
    try:
        auth = authenticate(credentials)
        return {"type": "admin", "name": auth.username}
    except Exception:
        pass

    # Fall back to per-agent Basic auth credentials
    if credentials:
        agents = _load_agents()
        agent = agents.get(credentials.username)
        if agent and agent.get("password") == credentials.password:
            return {"type": "employee", "name": agent.get("name", credentials.username), "is_agent": True}

    raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


def validate_booking_input(data: dict) -> dict:
    unit_id = str(data.get("unit_id", "")).strip()
    if unit_id not in ALLOWED_UNITS:
        raise ValueError("unit_id must be one of the approved lakeview staycation units")

    try:
        check_in = datetime.strptime(data["check_in"], "%Y-%m-%d").date()
        check_out = datetime.strptime(data["check_out"], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Dates must be in YYYY-MM-DD format") from exc

    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")

    amount = float(data["amount"])
    parking_fee = float(data.get("parking_fee", 0) or 0)
    if amount < 0 or parking_fee < 0:
        raise ValueError("amount and parking_fee must be non-negative")

    reservation_fee = float(data.get("reservation_fee", 0) or 0)
    if reservation_fee < 0:
        raise ValueError("reservation_fee must be non-negative")

    payment_method = str(data.get("payment_method", "")).strip()
    if payment_method and payment_method not in ALLOWED_PAYMENT_METHODS:
        raise ValueError(f"payment_method must be one of {sorted(ALLOWED_PAYMENT_METHODS)}")

    agent_name = str(data.get("agent_name", "")).strip()
    if len(agent_name) > 100:
        raise ValueError("agent_name is too long")

    balance = data.get("balance")
    balance = float(balance) if balance not in (None, "") else None

    return {
        "unit_id": unit_id,
        "check_in": data["check_in"],
        "check_out": data["check_out"],
        "amount": amount,
        "parking_fee": parking_fee,
        "agent_name": agent_name,
        "reservation_fee": reservation_fee,
        "payment_method": payment_method,
        "balance": balance,
    }


@app.get("/")
def home(request: Request):
    # pass allowed units to the template for the calendar dropdown
    try:
        units = sorted(list(ALLOWED_UNITS))
    except Exception:
        units = []
    return templates.TemplateResponse(request=request, name="index.html", context={"allowed_units": units})


@app.get("/api/bookings")
def list_bookings(unit: str | None = None):
    try:
        logger.info(f"list_bookings called unit={unit}")
        records = get_all_bookings(unit_id=unit)
        return JSONResponse(status_code=200, content={"bookings": records}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception:
        # return an error to help client debugging
        logger.exception('list_bookings failed')
        return JSONResponse(status_code=500, content={"bookings": [], "error": "internal server error"}, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/health")
def health():
    return JSONResponse(status_code=200, content={"status": "ok"}, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/whoami")
def whoami(actor: dict = Depends(get_actor)):
    return JSONResponse(status_code=200, content={"type": actor.get("type"), "name": actor.get("name"), "is_agent": bool(actor.get("is_agent"))}, headers={"Access-Control-Allow-Origin": "*"})


@app.post("/api/change_password")
def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
):
    # Only agents stored in agents.json (Basic-auth logins) can self-service their password here;
    # the admin password is managed via the ADMIN_PASSWORD environment variable, not this file.
    if not credentials:
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})

    if credentials.username == os.getenv("ADMIN_USERNAME", "admin"):
        raise HTTPException(status_code=400, detail="Admin password is managed via environment variables and cannot be changed here")

    agents = _load_agents()
    agent = agents.get(credentials.username)
    if not agent or agent.get("password") != credentials.password or credentials.password != current_password:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    agent["password"] = new_password
    agents[credentials.username] = agent
    try:
        path = os.path.join(Path(__file__).resolve().parent, 'agents.json')
        with open(path, 'w') as f:
            json.dump(agents, f, indent=2)
    except Exception:
        logger.exception('failed saving agents.json')
        raise HTTPException(status_code=500, detail="Failed to save new password")

    return JSONResponse(status_code=200, content={"message": "Password updated"}, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/agent_payroll")
def agent_payroll(actor: dict = Depends(get_actor)):
    # admin sees everyone; a booking agent may only see rows matching their own name
    if actor.get('type') != 'admin' and not actor.get('is_agent'):
        raise HTTPException(status_code=403, detail="forbidden: admin only")
    try:
        rows = get_agent_payroll()
        if actor.get('type') != 'admin' and actor.get('is_agent'):
            own_name = str(actor.get('name', '')).strip().lower()
            rows = [r for r in rows if str(r.get('agent_name', '')).strip().lower() == own_name]
        return JSONResponse(status_code=200, content={"payroll": rows}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception:
        logger.exception('agent_payroll failed')
        return JSONResponse(status_code=500, content={"payroll": [], "error": "internal server error"}, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/caretaker_ledger")
def caretaker_ledger(actor: dict = Depends(get_actor)):
    # only admin is allowed to view caretaker ledger
    if actor.get('type') != 'admin':
        raise HTTPException(status_code=403, detail="forbidden: admin only")
    try:
        rows = get_caretaker_ledger()
        return JSONResponse(status_code=200, content={"caretaker_ledger": rows}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception:
        logger.exception('caretaker_ledger failed')
        return JSONResponse(status_code=500, content={"caretaker_ledger": [], "error": "internal server error"}, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/analytics")
def analytics(actor: dict = Depends(get_actor)):
    # admin-only analytics
    if actor.get('type') != 'admin':
        raise HTTPException(status_code=403, detail="forbidden: admin only")
    try:
        data = get_analytics()
        return JSONResponse(status_code=200, content={"analytics": data}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception:
        logger.exception('analytics failed')
        return JSONResponse(status_code=500, content={"analytics": {}, "error": "internal server error"}, headers={"Access-Control-Allow-Origin": "*"})


def _build_booking_result(validated_data: dict) -> dict:
    """Compute derived fields (nights, commission, caretaker fee, balance, etc.) shared by create/update."""
    booking_result = process_booking(validated_data)

    booking_result["amount"] = validated_data["amount"]
    booking_result["parking_fee"] = validated_data["parking_fee"]
    booking_result["gross_revenue"] = validated_data["amount"] + validated_data["parking_fee"]
    booking_result["owner_net"] = booking_result.get("owner_net_profit", 0)
    booking_result["agent_name"] = validated_data["agent_name"]
    booking_result["reservation_fee"] = validated_data["reservation_fee"]
    booking_result["payment_method"] = validated_data["payment_method"]
    # allow the agent to override the computed balance (e.g. partial payments already settled)
    computed_balance = booking_result["gross_revenue"] - validated_data["reservation_fee"]
    booking_result["balance"] = validated_data["balance"] if validated_data["balance"] is not None else computed_balance
    return booking_result


def _maybe_mark_fully_paid(booking_result: dict) -> None:
    """Force status to 'Fully Paid' once the remaining balance reaches zero (or less)."""
    try:
        balance_value = float(booking_result.get("balance") or 0)
    except (TypeError, ValueError):
        return
    if balance_value <= 0:
        booking_result["status"] = "Fully Paid"


@app.post("/api/bookings/create")
def create_booking(
    unit_id: str = Form(...),
    check_in: str = Form(...),
    check_out: str = Form(...),
    amount: float = Form(...),
    parking_fee: Optional[str] = Form(None),
    agent_name: str = Form(""),
    reservation_fee: Optional[str] = Form(None),
    payment_method: str = Form(""),
    balance: Optional[str] = Form(None),
    actor: dict = Depends(get_actor),
):
    try:
        validated_data = validate_booking_input(
            {
                "unit_id": unit_id,
                "check_in": check_in,
                "check_out": check_out,
                "amount": amount,
                "parking_fee": parking_fee,
                "agent_name": agent_name,
                "reservation_fee": reservation_fee,
                "payment_method": payment_method,
                "balance": balance,
            }
        )
        booking_result = _build_booking_result(validated_data)
        booking_result["status"] = "Pending"
        _maybe_mark_fully_paid(booking_result)
        booking_result["created_at"] = datetime.utcnow().isoformat()
        # record who created this booking (employee key or admin username)
        if actor.get('type') == 'employee':
            booking_result['created_by'] = actor.get('name')
            booking_result['created_by_key'] = actor.get('key')
        else:
            booking_result['created_by'] = actor.get('name')

        append_booking(booking_result)

        return JSONResponse(
            status_code=201,
            content={
                "message": "Booking created successfully",
                "booking": booking_result,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Booking could not be created") from exc


@app.post("/api/bookings/update")
def update_booking_endpoint(
    booking_id: str = Form(...),
    unit_id: str = Form(...),
    check_in: str = Form(...),
    check_out: str = Form(...),
    amount: float = Form(...),
    parking_fee: Optional[str] = Form(None),
    agent_name: str = Form(""),
    reservation_fee: Optional[str] = Form(None),
    payment_method: str = Form(""),
    balance: Optional[str] = Form(None),
    balance_payment_method: Optional[str] = Form(None),
    paid_balance: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    actor: dict = Depends(get_actor),
):
    booking_id = booking_id.strip()
    if not booking_id:
        raise HTTPException(status_code=400, detail="booking_id is required")
    balance_payment_method = (balance_payment_method or "").strip()
    if balance_payment_method and balance_payment_method not in ALLOWED_BALANCE_PAYMENT_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"balance_payment_method must be one of {sorted(ALLOWED_BALANCE_PAYMENT_METHODS)}",
        )
    if paid_balance not in (None, ""):
        try:
            paid_balance = float(paid_balance)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="paid_balance must be a number") from exc
    else:
        paid_balance = None
    try:
        validated_data = validate_booking_input(
            {
                "unit_id": unit_id,
                "check_in": check_in,
                "check_out": check_out,
                "amount": amount,
                "parking_fee": parking_fee,
                "agent_name": agent_name,
                "reservation_fee": reservation_fee,
                "payment_method": payment_method,
                "balance": balance,
            }
        )
        booking_result = _build_booking_result(validated_data)
        booking_result["booking_id"] = booking_id
        booking_result["balance_payment_method"] = balance_payment_method
        booking_result["paid_balance"] = paid_balance if paid_balance is not None else 0
        # once the paid balance covers the remaining balance, clear the balance to zero
        if paid_balance is not None and paid_balance >= booking_result["balance"]:
            booking_result["balance"] = 0
        # status is no longer edited from this form; preserve whatever is already on the sheet
        if status and status.strip():
            booking_result["status"] = status.strip()[:100]
        _maybe_mark_fully_paid(booking_result)

        updated = update_booking(booking_id, booking_result)
        if not updated:
            raise HTTPException(status_code=404, detail="Booking not found")

        return JSONResponse(
            status_code=200,
            content={"message": "Booking updated successfully", "booking": booking_result},
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('update_booking failed')
        raise HTTPException(status_code=400, detail="Booking could not be updated") from exc

