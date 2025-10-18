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

# ------------------ DATA LOADING ------------------
def load_sheet(sheet_name, worksheet_name="Sheet1"):
    client = get_gsheet_client()
    try:
        sh = client.open(sheet_name)
        ws = sh.worksheet(worksheet_name)
        data = pd.DataFrame(ws.get_all_records())
        return data, ws
    except Exception as e:
        st.error(f"Failed to load sheet: {e}")
        st.stop()

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
if "usage" not in st.session_state:
    st.session_state.usage = {}

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

# Load data from Google Sheet
sheet_name = "Team Management Data"
players_df, ws_players = load_sheet(sheet_name, "Players")  # superset of players
vehicles_df, ws_vehicles = load_sheet(sheet_name, "Vehicles")  # vehicles
groups_df, ws_groups = load_sheet(sheet_name, "VehicleGroups")  # vehicle groups
history_df, ws_history = load_sheet(sheet_name, "History")  # previous history

# ------------------ PLAYER SELECTION ------------------
st.header("Select Players for Today")
player_options = players_df["Player"].tolist()
selected_players = st.multiselect("Select players present today", player_options)

# ------------------ VEHICLE SELECTION ------------------
st.header("Vehicle Selection")
num_vehicles = st.number_input("Number of vehicles needed", min_value=1, max_value=len(selected_players), value=1)

auto_manual = st.radio("Select vehicles automatically or manually?", ["Auto", "Manual"])

selected_vehicles = []

if auto_manual == "Auto":
    # Simple round-robin using usage history
    usage_count = {v: history_df['Vehicles'].tolist().count(v) for v in vehicles_df["Vehicle"].tolist()}
    sorted_vehicles = sorted(usage_count, key=lambda x: usage_count[x])
    for i in range(num_vehicles):
        for v in sorted_vehicles:
            # Check group constraints
            group_members = groups_df[groups_df["Vehicle"]==v]["Players"].tolist()
            conflict = any(p in selected_players for p in group_members)
            if not conflict:
                selected_vehicles.append(v)
                break
else:
    selected_vehicles = st.multiselect("Select vehicles manually", vehicles_df["Vehicle"].tolist(), default=[])

# ------------------ UNDO LAST ENTRY ------------------
if st.button("Undo Last Entry"):
    if not history_df.empty:
        last_row = history_df.iloc[-1]
        history_df = history_df.iloc[:-1]
        save_sheet(ws_history, history_df)
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
    save_sheet(ws_history, history_df)
    st.success("History updated!")

# ------------------ CSV Download/Upload ------------------
st.header("Backup / Restore CSV")
csv_data = history_df.to_csv(index=False).encode("utf-8")
st.download_button("Download History CSV", data=csv_data, file_name="history.csv", mime="text/csv")

uploaded_file = st.file_uploader("Upload CSV to restore history", type="csv")
if uploaded_file and st.session_state.logged_in:
    try:
        restored_df = pd.read_csv(uploaded_file)
        save_sheet(ws_history, restored_df)
        st.success("History restored from uploaded CSV")
    except Exception as e:
        st.error(f"Failed to restore CSV: {e}")
elif uploaded_file:
    st.warning("Admin login required to restore CSV")

# ------------------ END OF APP ------------------
