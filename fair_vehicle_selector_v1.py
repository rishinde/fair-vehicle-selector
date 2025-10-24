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

def open_or_create_sheet(client, sheet_name=SHEET_NAME):
    try:
        # list_spreadsheet_files returns list of dicts
        files = client.list_spreadsheet_files()
        titles = [f.get("name") for f in files]
        if sheet_name in titles:
            sh = client.open(sheet_name)
        else:
            sh = client.create(sheet_name)
        return sh
    except Exception as e:
        st.error(f"Failed to open or create spreadsheet: {e}")
        return None

def get_or_create_ws(sh, name, headers):
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(name, rows=100, cols=20)
        ws.append_row(headers)
    return ws

# -----------------------------
# Data Loading and Caching
# -----------------------------
@st.cache_data(show_spinner=False)
def load_players_vehicles(client):
    sh = open_or_create_sheet(client)
    if sh is None:
        return [], [], {}, [], {}
    ws_players = get_or_create_ws(sh, "Players", ["Player"])
    ws_vehicles = get_or_create_ws(sh, "Vehicles", ["Vehicle"])
    ws_groups = get_or_create_ws(sh, "VehicleGroups", ["Vehicle","Players"])
    ws_history = get_or_create_ws(sh, "History", ["Date","Ground","Players","Vehicles","Message"])

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
                usage[p]["present"] +=1
            for v in record.get("Vehicles","").split(", "):
                if v not in usage:
                    usage[v] = {"used":0,"present":0}
                usage[v]["used"] +=1
        return players, vehicles, vehicle_groups, history_records, usage
    except Exception as e:
        st.error(f"Failed to load sheet data: {e}")
        return [], [], {}, [], {}

# -----------------------------
# Google Sheets Incremental Updates
# -----------------------------
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

def add_player_local(player, players):
    if player and player not in players:
        players.append(player)
        st.success(f"✅ Added player locally: {player}")

def remove_player_local(player, players):
    if player in players:
        players.remove(player)
        st.warning(f"🗑️ Removed player locally: {player}")

def add_vehicle_local(vehicle, vehicles):
    if vehicle and vehicle not in vehicles:
        vehicles.append(vehicle)
        st.success(f"✅ Added vehicle locally: {vehicle}")

def remove_vehicle_local(vehicle, vehicles):
    if vehicle in vehicles:
        vehicles.remove(vehicle)
        st.warning(f"🗑️ Removed vehicle locally: {vehicle}")

def update_vehicle_group_local(vehicle_groups, vehicle, members):
    if vehicle:
        vehicle_groups[vehicle] = members
        st.success(f"✅ Updated group locally: {vehicle}")

def reset_all_data_local(players, vehicles, vehicle_groups, history):
    players.clear()
    vehicles.clear()
    vehicle_groups.clear()
    history.clear()
    st.warning("🧹 All data reset locally!")

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
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with admin control and vehicle grouping")

# Admin login
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
            st.experimental_rerun()
        else:
            st.error("❌ Incorrect username or password")

# Load Google Sheets data
client = get_gsheet_client()
if client:
    players, vehicles, vehicle_groups, history, usage = load_players_vehicles(client)
else:
    players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}
    st.warning("⚠️ Google Sheets not available. Using local session only.")

# -----------------------------
# Admin Controls Sidebar
# -----------------------------
if st.session_state.admin_logged_in:
    st.sidebar.header("⚙️ Admin Controls")
    if st.sidebar.button("🧹 Reset All Data"):
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
        reset_all_data_local(players, vehicles, vehicle_groups, history)
    if st.sidebar.button("💾 Save to Google Sheet"):
        if client:
            sh = open_or_create_sheet(client)
            if sh:
                ws_players = get_or_create_ws(sh, "Players", ["Player"])
                ws_vehicles = get_or_create_ws(sh, "Vehicles", ["Vehicle"])
                ws_groups = get_or_create_ws(sh, "VehicleGroups", ["Vehicle","Players"])
                ws_history = get_or_create_ws(sh, "History", ["Date","Ground","Players","Vehicles","Message"])
                try:
                    ws_players.clear()
                    ws_players.append_row(["Player"])
                    for p in players:
                        ws_players.append_row([p])
                    ws_vehicles.clear()
                    ws_vehicles.append_row(["Vehicle"])
                    for v in vehicles:
                        ws_vehicles.append_row([v])
                    ws_groups.clear()
                    ws_groups.append_row(["Vehicle","Players"])
                    for k,v in vehicle_groups.items():
                        ws_groups.append_row([k, ", ".join(v)])
                    ws_history.clear()
                    ws_history.append_row(["Date","Ground","Players","Vehicles","Message"])
                    for h in history:
                        append_history(ws_history, h)
                    st.success("✅ Data saved to Google Sheet successfully")
                except Exception as e:
                    st.error(f"Failed to save: {e}")
        else:
            st.error("⚠️ Google Sheets client not available")

# -----------------------------
# Players & Vehicles UI
# -----------------------------
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_player = st.text_input("Add new player:")
    if st.button("Add Player"):
        add_player_local(new_player, players)
    if players:
        remove_player_name = st.selectbox("Remove a player:", ["None"]+players)
        if remove_player_name!="None" and st.button("Remove Player"):
            remove_player_local(remove_player_name, players)
st.write("**Current Players:**", ", ".join(players))

st.header("2️⃣ Vehicle Set (subset of players)")
if st.session_state.admin_logged_in:
    new_vehicle = st.text_input("Add vehicle owner:")
    if st.button("Add Vehicle"):
        if new_vehicle in players:
            add_vehicle_local(new_vehicle, vehicles)
        else:
            st.warning("⚠️ Vehicle owner must exist in players superset")
    if vehicles:
        remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"]+vehicles)
        if remove_vehicle_name!="None" and st.button("Remove Vehicle"):
            remove_vehicle_local(remove_vehicle_name, vehicles)
st.write("**Current Vehicle Owners:**", ", ".join(vehicles))

# -----------------------------
# Vehicle Groups UI
# -----------------------------
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", players)
    if st.button("Add/Update Vehicle Group"):
        update_vehicle_group_local(vehicle_groups, vg_vehicle, vg_members)
st.write("**Current Vehicle Groups:**")
if vehicle_groups:
    for v, members in vehicle_groups.items():
        st.write(f"{v}: {', '.join(members)}")
else:
    st.write("No vehicle groups defined.")

# -----------------------------
# Daily Match Selection
# -----------------------------
st.header("4️⃣ Daily Match Selection")
if st.session_state.admin_logged_in:
    game_date = st.date_input("Select date:", value=date.today())
    ground_name = st.text_input("Ground name:")
    players_today = st.multiselect("Select players present today:", players)
    num_needed = st.number_input("Number of vehicles needed:", 1, len(vehicles) if vehicles else 1, 1)
    selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"], key="mode")

    if selection_mode == "Manual-Select":
        manual_selected = st.multiselect("Select vehicles manually:", vehicles, default=[])
    else:
        manual_selected = []

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
            history.append({
                "date": str(game_date),
                "ground": ground_name,
                "players_present": players_today,
                "selected_vehicles": selected,
                "message": msg
            })
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")

# -----------------------------
# Usage Table & Chart
# -----------------------------
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

# -----------------------------
# Recent Match Records
# -----------------------------
st.header("7️⃣ Recent Match Records")
if history:
    for r in reversed(history[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {', '.join(r['selected_vehicles'])}")
else:
    st.info("No match records yet")
