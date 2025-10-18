import streamlit as st
import json
import os
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
# Constants
# -----------------------------
HISTORY_FILE = "vehicle_history.json"
CSV_FILE = "vehicle_history.csv"

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

def push_to_google_sheet(players, vehicles, vehicle_groups, history):
    client = get_gsheet_client()
    if not client:
        st.warning("Google Sheets client not available")
        return
    try:
        sh = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = client.create(SHEET_NAME)
    # Players
    try:
        ws = sh.worksheet("Players")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("Players", rows=100, cols=20)
    ws.update([["Player"]] + [[p] for p in players])
    # Vehicles
    try:
        ws = sh.worksheet("Vehicles")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("Vehicles", rows=100, cols=20)
    ws.update([["Vehicle"]] + [[v] for v in vehicles])
    # Vehicle Groups
    try:
        ws = sh.worksheet("VehicleGroups")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("VehicleGroups", rows=100, cols=20)
    groups_list = [[k, ", ".join(v)] for k,v in vehicle_groups.items()]
    ws.update([["Vehicle","Players"]]+groups_list)
    # History
    try:
        ws = sh.worksheet("History")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("History", rows=100, cols=20)
    hist_list = []
    for h in history:
        hist_list.append([h.get("date",""), h.get("ground",""), ", ".join(h.get("players_present",[])), ", ".join(h.get("selected_vehicles",[])), h.get("message","")])
    ws.update([["Date","Ground","Players","Vehicles","Message"]]+hist_list)
    st.success("✅ All data pushed to Google Sheets")

def download_from_google_sheet():
    client = get_gsheet_client()
    if not client:
        st.warning("Google Sheets client not available")
        return None
    try:
        sh = client.open(SHEET_NAME)
        data = {}
        for ws_name in ["Players","Vehicles","VehicleGroups","History"]:
            try:
                ws = sh.worksheet(ws_name)
                records = ws.get_all_records()
                data[ws_name] = records
            except:
                data[ws_name] = []
        return data
    except Exception as e:
        st.warning(f"Failed to download: {e}")
        return None

def reset_google_sheet():
    client = get_gsheet_client()
    if not client:
        st.warning("Google Sheets client not available")
        return
    try:
        sh = client.open(SHEET_NAME)
        for ws_name in ["Players","Vehicles","VehicleGroups","History"]:
            try:
                ws = sh.worksheet(ws_name)
                ws.clear()
            except:
                continue
        st.success("✅ Google Sheet reset successfully")
    except Exception as e:
        st.warning(f"Failed to reset Google Sheet: {e}")

def load_from_google_sheet():
    data = download_from_google_sheet()
    if not data:
        st.warning("No data found on Google Sheet")
        return [], [], {}, [], {}
    players = [p["Player"] for p in data.get("Players",[])]
    vehicles = [v["Vehicle"] for v in data.get("Vehicles",[])]
    vehicle_groups = {g["Vehicle"]: g["Players"].split(", ") for g in data.get("VehicleGroups",[])}
    history = data.get("History", [])
    usage = {}
    for record in history:
        for p in record.get("players_present",[]):
            if p not in usage:
                usage[p] = {"used":0,"present":0}
            usage[p]["present"] +=1
        for v in record.get("selected_vehicles",[]):
            if v not in usage:
                usage[v] = {"used":0,"present":0}
            usage[v]["used"] +=1
    st.success("✅ Data loaded from Google Sheet")
    return players, vehicles, vehicle_groups, history, usage

# -----------------------------
# Local JSON Persistence
# -----------------------------
def load_data():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        players = data.get("players", [])
        vehicles = data.get("vehicles", [])
        history = data.get("history", [])
        usage = data.get("usage", {})
        vehicle_groups = data.get("vehicle_groups", {})
        return players, vehicles, history, usage, vehicle_groups
    return [], [], [], {}, {}

def save_data(players, vehicles, history, usage, vehicle_groups):
    data = {
        "players": players,
        "vehicles": vehicles,
        "history": history,
        "usage": usage,
        "vehicle_groups": vehicle_groups
    }
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=4)
    save_csv(history)

def save_csv(history):
    if history:
        df = pd.DataFrame(history)
        df.to_csv(CSV_FILE, index=False)

# -----------------------------
# Vehicle Selection Logic
# -----------------------------
def update_usage(selected_players, eligible_players, usage):
    for p in selected_players:
        if p not in usage:
            usage[p] = {"used":0,"present":0}
        usage[p]["used"] += 1
    for p in eligible_players:
        if p not in usage:
            usage[p] = {"used":0,"present":0}
        usage[p]["present"] +=1

def select_vehicles_auto(vehicle_set, players_today, num_needed, usage, vehicle_groups):
    selected = []
    eligible = [v for v in players_today if v in vehicle_set]
    for _ in range(num_needed):
        if not eligible:
            break
        def usage_ratio(p):
            u = usage.get(p, {"used":0,"present":0})
            return u["used"]/u["present"] if u["present"]>0 else 0
        ordered = sorted(eligible, key=lambda p: (usage_ratio(p), vehicle_set.index(p)))
        pick = ordered[0]
        selected.append(pick)
        update_usage([pick], eligible, usage)
        for members in vehicle_groups.values():
            if pick in members:
                eligible = [e for e in eligible if e not in members]
                break
        else:
            eligible.remove(pick)
    return selected

def generate_message(game_date, ground_name, players, selected):
    message = (
        f"🏏 Match Details\n"
        f"📅 Date: {game_date}\n"
        f"📍 Venue: {ground_name}\n\n"
        f"👥 Team:\n" + "\n".join([f"- {p}" for p in players]) + "\n\n"
        f"🚗 Vehicles:\n" + "\n".join([f"- {v}" for v in selected])
    )
    return message

def undo_last_entry(history, usage):
    if not history or not isinstance(history, list):
        return history, usage, False
    last = history.pop()
    for v in last.get("selected_vehicles", []):
        if v in usage and usage[v]["used"]>0:
            usage[v]["used"] -=1
    for v in last.get("players_present", []):
        if v in usage and usage[v]["present"]>0:
            usage[v]["present"] -=1
    return history, usage, True

# -----------------------------
# Admin Login
# -----------------------------
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

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

# -----------------------------
# Load Data
# -----------------------------
players, vehicles, history, usage, vehicle_groups = load_data()

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with admin control and vehicle grouping")

# -----------------------------
# Sidebar Admin Controls
# -----------------------------
if st.session_state.admin_logged_in:
    st.sidebar.header("⚙️ Admin Controls")
    
    if st.sidebar.button("🧹 Reset All Data"):
        players, vehicles, history, usage, vehicle_groups = [], [], [], {}, {}
        save_data(players, vehicles, history, usage, vehicle_groups)
        st.sidebar.success("✅ All data reset")

    if st.sidebar.button("↩ Undo Last Entry"):
        history, usage, undone = undo_last_entry(history, usage)
        save_data(players, vehicles, history, usage, vehicle_groups)
        if undone:
            st.sidebar.success("✅ Last entry removed")
        else:
            st.sidebar.info("ℹ️ No record to undo")

    # Google Sheets integration
    st.sidebar.header("📂 Google Sheets & Backup")
    if st.sidebar.button("💾 Push All Data to Google Sheets"):
        push_to_google_sheet(players, vehicles, vehicle_groups, history)
    if st.sidebar.button("📥 Download All Data from Google Sheets"):
        data = download_from_google_sheet()
        if data:
            st.sidebar.download_button("Download JSON Backup", json.dumps(data, indent=4), "backup.json", "application/json")
    upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
    if upload_file:
        data = json.load(upload_file)
        players = [p["Player"] for p in data.get("Players",[])]
        vehicles = [v["Vehicle"] for v in data.get("Vehicles",[])]
        vehicle_groups = {g["Vehicle"]: g["Players"].split(", ") for g in data.get("VehicleGroups",[])}
        history = data.get("History",[])
        usage = {}
        for record in history:
            for p in record.get("players_present",[]):
                if p not in usage:
                    usage[p] = {"used":0,"present":0}
                usage[p]["present"] +=1
            for v in record.get("selected_vehicles",[]):
                if v not in usage:
                    usage[v] = {"used":0,"present":0}
                usage[v]["used"] +=1
        save_data(players, vehicles, history, usage, vehicle_groups)
        st.sidebar.success("✅ Data restored from backup JSON")
    if st.sidebar.button("🗑 Reset Google Sheet"):
        reset_google_sheet()
    if st.sidebar.button("🔄 Load Data from Google Sheet"):
        players, vehicles, vehicle_groups, history, usage = load_from_google_sheet()

# -----------------------------
# Main UI: Players, Vehicles, Groups, Daily Match Selection, CSV, Usage, Records
# -----------------------------
# Copy your previous working code for these sections here.
# Players Superset, Vehicle Set, Vehicle Groups, Daily Match Selection,
# Download CSV, Vehicle Usage Table & Chart, Recent Match Records
# — all remain exactly as in your working original app.
