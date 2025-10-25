import streamlit as st
import json
from datetime import date
import pandas as pd
import plotly.express as px
import time

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
# Google Sheets Data Loader
# -----------------------------
def load_gsheet_data(client):
    """Load all data once per session, throttle reads to reduce quota hits"""
    try:
        existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
        sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)
    except Exception as e:
        st.error(f"Failed to open or create spreadsheet: {e}")
        return None, None, None, None, [], [], {}, [], {}

    def get_or_create_ws(name, headers):
        try:
            ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(name, rows=100, cols=20)
            ws.append_row(headers)
        return ws

    # Throttle reads
    time.sleep(0.5)

    ws_players = get_or_create_ws("Players", ["Player"])
    ws_vehicles = get_or_create_ws("Vehicles", ["Vehicle"])
    ws_groups = get_or_create_ws("VehicleGroups", ["Vehicle", "Players"])
    ws_history = get_or_create_ws("History", ["Date","Ground","Players","Vehicles","Message"])

    # Read all data once
    players = [r["Player"] for r in ws_players.get_all_records()]
    time.sleep(0.2)
    vehicles = [r["Vehicle"] for r in ws_vehicles.get_all_records()]
    time.sleep(0.2)
    vehicle_groups = {r["Vehicle"]: r["Players"].split(", ") for r in ws_groups.get_all_records()}
    time.sleep(0.2)
    history_records = ws_history.get_all_records()
    time.sleep(0.2)

    # Compute usage
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

    return ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history_records, usage

# -----------------------------
# Incremental Updates (in-memory only)
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
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with admin control and vehicle grouping")

client = get_gsheet_client()

# Load all data once per session
if client and "gsheet_data" not in st.session_state:
    st.session_state.gsheet_data = load_gsheet_data(client)

if client:
    ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = st.session_state.gsheet_data
else:
    st.warning("⚠️ Google Sheets not available. Admin operations disabled.")
    players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}

# -----------------------------
# Sidebar Admin Controls
# -----------------------------
if st.session_state.admin_logged_in and client:
    st.sidebar.header("⚙️ Admin Controls")
    
    # Reset all
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
        # Clear in-memory data
        players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}
        st.sidebar.success("✅ All data reset")

    # Undo last entry
    if st.sidebar.button("↩ Undo Last Entry"):
        if history:
            history.pop()
            st.sidebar.success("✅ Last entry removed from memory")

    # Backup
    st.sidebar.header("📂 Backup")
    st.sidebar.download_button("📥 Download JSON Backup", 
        json.dumps({
            "Players":[{"Player":p} for p in players],
            "Vehicles":[{"Vehicle":v} for v in vehicles],
            "VehicleGroups":[{"Vehicle":k,"Players":", ".join(v)} for k,v in vehicle_groups.items()],
            "History":history
        }, indent=4),
        file_name="backup.json",
        mime="application/json"
    )

    # Upload
    upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
    if upload_file:
        data = json.load(upload_file)
        players = [p["Player"] for p in data.get("Players",[])]
        vehicles = [v["Vehicle"] for v in data.get("Vehicles",[])]
        vehicle_groups = {g["Vehicle"]: g["Players"].split(", ") for g in data.get("VehicleGroups",[])}
        history = data.get("History",[])
        st.sidebar.success("✅ Data restored from backup")

# -----------------------------
# Main UI: 7 Sections (All in-memory operations)
# -----------------------------

# 1️⃣ Players Superset
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_player = st.text_input("Add new player:")
    if st.button("Add Player"):
        if new_player and new_player not in players:
            players.append(new_player)
            st.success(f"✅ Added player: {new_player}")
    if players:
        remove_player_name = st.selectbox("Remove a player:", ["None"]+players)
        if remove_player_name!="None" and st.button("Remove Player"):
            players.remove(remove_player_name)
            st.success(f"🗑️ Removed player: {remove_player_name}")
    if st.button("💾 Save Players to Google Sheet") and client:
        ws_players.clear()
        ws_players.append_row(["Player"])
        for p in players:
            ws_players.append_row([p])
        st.success("✅ Players saved to Google Sheet")

st.write("**Current Players:**", ", ".join(players))

# 2️⃣ Vehicle Set
st.header("2️⃣ Vehicle Set")
if st.session_state.admin_logged_in:
    new_vehicle = st.text_input("Add vehicle owner:")
    if st.button("Add Vehicle"):
        if new_vehicle in players and new_vehicle not in vehicles:
            vehicles.append(new_vehicle)
            st.success(f"✅ Added vehicle owner: {new_vehicle}")
        else:
            st.warning("⚠️ Vehicle owner must exist in players and not duplicate")
    if vehicles:
        remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"]+vehicles)
        if remove_vehicle_name!="None" and st.button("Remove Vehicle"):
            vehicles.remove(remove_vehicle_name)
            st.success(f"🗑️ Removed vehicle: {remove_vehicle_name}")
    if st.button("💾 Save Vehicles to Google Sheet") and client:
        ws_vehicles.clear()
        ws_vehicles.append_row(["Vehicle"])
        for v in vehicles:
            ws_vehicles.append_row([v])
        st.success("✅ Vehicles saved to Google Sheet")

st.write("**Current Vehicle Owners:**", ", ".join(vehicles))

# 3️⃣ Vehicle Groups
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", players)
    if st.button("Add/Update Vehicle Group"):
        if vg_vehicle:
            vehicle_groups[vg_vehicle] = vg_members
            st.success(f"✅ Group updated for {vg_vehicle}")
    if st.button("💾 Save Vehicle Groups to Google Sheet") and client:
        ws_groups.clear()
        ws_groups.append_row(["Vehicle","Players"])
        for k,v in vehicle_groups.items():
            ws_groups.append_row([k, ", ".join(v)])
        st.success("✅ Vehicle groups saved to Google Sheet")

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
            # Store in memory
            history.append({
                "date": str(game_date),
                "ground": ground_name,
                "players_present": players_today,
                "selected_vehicles": selected,
                "message": msg
            })
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")

    if st.button("💾 Save Match History to Google Sheet") and client:
        ws_history.clear()
        ws_history.append_row(["Date","Ground","Players","Vehicles","Message"])
        for r in history:
            ws_history.append_row([
                r["date"],
                r["ground"],
                ", ".join(r["players_present"]),
                ", ".join(r["selected_vehicles"]),
                r["message"]
            ])
        st.success("✅ Match history saved to Google Sheet")

# 5️⃣ Reserved (future)

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
        st.write(f"📅 {r['Date']} — {r['Ground']} — 🚗 {', '.join(r['Vehicles'])}")
else:
    st.info("No match records yet")
