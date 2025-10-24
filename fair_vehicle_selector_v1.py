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
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
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
        st.error(f"Failed to authorize Google Sheets: {e}")
        return None

def load_sheets(client):
    try:
        sheet_titles = [s['name'] for s in client.list_spreadsheet_files()]
        if SHEET_NAME in sheet_titles:
            sh = client.open(SHEET_NAME)
        else:
            sh = client.create(SHEET_NAME)
    except Exception as e:
        st.error(f"Failed to open or create spreadsheet: {e}")
        return None, None, None, None

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
    ws_history = get_or_create_ws("History", ["Date", "Ground", "Players", "Vehicles", "Message"])
    return ws_players, ws_vehicles, ws_groups, ws_history

def read_data(ws_players, ws_vehicles, ws_groups, ws_history):
    try:
        players = [r["Player"] for r in ws_players.get_all_records()]
        vehicles = [r["Vehicle"] for r in ws_vehicles.get_all_records()]
        vehicle_groups = {r["Vehicle"]: r["Players"].split(", ") for r in ws_groups.get_all_records()}
        history_records = ws_history.get_all_records()
        usage = {}
        for record in history_records:
            for p in record.get("Players","").split(", "):
                if p not in usage:
                    usage[p] = {"used":0,"present":0}
                usage[p]["present"] += 1
            for v in record.get("Vehicles","").split(", "):
                if v not in usage:
                    usage[v] = {"used":0,"present":0}
                usage[v]["used"] +=1
        return players, vehicles, vehicle_groups, history_records, usage
    except Exception as e:
        st.error(f"Error reading data from sheet: {e}")
        return [], [], {}, [], {}

def append_history(ws_history, record):
    try:
        row = [
            record.get("date",""),
            record.get("ground",""),
            ", ".join(record.get("players_present",[])),
            ", ".join(record.get("selected_vehicles",[])),
            record.get("message","")
        ]
        ws_history.append_row(row)
    except Exception as e:
        st.error(f"Failed to append history: {e}")

def undo_last_history(ws_history):
    try:
        all_rows = ws_history.get_all_values()
        if len(all_rows) > 1:
            ws_history.delete_rows(len(all_rows))
    except Exception as e:
        st.error(f"Failed to undo last entry: {e}")

def add_player(ws_players, player, players_list):
    try:
        if player not in players_list:
            ws_players.append_row([player])
            players_list.append(player)
    except Exception as e:
        st.error(f"Failed to add player '{player}': {e}")

def remove_player(ws_players, player, players_list):
    try:
        all_records = ws_players.get_all_records()
        for idx, r in enumerate(all_records, start=2):
            if r["Player"] == player:
                ws_players.delete_rows(idx)
                players_list.remove(player)
                break
    except Exception as e:
        st.error(f"Failed to remove player '{player}': {e}")

def add_vehicle(ws_vehicles, vehicle, vehicles_list):
    try:
        if vehicle not in vehicles_list:
            ws_vehicles.append_row([vehicle])
            vehicles_list.append(vehicle)
    except Exception as e:
        st.error(f"Failed to add vehicle '{vehicle}': {e}")

def remove_vehicle(ws_vehicles, vehicle, vehicles_list):
    try:
        all_records = ws_vehicles.get_all_records()
        for idx, r in enumerate(all_records, start=2):
            if r["Vehicle"]==vehicle:
                ws_vehicles.delete_rows(idx)
                vehicles_list.remove(vehicle)
                break
    except Exception as e:
        st.error(f"Failed to remove vehicle '{vehicle}': {e}")

def update_vehicle_group(ws_groups, vehicle, members):
    try:
        all_records = ws_groups.get_all_records()
        for idx, r in enumerate(all_records, start=2):
            if r["Vehicle"] == vehicle:
                ws_groups.delete_rows(idx)
                break
        ws_groups.append_row([vehicle, ", ".join(members)])
    except Exception as e:
        st.error(f"Failed to update vehicle group for '{vehicle}': {e}")

def reset_all_data(ws_players, ws_vehicles, ws_groups, ws_history):
    try:
        backup = {
            "Players": ws_players.get_all_records(),
            "Vehicles": ws_vehicles.get_all_records(),
            "VehicleGroups": ws_groups.get_all_records(),
            "History": ws_history.get_all_records()
        }
        st.download_button("📥 Download Backup Before Reset",
                           json.dumps(backup, indent=4),
                           file_name=f"backup_before_reset_{date.today()}.json",
                           mime="application/json")
        for ws in [ws_players, ws_vehicles, ws_groups, ws_history]:
            ws.clear()
    except Exception as e:
        st.error(f"Failed to reset data: {e}")

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

# -----------------------------
# Admin Login
# -----------------------------
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with admin control and vehicle grouping")

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
# Load Data Once
# -----------------------------
client = get_gsheet_client() if GOOGLE_SHEETS_AVAILABLE else None
if client and "sheets_loaded" not in st.session_state:
    ws_players, ws_vehicles, ws_groups, ws_history = load_sheets(client)
    if ws_players:
        players, vehicles, vehicle_groups, history, usage = read_data(ws_players, ws_vehicles, ws_groups, ws_history)
        st.session_state.update({
            "ws_players": ws_players,
            "ws_vehicles": ws_vehicles,
            "ws_groups": ws_groups,
            "ws_history": ws_history,
            "players": players,
            "vehicles": vehicles,
            "vehicle_groups": vehicle_groups,
            "history": history,
            "usage": usage,
            "sheets_loaded": True
        })
else:
    # Use cached session state
    players = st.session_state.get("players", [])
    vehicles = st.session_state.get("vehicles", [])
    vehicle_groups = st.session_state.get("vehicle_groups", {})
    history = st.session_state.get("history", [])
    usage = st.session_state.get("usage", {})
    ws_players = st.session_state.get("ws_players")
    ws_vehicles = st.session_state.get("ws_vehicles")
    ws_groups = st.session_state.get("ws_groups")
    ws_history = st.session_state.get("ws_history")

# -----------------------------
# Sidebar Admin Controls
# -----------------------------
if st.session_state.admin_logged_in:
    st.sidebar.header("⚙️ Admin Controls")
    if st.sidebar.button("🧹 Reset All Data"):
        reset_all_data(ws_players, ws_vehicles, ws_groups, ws_history)
        st.experimental_rerun()

    if st.sidebar.button("↩ Undo Last Entry"):
        undo_last_history(ws_history)
        st.experimental_rerun()

    if st.sidebar.button("💾 Save Changes to Sheet"):
        st.success("✅ All changes saved to Google Sheet")

    st.sidebar.header("📂 Backup")
    upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
    if upload_file:
        try:
            data = json.load(upload_file)
            # Clear existing
            reset_all_data(ws_players, ws_vehicles, ws_groups, ws_history)
            # Restore
            for p in data.get("Players",[]):
                add_player(ws_players, p["Player"], players)
            for v in data.get("Vehicles",[]):
                add_vehicle(ws_vehicles, v["Vehicle"], vehicles)
            for g in data.get("VehicleGroups",[]):
                update_vehicle_group(ws_groups, g["Vehicle"], g["Players"].split(", "))
                vehicle_groups[g["Vehicle"]] = g["Players"].split(", ")
            for h in data.get("History",[]):
                append_history(ws_history, h)
            st.success("✅ Data restored from backup")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Failed to upload backup: {e}")

# -----------------------------
# UI: Players, Vehicles, Groups, Match Selection
# -----------------------------
# 1️⃣ Players
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_player = st.text_input("Add new player:")
    if st.button("Add Player"):
        add_player(ws_players, new_player, players)
        st.experimental_rerun()
    if players:
        remove_player_name = st.selectbox("Remove a player:", ["None"]+players)
        if remove_player_name!="None" and st.button("Remove Player"):
            remove_player(ws_players, remove_player_name, players)
            st.experimental_rerun()
st.write("**Current Players:**", ", ".join(players))

# 2️⃣ Vehicle Set
st.header("2️⃣ Vehicle Set")
if st.session_state.admin_logged_in:
    new_vehicle = st.text_input("Add vehicle owner:")
    if st.button("Add Vehicle"):
        if new_vehicle in players:
            add_vehicle(ws_vehicles, new_vehicle, vehicles)
            st.experimental_rerun()
        else:
            st.warning("⚠️ Player must exist in superset")
    if vehicles:
        remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"]+vehicles)
        if remove_vehicle_name!="None" and st.button("Remove Vehicle"):
            remove_vehicle(ws_vehicles, remove_vehicle_name, vehicles)
            st.experimental_rerun()
st.write("**Current Vehicle Owners:**", ", ".join(vehicles))

# 3️⃣ Vehicle Groups
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", players)
    if st.button("Add/Update Vehicle Group"):
        if vg_vehicle:
            update_vehicle_group(ws_groups, vg_vehicle, vg_members)
            vehicle_groups[vg_vehicle] = vg_members
st.write("**Current Vehicle Groups:**")
if vehicle_groups:
    for v, members in vehicle_groups.items():
        st.write(f"{v}: {', '.join(members)}")
else:
    st.write("No vehicle groups defined.")

# 4️⃣ Daily Match Selection
st.header("4️⃣ Daily Match Selection")
if st.session_state.admin_logged_in:
    game_date = st.date_input("Select date:", value=date.today())
    ground_name = st.text_input("Ground name:")
    players_today = st.multiselect("Select players present today:", players)
    num_needed = st.number_input("Number of vehicles needed:", 1, len(vehicles) if vehicles else 1, 1)
    selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"], key="mode")
    manual_selected = st.multiselect("Select vehicles manually:", vehicles) if selection_mode=="Manual-Select" else []

    if st.button("Select Vehicles"):
        eligible = [v for v in players_today if v in vehicles]
        if selection_mode=="Auto-Select":
            selected = select_vehicles_auto(vehicles, players_today, num_needed, usage, vehicle_groups)
        else:
            if len(manual_selected) != num_needed:
                st.warning(f"⚠️ Select exactly {num_needed} vehicles")
                selected = []
            else:
                selected = manual_selected
                update_usage(selected, eligible, usage)
        if selected:
            msg = generate_message(game_date, ground_name, players_today, selected)
            st.subheader("📋 Copy-Ready Message")
            st.text_area("Message:", msg, height=200)
            record = {
                "date": str(game_date),
                "ground": ground_name,
                "players_present": players_today,
                "selected_vehicles": selected,
                "message": msg
            }
            append_history(ws_history, record)
            st.experimental_rerun()

# 6️⃣ Usage Table & Chart
st.header("6️⃣ Vehicle Usage")
if usage:
    df_usage = pd.DataFrame([
        {"Player": k, "Used": v["used"], "Present": v["present"], "Ratio": v["used"]/v["present"] if v["present"]>0 else 0}
        for k,v in usage.items()
    ])
    st.table(df_usage)
    fig = px.bar(df_usage, x="Player", y="Ratio", text="Used", title="Player Vehicle Usage Fairness")
    fig.update_traces(textposition='outside')
    fig.update_layout(yaxis=dict(range=[0,1.2]))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No usage data yet")

# 7️⃣ Recent Match Records
st.header("7️⃣ Recent Match Records")
if history:
    for r in reversed(history[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {', '.join(r['selected_vehicles'])}")
else:
    st.info("No match records yet")
