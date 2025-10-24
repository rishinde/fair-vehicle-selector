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
            st.warning("⚠️ Google Sheets service account not found in secrets")
            return None
    except Exception as e:
        st.error(f"❌ Failed to authorize Google Sheets: {e}")
        return None

def safe_append(ws, row):
    """Append a row safely to Google Sheet"""
    try:
        row_str = [str(x) for x in row]
        ws.append_row(row_str)
    except Exception as e:
        st.error(f"❌ Could not write to sheet '{ws.title}': {e}")

def safe_delete_last(ws):
    """Delete last row safely"""
    try:
        rows = ws.get_all_values()
        if len(rows) > 1:
            ws.delete_row(len(rows))
    except Exception as e:
        st.error(f"❌ Could not delete last row from '{ws.title}': {e}")

def safe_update_group(ws, vehicle, members):
    """Add or update vehicle group"""
    try:
        all_records = ws.get_all_records()
        for idx, r in enumerate(all_records, start=2):
            if r["Vehicle"]==vehicle:
                ws.delete_row(idx)
                break
        ws.append_row([vehicle, ", ".join(members)])
    except Exception as e:
        st.error(f"❌ Could not update vehicle group '{vehicle}': {e}")

def safe_reset(ws):
    try:
        ws.clear()
    except Exception as e:
        st.error(f"❌ Could not reset sheet '{ws.title}': {e}")

# -----------------------------
# Load Cached Data
# -----------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_gsheet_data(client):
    try:
        # Open or create spreadsheet
        sh = client.open(SHEET_NAME) if SHEET_NAME in [s.title for s in client.list_spreadsheet_files()] else client.create(SHEET_NAME)

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
        ws_history = get_or_create_ws("History", ["Date","Ground","Players","Vehicles","Message"])

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

        return ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history_records, usage
    except Exception as e:
        st.error(f"❌ Could not load Google Sheet data: {e}")
        return None, None, None, None, [], [], {}, [], {}

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
        # Remove other players in same group
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
if client:
    ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = load_gsheet_data(client)
else:
    st.warning("⚠️ Google Sheets not available. Admin operations disabled.")
    players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}

# -----------------------------
# Sidebar Admin Controls
# -----------------------------
if st.session_state.admin_logged_in and client:
    st.sidebar.header("⚙️ Admin Controls")
    if st.sidebar.button("🧹 Reset All Data"):
        # Auto backup
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
        # Clear all sheets
        for ws in [ws_players, ws_vehicles, ws_groups, ws_history]:
            safe_reset(ws)
        st.sidebar.success("✅ All data reset")
        st.experimental_rerun()

    if st.sidebar.button("↩ Undo Last Entry"):
        safe_delete_last(ws_history)
        st.sidebar.success("✅ Last entry undone")
        st.experimental_rerun()

    st.sidebar.header("📂 Backup")
    if st.sidebar.button("📥 Download JSON Backup"):
        data = {
            "Players":[{"Player":p} for p in players],
            "Vehicles":[{"Vehicle":v} for v in vehicles],
            "VehicleGroups":[{"Vehicle":k,"Players":", ".join(v)} for k,v in vehicle_groups.items()],
            "History":history
        }
        st.sidebar.download_button("Download JSON Backup", json.dumps(data, indent=4), "backup.json", "application/json")

    upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
    if upload_file:
        data = json.load(upload_file)
        # Clear existing
        for ws in [ws_players, ws_vehicles, ws_groups, ws_history]:
            safe_reset(ws)
        # Restore
        for p in data.get("Players",[]):
            safe_append(ws_players, [p["Player"]])
            players.append(p["Player"])
        for v in data.get("Vehicles",[]):
            safe_append(ws_vehicles, [v["Vehicle"]])
            vehicles.append(v["Vehicle"])
        for g in data.get("VehicleGroups",[]):
            safe_update_group(ws_groups, g["Vehicle"], g["Players"].split(", "))
            vehicle_groups[g["Vehicle"]] = g["Players"].split(", ")
        for h in data.get("History",[]):
            safe_append(ws_history, [h.get("date",""), h.get("ground",""), ", ".join(h.get("players_present",[])), ", ".join(h.get("selected_vehicles",[])), h.get("message","")])
            history.append(h)
        st.sidebar.success("✅ Data restored from backup")
        st.experimental_rerun()

# -----------------------------
# Main UI: Players, Vehicles, Groups, Daily Match Selection
# -----------------------------
# Players
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_player = st.text_input("Add new player:")
    if st.button("Add Player"):
        if new_player and new_player not in players:
            safe_append(ws_players, [new_player])
            players.append(new_player)
            st.success(f"✅ Added player: {new_player}")
            st.experimental_rerun()
    if players:
        remove_player_name = st.selectbox("Remove a player:", ["None"]+players)
        if remove_player_name!="None" and st.button("Remove Player"):
            # remove from sheet
            all_records = ws_players.get_all_records()
            for idx, r in enumerate(all_records, start=2):
                if r["Player"]==remove_player_name:
                    try:
                        ws_players.delete_row(idx)
                        players.remove(remove_player_name)
                        st.success(f"🗑️ Removed player: {remove_player_name}")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"❌ Could not remove player: {e}")

st.write("**Current Players:**", ", ".join(players))

# Vehicles
st.header("2️⃣ Vehicle Set (subset of players)")
if st.session_state.admin_logged_in:
    new_vehicle = st.text_input("Add vehicle owner:")
    if st.button("Add Vehicle"):
        if new_vehicle in players and new_vehicle not in vehicles:
            safe_append(ws_vehicles, [new_vehicle])
            vehicles.append(new_vehicle)
            st.success(f"✅ Added vehicle owner: {new_vehicle}")
            st.experimental_rerun()
        else:
            st.warning("⚠️ Vehicle owner must exist in player superset or already added")
    if vehicles:
        remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"]+vehicles)
        if remove_vehicle_name!="None" and st.button("Remove Vehicle"):
            all_records = ws_vehicles.get_all_records()
            for idx, r in enumerate(all_records, start=2):
                if r["Vehicle"]==remove_vehicle_name:
                    try:
                        ws_vehicles.delete_row(idx)
                        vehicles.remove(remove_vehicle_name)
                        st.success(f"🗑️ Removed vehicle owner: {remove_vehicle_name}")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"❌ Could not remove vehicle owner: {e}")

st.write("**Current Vehicle Owners:**", ", ".join(vehicles))

# Vehicle Groups
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", players)
    if st.button("Add/Update Vehicle Group"):
        if vg_vehicle:
            safe_update_group(ws_groups, vg_vehicle, vg_members)
            vehicle_groups[vg_vehicle] = vg_members
            st.success(f"✅ Group updated for {vg_vehicle}")

if vehicle_groups:
    st.write("**Current Vehicle Groups:**")
    for v, members in vehicle_groups.items():
        st.write(f"{v}: {', '.join(members)}")
else:
    st.write("No vehicle groups defined.")

# Daily Match Selection
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
            # append history to sheet
            record = [str(game_date), ground_name, ", ".join(players_today), ", ".join(selected), msg]
            safe_append(ws_history, record)
            history.append({
                "date": str(game_date),
                "ground": ground_name,
                "players_present": players_today,
                "selected_vehicles": selected,
                "message": msg
            })
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")
            st.experimental_rerun()

# Vehicle Usage
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

# Recent Matches
st.header("7️⃣ Recent Match Records")
if history:
    for r in reversed(history[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {', '.join(r['selected_vehicles'])}")
else:
    st.info("No match records yet")
