import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
from datetime import date
import random

# ------------------ SETTINGS ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# Name of the pre-created Google Sheet
sheet_name = "Team Management Data"

# ------------------ GOOGLE SHEETS ------------------
def get_gsheet_client():
    if "gcp_service_account" in st.secrets:
        try:
            sa_info = st.secrets["gcp_service_account"]
            if isinstance(sa_info, str):
                sa_info = json.loads(sa_info)
            creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
            client = gspread.authorize(creds)
            return client
        except Exception as e:
            st.error(f"Failed to authorize using Streamlit Secrets: {e}")
            st.stop()
    else:
        st.error("Google Sheets credentials not found in Streamlit Secrets!")
        st.stop()

def ensure_worksheet(ws_list, sh, worksheet_name, headers):
    """Ensure worksheet exists, create with headers if missing or empty."""
    try:
        ws = sh.worksheet(worksheet_name)
        # Add headers if empty
        if ws.row_count == 0:
            ws.append_row(headers)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows="100", cols="20")
        ws.append_row(headers)
    ws_list[worksheet_name] = ws
    return ws

def load_sheet_df(ws):
    try:
        df = pd.DataFrame(ws.get_all_records())
    except Exception:
        df = pd.DataFrame()
    return df

def save_sheet(ws, df):
    try:
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"Failed to update sheet: {e}")

# ------------------ SESSION STATE ------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "history" not in st.session_state:
    st.session_state.history = []

# ------------------ AUTH ------------------
def admin_login():
    with st.sidebar.form("login_form"):
        st.write("### Admin Login")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if user == ADMIN_USER and pwd == ADMIN_PASS:
                st.session_state.logged_in = True
                st.success("Logged in as admin")
            else:
                st.error("Invalid credentials")

if not st.session_state.logged_in:
    admin_login()

# ------------------ APP ------------------
st.title("Fair Vehicle Selector")

# Get Google Sheets client and open pre-created sheet
client = get_gsheet_client()
try:
    sh = client.open(sheet_name)
except gspread.SpreadsheetNotFound:
    st.error(f"Spreadsheet '{sheet_name}' not found. Make sure it exists and is shared with the service account.")
    st.stop()

# Ensure worksheets exist
worksheets = {}
players_ws = ensure_worksheet(worksheets, sh, "Players", headers=["Player"])
vehicles_ws = ensure_worksheet(worksheets, sh, "Vehicles", headers=["Vehicle"])
groups_ws = ensure_worksheet(worksheets, sh, "VehicleGroups", headers=["Vehicle","Players"])
history_ws = ensure_worksheet(worksheets, sh, "History", headers=["Date","Players","Vehicles"])

# Load dataframes
players_df = load_sheet_df(players_ws)
vehicles_df = load_sheet_df(vehicles_ws)
groups_df = load_sheet_df(groups_ws)
history_df = load_sheet_df(history_ws)

# ------------------ PLAYER SELECTION ------------------
st.header("Select Players for Today")
player_options = players_df["Player"].tolist() if not players_df.empty else []
selected_players = st.multiselect("Select players present today", player_options)

# ------------------ VEHICLE SELECTION ------------------
st.header("Vehicle Selection")
num_vehicles = st.number_input("Number of vehicles needed", min_value=1, max_value=len(selected_players), value=1)
auto_manual = st.radio("Select vehicles automatically or manually?", ["Auto", "Manual"])

selected_vehicles = []

if auto_manual == "Auto":
    if not vehicles_df.empty:
        usage_count = {v: history_df['Vehicles'].tolist().count(v) for v in vehicles_df["Vehicle"].tolist()} if not history_df.empty else {v:0 for v in vehicles_df["Vehicle"].tolist()}
        sorted_vehicles = sorted(usage_count, key=lambda x: usage_count[x])
        for i in range(num_vehicles):
            for v in sorted_vehicles:
                group_members = []
                if not groups_df.empty:
                    group_members = groups_df[groups_df["Vehicle"]==v]["Players"].tolist()
                    group_members = [p for g in group_members for p in g.split(",")]  # flatten
                conflict = any(p in selected_players for p in group_members)
                if not conflict and v not in selected_vehicles:
                    selected_vehicles.append(v)
                    break
else:
    if not vehicles_df.empty:
        selected_vehicles = st.multiselect("Select vehicles manually", vehicles_df["Vehicle"].tolist(), default=[])

# ------------------ UNDO LAST ENTRY ------------------
if st.button("Undo Last Entry"):
    if not history_df.empty:
        history_df = history_df.iloc[:-1]
        save_sheet(history_ws, history_df)
        st.success("Last entry undone!")
    else:
        st.warning("No history to undo")

# ------------------ GENERATE MESSAGE ------------------
if st.button("Generate Match Details"):
    today = str(date.today())
    match_message = f"**Match Details**\nDate: {today}\nPlayers: {', '.join(selected_players)}\nVehicles: {', '.join(selected_vehicles)}"
    st.text_area("Ready to copy message", value=match_message, height=150)

    # Append to history
    new_entry = {"Date": today, "Players": ", ".join(selected_players), "Vehicles": ", ".join(selected_vehicles)}
    history_df = pd.concat([history_df, pd.DataFrame([new_entry])], ignore_index=True)
    save_sheet(history_ws, history_df)
    st.success("History updated!")

# ------------------ CSV Download/Upload ------------------
st.header("Backup / Restore CSV")
csv_data = history_df.to_csv(index=False).encode("utf-8")
st.download_button("Download History CSV", data=csv_data, file_name="history.csv", mime="text/csv")

uploaded_file = st.file_uploader("Upload CSV to restore history", type="csv")
if uploaded_file and st.session_state.logged_in:
    try:
        restored_df = pd.read_csv(uploaded_file)
        save_sheet(history_ws, restored_df)
        st.success("History restored from uploaded CSV")
    except Exception as e:
        st.error(f"Failed to restore CSV: {e}")
elif uploaded_file:
    st.warning("Admin login required to restore CSV")
