# Lakeview Staycation - Google Sheets setup

This project can append bookings to a Google Sheet via a service account.

Setup

1. Enable the Google Sheets and Drive APIs in the Google Cloud Console.
2. Create a service account and generate a JSON key. Download the key file.
3. Set `GOOGLE_APPLICATION_CREDENTIALS` to the path of the JSON key, or place the file as `credentials.json` in the project root.
4. (Optional) Set `SPREADSHEET_NAME` to the desired sheet name. Default: `Tagaytay_Lakeview_Staycation_Accounting_2026`.
5. You can set `SPREADSHEET_ID` to the sheet ID (recommended when you already created the sheet). To extract the ID from a sheet URL like:

```
https://docs.google.com/spreadsheets/d/1BGaaSRTCmdV2l-4HNvUoO5ML5XJJJUbx75Tcw_MgVJI/edit?usp=sharing
```

the ID is `1BGaaSRTCmdV2l-4HNvUoO5ML5XJJJUbx75Tcw_MgVJI`. Set `SPREADSHEET_ID` to that value, or set `SPREADSHEET_NAME` to the same URL — the code will attempt to extract the ID automatically.

6. (Optional) Set `GOOGLE_SHEET_OWNER_EMAIL` to an email address to auto-share the created spreadsheet with your account.

Install dependencies

```bash
pip install -r requirements.txt
```

Usage

- The `append_booking` function in `services/sheets_engine.py` will open or create the configured spreadsheet and append a row for each booking.
- If the spreadsheet is created by the service account, it will be created in the service account's Drive; set `GOOGLE_SHEET_OWNER_EMAIL` to your personal email to grant access.

Authentication

- The `POST /api/bookings/create` endpoint requires HTTP Basic authentication (default `admin`/`admin`).
- The `GET /api/bookings` endpoint is public so the dashboard calendar can load bookings without credentials. Override POST auth by setting `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables.

Worksheet tabs created/used

- `Bookings`: all booking rows with full details
- `Agent Payroll`: per-booking agent commission entries
- `Caretaker Ledger`: per-booking caretaker cleaning fees
- `Analytics`: periodic summary rows with aggregated totals

Notes

- If you prefer to create the sheet manually in your Drive, create it with the same name and share edit access with the service account email (found in the JSON key) so the service account can append rows.
