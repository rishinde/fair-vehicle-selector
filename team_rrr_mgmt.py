# team_rrr_mgmt.py
import sys
import os
import streamlit as st
import json
from datetime import date
sys.path.append(os.path.dirname(__file__))
from vehicle_management import vehicle_management
from financial_management import financial_management
from player_stats_management import player_stats_management

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

# -----------------------------
# Load Google Sheets Data
# -----------------------------
def load_gsheet_data(client):
    try:
        existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
        sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)
    except Exception as e:
        st.error(f"Failed to open or create spreadsheet: {e}")
        return None, None, None, None, [], [], {}, [], {}

    def safe_get_records(ws, name):
        try:
            return ws.get_all_records()
        except Exception as e:
            if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                st.error(f"⚠️ Google Sheets quota exceeded while reading {name}. Please try again later.")
            else:
                st.error(f"❌ Failed to read {name} data: {e}")
            return []

    def get_or_create_ws(name, headers):
        try:
            ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(name, rows=100, cols=20)
            ws.append_row(headers)
        return ws

    ws_players = get_or_create_ws("Players", ["Player"])
    ws_vehicles = get_or_create_ws("Vehicles", ["Vehicle"])
    ws_groups = get_or_create_ws("VehicleGroups", ["Vehicle", "Players"])
    ws_history = get_or_create_ws("History", ["date","players_present","selected_vehicles","message"])

    # Load data
    players = [r["Player"] for r in safe_get_records(ws_players, "Players")]
    vehicles = [r["Vehicle"] for r in safe_get_records(ws_vehicles, "Vehicles")]
    vehicle_groups = {r["Vehicle"]: r["Players"].split(", ") for r in safe_get_records(ws_groups, "VehicleGroups")}
    history_records = safe_get_records(ws_history, "History")

    # Compute usage
    usage = {}
    for record in history_records:
        for p in record.get("players_present","").split(", "):
            if p not in usage:
                usage[p] = {"used":0,"present":0}
            usage[p]["present"] +=1
        for v in record.get("selected_vehicles","").split(", "):
            if v not in usage:
                usage[v] = {"used":0,"present":0}
            usage[v]["used"] +=1

    return ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history_records, usage

# -----------------------------
# Streamlit Setup
# -----------------------------
st.set_page_config(page_title="Team RRR Management", page_icon="🏏", layout="centered")
st.title("🏏 Team RRR Management 🏏")

if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

with st.sidebar:
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
    
## Admin Login
#if "admin_logged_in" not in st.session_state:
#    st.session_state.admin_logged_in = False
#
#if not st.session_state.admin_logged_in:
#    st.subheader("🔒 Admin Login")
#    username = st.text_input("Username")
#    password = st.text_input("Password", type="password")
#    if st.button("Login"):
#        if username=="admin" and password=="admin123":
#            st.session_state.admin_logged_in = True
#            st.success("✅ Logged in as Admin")
#        else:
#            st.error("❌ Incorrect username or password")

# Load Google Sheet data
client = get_gsheet_client()
if client and "gsheet_data" not in st.session_state:
    st.session_state.gsheet_data = load_gsheet_data(client)

if client:
    ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = st.session_state.gsheet_data
else:
    st.warning("⚠️ Google Sheets not available. Admin operations disabled.")
    players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}

# -----------------------------
# Tabs Integration
# -----------------------------
tabs = st.tabs(["Player Superset", "Vehicle Management", "Financial Management"])

# -----------------------------
# Tab 1: Player Superset
# -----------------------------
with tabs[0]:
# -----------------------------
# Tab 1: Player Superset (Card Grid Style)
# -----------------------------
    st.header("👥 Player Superset")

    player_stats = {}
    try:
        ws_stats = client.open(SHEET_NAME).worksheet("PlayerStats")
        stats_data = ws_stats.get_all_records()
        for row in stats_data:
            player_name = row.get("Player")
            if player_name:
                player_stats[player_name] = {
                    "Inns": row.get("Innings", 0),
                    "Runs": row.get("Runs", 0),
                    "Avg": row.get("Average", 0),
                    "SR": row.get("StrikeRate", 0)
                }
    except Exception:
        player_stats = {}
    
    player_stats_bowl = {}
    try:
        ws_stats = client.open(SHEET_NAME).worksheet("PlayerStatsBowl")
        stats_data = ws_stats.get_all_records()
        for row in stats_data:
            player_name = row.get("Player")
            if player_name:
                player_stats_bowl[player_name] = {
                    "Inns": row.get("Innings", 0),
                    "Wkts": row.get("Wickets", 0),
                    "Eco": row.get("Economy", 0),
                    "Avg": row.get("Average", 0)
                }
    except Exception:
        player_stats_bowl = {}

    # --- Admin actions ---
    if st.session_state.admin_logged_in:
        st.subheader("➕ Manage Players")
        new_player = st.text_input("Add New Player", key="add_player_input")
        if st.button("Add Player", key="add_player_btn"):
            if new_player and new_player not in players:
                players.append(new_player)
                st.success(f"✅ Added player: {new_player}")
            else:
                st.warning("⚠️ Player name is empty or already exists.")

        # Remove player
        if players:
            remove_player = st.selectbox("Select Player to Remove", ["None"] + sorted(players))
            if remove_player != "None" and st.button("🗑️ Remove Player", key="remove_player_btn"):
                players.remove(remove_player)
                st.success(f"🗑️ Removed player: {remove_player}")

        # Save to Google Sheet
        if st.button("💾 Save Players to Google Sheet", key="save_players_btn") and client:
            try:
                ws_players.clear()
                ws_players.append_row(["Player"])
                for p in sorted(players):
                    ws_players.append_row([p])
                st.success("✅ Players saved to Google Sheet")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.error(f"❌ Failed to save players: {e}")

    # --- Display players as cards ---
    st.subheader("🏏 Current Players")

    if not players:
        st.info("No players added yet. Add some from the admin panel.")
    else:
        sorted_players = sorted(players)
        #cols = st.columns(1)  # 4 cards per row
        for i, player in enumerate(sorted_players):
            stats = player_stats.get(player, None)
            if stats:
                stats_text = f"Inns: {stats['Inns']} | Runs: {stats['Runs']} | Avg: {stats['Avg']} | SR: {stats['SR']}"
            else:
                stats_text = "No Data Available"
            statsB = player_stats_bowl.get(player, None)
            if statsB:
                statsb_text = f"Inns: {statsB['Inns']} | Wkts: {statsB['Wkts']} | Eco: {statsB['Eco']} | Avg: {statsB['Avg']}"
            else:
                statsb_text = "No Data Available"
            
            #st.markdown(
            #    f"""
            #    <div style='
            #        background-color:#ffffff;
            #        border:1px solid #e0e0e0;
            #        padding:15px;
            #        margin:8px 0;
            #        border-radius:12px;
            #        box-shadow:0 2px 6px rgba(0,0,0,0.1);
            #        font-family:"Segoe UI", sans-serif;
            #        transition: all 0.2s ease-in-out;
            #    '>
            #        <div style='font-weight:600; color:#007bff; font-size:1.05rem; margin-bottom:4px;'>
            #            🏏 {player}
            #        </div>
            #        <div style='color:#444; font-size:0.9rem;'>
            #            <span style='font-weight:500;'>Bat:</span> {stats_text}
            #        </div>
            #        <div style='color:#444; font-size:0.9rem;'>
            #            <span style='font-weight:500;'>Bowl:</span> {statsb_text}
            #        </div>
            #    </div>
            #    """,
            #    unsafe_allow_html=True
            #)

            st.markdown(
            f"""
            <div style='
                background-color:#ffffff;
                border:1px solid #e0e0e0;
                border-radius:12px;
                padding:10px 14px;
                margin:8px 0;
                box-shadow:0 1px 4px rgba(0,0,0,0.06);
                font-family:"Segoe UI", sans-serif;
            '>
                <div style='font-weight:600; color:#007bff; font-size:1rem; margin-bottom:6px;'>
                    🏏 {player}
                </div>
                <div style='background:#f1f9ff; border-radius:6px; padding:6px 10px; margin-bottom:4px; font-size:0.9rem;'>
                    <span style='font-weight:600;'>⚔️ Bat:</span> {stats_text}
                </div>
                <div style='background:#f8fff1; border-radius:6px; padding:6px 10px; font-size:0.9rem;'>
                    <span style='font-weight:600;'>🎯 Bowl:</span> {statsb_text}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

# -----------------------------
# Tab 2: Vehicle Management
# -----------------------------
with tabs[1]:
    vehicle_management(players, vehicles, vehicle_groups, history, usage, client, ws_players, ws_vehicles, ws_groups, ws_history)

# -----------------------------
# Tab 3: Financial Management (Placeholder)
# -----------------------------
with tabs[2]:
    st.header("💰 Financial Management")
    financial_management(players, client)
    #st.info("Financial management tab will be implemented here.")
#with tabs[3]:
#    st.header("Player Stats Management")
#    player_stats_management(client)
