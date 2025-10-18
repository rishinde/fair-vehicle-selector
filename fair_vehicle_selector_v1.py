import streamlit as st
import pandas as pd
from datetime import date
import random
import json

# Optional Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except:
    GOOGLE_SHEETS_AVAILABLE = False

# ------------------ SETTINGS ------------------
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Team Management Data"

# ------------------ SESSION STATE ------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "player_superset" not in st.session_state:
    st.session_state.player_superset = []
if "vehicle_set" not in st.session_state:
    st.session_state.vehicle_set = []
if "vehicle_groups" not in st.session_state:
    st.session_state.vehicle_groups = []  # list of lists
if "history" not in st.session_state:
    st.session_state.history = []

# ------------------ GOOGLE SHEETS FUNCTIONS ------------------
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

def save_sheet_df(sheet, worksheet_name, df):
    client = get_gsheet_client()
    if client:
        try:
            sh = client.open(sheet)
            try:
                ws = sh.worksheet(worksheet_name)
                ws.clear()
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=worksheet_name, rows="100", cols="20")
            ws.update([df.columns.tolist()] + df.values.tolist())
        except Exception as e:
            st.warning(f"Cannot save to sheet: {e}")

def load_sheet_df(sheet, worksheet_name, headers):
    client = get_gsheet_client()
    if client:
        try:
            sh = client.open(sheet)
            try:
                ws = sh.worksheet(worksheet_name)
                df = pd.DataFrame(ws.get_all_records())
                return df
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=worksheet_name, rows="100", cols="20")
                ws.append_row(headers)
                return pd.DataFrame(columns=headers)
        except Exception as e:
            st.warning(f"Cannot load sheet: {e}")
            return pd.DataFrame(columns=headers)
    else:
        return pd.DataFrame(columns=headers)

# ------------------ ADMIN LOGIN ------------------
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

# Sidebar
st.sidebar.title("Actions")
if not st.session_state.logged_in:
    admin_login()
else:
    if st.sidebar.button("Undo Last Entry"):
        if st.session_state.history:
            st.session_state.history.pop()
    if st.sidebar.button("Reset All"):
        st.session_state.player_superset = []
        st.session_state.vehicle_set = []
        st.session_state.vehicle_groups = []
        st.session_state.history = []

# ------------------ APP UI ------------------
st.title("Fair Vehicle Selector")

# ------------------ PLAYER / VEHICLE / GROUP MANAGEMENT ------------------
st.header("Manage Data")
if st.session_state.logged_in:
    # Player Superset
    with st.expander("Player Superset"):
        new_player = st.text_input("Add Player")
        remove_player = st.selectbox("Remove Player", st.session_state.player_superset + [""])
        if st.button("Add Player"):
            if new_player and new_player not in st.session_state.player_superset:
                st.session_state.player_superset.append(new_player)
        if st.button("Remove Player") and remove_player:
            if remove_player in st.session_state.player_superset:
                st.session_state.player_superset.remove(remove_player)
        st.write(st.session_state.player_superset)

    # Vehicle Set
    with st.expander("Vehicle Set"):
        add_vehicle = st.selectbox("Add Vehicle", [p for p in st.session_state.player_superset if p not in st.session_state.vehicle_set] + [""])
        remove_vehicle = st.selectbox("Remove Vehicle", st.session_state.vehicle_set + [""])
        if st.button("Add Vehicle") and add_vehicle:
            st.session_state.vehicle_set.append(add_vehicle)
        if st.button("Remove Vehicle") and remove_vehicle:
            st.session_state.vehicle_set.remove(remove_vehicle)
        st.write(st.session_state.vehicle_set)

    # Vehicle Groups
    with st.expander("Vehicle Groups"):
        group_input = st.text_input("Enter player names separated by comma for group")
        remove_group = st.selectbox("Remove Group", [" , ".join(g) for g in st.session_state.vehicle_groups] + [""])
        if st.button("Add Group") and group_input:
            group = [p.strip() for p in group_input.split(",") if p.strip()]
            if group:
                st.session_state.vehicle_groups.append(group)
        if st.button("Remove Group") and remove_group:
            idx = [" , ".join(g) for g in st.session_state.vehicle_groups].index(remove_group)
            st.session_state.vehicle_groups.pop(idx)
        st.write(st.session_state.vehicle_groups)

# ------------------ MATCH DETAILS ------------------
st.header("Match Details")
match_date = st.date_input("Date", value=date.today())
venue = st.text_input("Venue")
selected_players = st.multiselect("Select players for match", st.session_state.player_superset)

if selected_players:
    num_vehicles = st.number_input(
        "Number of vehicles needed",
        min_value=1,
        max_value=len(selected_players),
        value=1
    )
else:
    st.info("Select at least one player to choose vehicles")
    num_vehicles = 0

auto_manual = st.radio("Vehicle selection method", ["Auto", "Manual"])
selected_vehicles = []

if st.button("Select Vehicles"):
    if auto_manual == "Auto":
        usage_count = {}
        for v in st.session_state.vehicle_set:
            usage_count[v] = sum([v in h['Vehicles'] for h in st.session_state.history])
        sorted_vehicles = sorted(usage_count, key=lambda x: usage_count[x])
        for i in range(num_vehicles):
            for v in sorted_vehicles:
                conflict = False
                for g in st.session_state.vehicle_groups:
                    if v in g and any(p in g for p in selected_players):
                        conflict = True
                        break
                if not conflict and v not in selected_vehicles:
                    selected_vehicles.append(v)
                    break
    else:
        selected_vehicles = st.multiselect("Select vehicles manually", st.session_state.vehicle_set)
st.write("Selected Vehicles:", selected_vehicles)

# ------------------ GENERATE MATCH MESSAGE ------------------
if st.button("Generate Match Message"):
    msg = f"**Match Details**\nDate: {match_date}\nVenue: {venue}\nTeam: {', '.join(selected_players)}\nVehicles: {', '.join(selected_vehicles)}"
    st.text_area("Ready to copy message", msg, height=150)
    st.session_state.history.append({
        "Date": str(match_date),
        "Venue": venue,
        "Players": ", ".join(selected_players),
        "Vehicles": ", ".join(selected_vehicles)
    })

# ------------------ BACKUP / RESTORE ------------------
upload_file = st.file_uploader("Upload Backup File to Restore All Data", type="json")
if upload_file:
    if st.session_state.logged_in:
        data = json.load(upload_file)
        st.session_state.player_superset = data.get("player_superset", [])
        st.session_state.vehicle_set = data.get("vehicle_set", [])
        st.session_state.vehicle_groups = data.get("vehicle_groups", [])
        st.session_state.history = data.get("history", [])
        st.success("All data restored from backup file")
    else:
        st.warning("Admin login required to restore data")

# ------------------ PUSH TO GOOGLE SHEETS ------------------
if st.session_state.logged_in and GOOGLE_SHEETS_AVAILABLE:
    if st.button("Push All Data to Google Sheets"):
        save_sheet_df(SHEET_NAME, "Players", pd.DataFrame({"Player": st.session_state.player_superset}))
        save_sheet_df(SHEET_NAME, "Vehicles", pd.DataFrame({"Vehicle": st.session_state.vehicle_set}))
        groups_list = [{"Vehicle": g[0], "Players": ", ".join(g)} for g in st.session_state.vehicle_groups]
        save_sheet_df(SHEET_NAME, "VehicleGroups", pd.DataFrame(groups_list))
        save_sheet_df(SHEET_NAME, "History", pd.DataFrame(st.session_state.history))
        st.success("All data saved to Google Sheets")
