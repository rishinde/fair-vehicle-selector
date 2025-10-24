import streamlit as st
import json
from datetime import date
import pandas as pd
import plotly.express as px

# Optional Google Sheets integration
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except:
    GOOGLE_SHEETS_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Team Management Data"

# -----------------------------
# Google Sheets Helper Functions
# -----------------------------
def get_gsheet_client():
    if not GOOGLE_SHEETS_AVAILABLE:
        return None
    try:
        if "gcp_service_account" in st.secrets:
            sa_info = st.secrets["gcp_service_account"]
            if isinstance(sa_info, str):
                sa_info = json.loads(sa_info)
            creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
            client = gspread.authorize(creds)
            return client
        else:
            return None
    except Exception as e:
        st.warning(f"Failed to authorize Google Sheets: {e}")
        return None

# Load sheet and worksheets (without caching unhashable objects)
def load_gsheet_data(client):
    try:
        sheet_list = [s['name'] for s in client.list_spreadsheet_files()] if hasattr(client, 'list_spreadsheet_files') else []
        sh = client.open(SHEET_NAME) if SHEET_NAME in sheet_list else client.create(SHEET_NAME)

        def get_or_create_ws(name, headers):
            try:
                ws = sh.worksheet(name)
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(name, rows=100, cols=20)
                ws.append_row(headers)
            return ws

        ws_players = get_or_create_ws("Players", ["Player"])
        ws_vehicles = get_or_create_ws("Vehicles", ["Vehicle"])
        ws_groups = get_or_create_ws("VehicleGroups", ["Vehicle","Players"])
        ws_history = get_or_create_ws("History", ["Date","Ground","Players","Vehicles","Message"])

        players = [r["Player"] for r in ws_players.get_all_records()] if ws_players else []
        vehicles = [r["Vehicle"] for r in ws_vehicles.get_all_records()] if ws_vehicles else []
        vehicle_groups = {r["Vehicle"]: r["Players"].split(", ") for r in ws_groups.get_all_records()} if ws_groups else {}
        history_records = ws_history.get_all_records() if ws_history else []

        usage = {}
        for record in history_records:
            for p in record.get("Players","").split(", "):
                if p not in usage:
                    usage[p] = {"used":0,"present":0}
                usage[p]["present"] += 1
            for v in record.get("Vehicles","").split(", "):
                if v not in usage:
                    usage[v] = {"used":0,"present":0}
                usage[v]["used"] += 1
        
        return ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history_records, usage
    except Exception as e:
        st.error(f"Failed to open or create spreadsheet: {e}")
        return None, None, None, None, [], [], {}, [], {}

# -----------------------------
# Incremental update functions
# -----------------------------
def append_history(ws_history, record):
    try:
        row = [record.get("date",""), record.get("ground",""), ", ".join(record.get("players_present",[])), ", ".join(record.get("selected_vehicles",[])), record.get("message","")]
        ws_history.append_row(row)
    except Exception as e:
        st.error(f"Failed to append history: {e}")

def add_player(ws_players, player, players_list):
    try:
        if player and player not in players_list:
            ws_players.append_row([player])
            players_list.append(player)
    except Exception as e:
        st.error(f"Failed to add player '{player}': {e}")

def add_vehicle(ws_vehicles, vehicle, vehicles_list):
    try:
        if vehicle and vehicle not in vehicles_list:
            ws_vehicles.append_row([vehicle])
            vehicles_list.append(vehicle)
    except Exception as e:
        st.error(f"Failed to add vehicle '{vehicle}': {e}")

def update_vehicle_group(ws_groups, vehicle, members):
    try:
        all_records = ws_groups.get_all_records()
        for idx, r in enumerate(all_records, start=2):
            if r["Vehicle"]==vehicle:
                ws_groups.delete_row(idx)
                break
        ws_groups.append_row([vehicle, ", ".join(members)])
    except Exception as e:
        st.error(f"Failed to update vehicle group '{vehicle}': {e}")

def append_history_safe(ws_history, record):
    try:
        append_history(ws_history, record)
    except Exception as e:
        st.error(f"Failed to append history: {e}")

# -----------------------------
# Reset Data with automatic backup
# -----------------------------
def reset_all_data_with_backup(ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history):
    try:
        backup_data = {
            "Players":[{"Player":p} for p in players],
            "Vehicles":[{"Vehicle":v} for v in vehicles],
            "VehicleGroups":[{"Vehicle":k,"Players":", ".join(v)} for k,v in vehicle_groups.items()],
            "History":history
        }
        st.sidebar.download_button(
            "📥 Download Backup Before Reset",
            json.dumps(backup_data, indent=4),
            file_name=f"backup_before_reset_{date.today()}.json",
            mime="application/json"
        )
        for ws in [ws_players, ws_vehicles, ws_groups, ws_history]:
            ws.clear()
            ws.append_row(ws.get_all_values()[0]) if ws.get_all_values() else None
        st.sidebar.success("✅ All data reset")
    except Exception as e:
        st.sidebar.error(f"Failed to reset data: {e}")

# -----------------------------
# Vehicle selection logic
# -----------------------------
def generate_message(game_date, ground_name, players, selected):
    return f"📅 {game_date}\n📍 {ground_name}\n👥 Players: {', '.join(players)}\n🚗 Vehicles: {', '.join(selected)}"

# -----------------------------
# Admin Login
# -----------------------------
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with admin control and vehicle grouping")

client = get_gsheet_client()
if client:
    ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = load_gsheet_data(client)
else:
    st.warning("⚠️ Google Sheets not available. Admin operations disabled.")
    players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}

# -----------------------------
# Sidebar Admin Controls
# -----------------------------
if not st.session_state.admin_logged_in:
    st.subheader("🔒 Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username=="admin" and password=="admin123":
            st.session_state.admin_logged_in = True
            st.success("✅ Logged in as Admin")
        else:
            st.error("❌ Incorrect username or password")

if st.session_state.admin_logged_in and client:
    st.sidebar.header("⚙️ Admin Controls")

    if st.sidebar.button("🧹 Reset All Data"):
        reset_all_data_with_backup(ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history)

    st.sidebar.header("💾 Save Changes")
    if st.sidebar.button("Save Current State to Google Sheet"):
        try:
            for p in players:
                add_player(ws_players, p, [])
            for v in vehicles:
                add_vehicle(ws_vehicles, v, [])
            for vg, members in vehicle_groups.items():
                update_vehicle_group(ws_groups, vg, members)
            for h in history:
                append_history_safe(ws_history, h)
            st.sidebar.success("✅ All changes saved to Google Sheet")
        except Exception as e:
            st.sidebar.error(f"Failed to save: {e}")

# -----------------------------
# Main UI (simplified for brevity)
# -----------------------------
st.header("1️⃣ Players")
st.write(players)
st.header("2️⃣ Vehicles")
st.write(vehicles)
st.header("3️⃣ Vehicle Groups")
st.write(vehicle_groups)
st.header("4️⃣ Daily Match Selection")
st.header("5️⃣ Match History")
st.write(history)
