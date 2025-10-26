import gspread

def get_or_create_financial_ws(client):
    SHEET_NAME = "Team Financial Data"
    try:
        sh = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = client.create(SHEET_NAME)
    try:
        ws = sh.worksheet("Financial")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("Financial", rows=100, cols=20)
        ws.append_row(["Player Name", "Deposit"])
    return ws

def safe_get_financial_records(ws):
    try:
        return ws.get_all_records()
    except Exception as e:
        return []
