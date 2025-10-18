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
    # Normalize history records
    for i, record in enumerate(history):
        if "players_present" not in record:
            record["players_present"] = record.get("Players","").split(", ") if record.get("Players") else []
        if "selected_vehicles" not in record:
            record["selected_vehicles"] = record.get("Vehicles","").split(", ") if record.get("Vehicles") else []
        if "date" not in record:
            record["date"] = record.get("Date","")
        if "ground" not in record:
            record["ground"] = record.get("Ground","")
        if "message" not in record:
            record["message"] = record.get("Message","")
        history[i] = record
    # Recalculate usage
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
# Load Data Initially
# -----------------------------
players, vehicles, history, usage, vehicle_groups = [], [], [], {}, {}

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
        players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}
        reset_google_sheet()
        st.sidebar.success("✅ All data reset")

    if st.sidebar.button("↩ Undo Last Entry"):
        history, usage, undone = undo_last_entry(history, usage)
        push_to_google_sheet(players, vehicles, vehicle_groups, history)
        if undone:
            st.sidebar.success("✅ Last entry removed")
        else:
            st.sidebar.info("ℹ️ No record to undo")

    if st.sidebar.button("📥 Download File"):
        data = download_from_google_sheet()
        if data:
            st.sidebar.download_button("Download JSON Backup", json.dumps(data, indent=4), "backup.json", "application/json")
    upload_file = st.sidebar.file_uploader("Upload JSON Backup", type="json")
    if upload_file:
        data = json.load(upload_file)
        players = [p["Player"] for p in data.get("Players",[])]
        vehicles = [v["Vehicle"] for v in data.get("Vehicles",[])]
        vehicle_groups = {g["Vehicle"]: g["Players"].split(", ") for g in data.get("VehicleGroups",[])}
        history = data.get("History", [])
        usage = {}
        for record in history:
            players_present = record.get("players_present", [])
            selected_vehicles = record.get("selected_vehicles", [])
            if not players_present:
                players_present = record.get("Players", "").split(", ")
            if not selected_vehicles:
                selected_vehicles = record.get("Vehicles", "").split(", ")
            for p in players_present:
                if p not in usage:
                    usage[p] = {"used":0,"present":0}
                usage[p]["present"] +=1
            for v in selected_vehicles:
                if v not in usage:
                    usage[v] = {"used":0,"present":0}
                usage[v]["used"] +=1
        push_to_google_sheet(players, vehicles, vehicle_groups, history)
        st.sidebar.success("✅ Data restored from uploaded JSON")

# -----------------------------
# Players Superset
# -----------------------------
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_player = st.text_input("Add new player:")
    if st.button("Add Player"):
        if new_player and new_player not in players:
            players.append(new_player)
            push_to_google_sheet(players, vehicles, vehicle_groups, history)
            st.success(f"✅ Added player: {new_player}")
        elif new_player in players:
            st.warning("⚠️ Player already exists")
        else:
            st.warning("Enter a valid name")
    if players:
        remove_player = st.selectbox("Remove a player:", ["None"] + players)
        if remove_player != "None" and st.button("Remove Player"):
            players.remove(remove_player)
            if remove_player in vehicles:
                vehicles.remove(remove_player)
            push_to_google_sheet(players, vehicles, vehicle_groups, history)
            st.success(f"🗑️ Removed player: {remove_player}")
st.write("**Current Players:**", ", ".join(players))

# -----------------------------
# Vehicle Set
# -----------------------------
st.header("2️⃣ Vehicle Set (subset of players)")
if st.session_state.admin_logged_in:
    new_vehicle = st.text_input("Add vehicle owner:")
    if st.button("Add Vehicle"):
        if new_vehicle and new_vehicle in players and new_vehicle not in vehicles:
            vehicles.append(new_vehicle)
            push_to_google_sheet(players, vehicles, vehicle_groups, history)
            st.success(f"✅ Added vehicle owner: {new_vehicle}")
        elif new_vehicle not in players:
            st.warning("⚠️ Player must exist in superset")
        elif new_vehicle in vehicles:
            st.warning("⚠️ Already a vehicle owner")
    if vehicles:
        remove_vehicle = st.selectbox("Remove vehicle owner:", ["None"] + vehicles)
        if remove_vehicle != "None" and st.button("Remove Vehicle"):
            vehicles.remove(remove_vehicle)
            push_to_google_sheet(players, vehicles, vehicle_groups, history)
            st.success(f"🗑️ Removed vehicle owner: {remove_vehicle}")
st.write("**Current Vehicle Owners:**", ", ".join(vehicles))

# -----------------------------
# Vehicle Groups
# -----------------------------
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", players)
    if st.button("Add/Update Vehicle Group"):
        if vg_vehicle:
            vehicle_groups[vg_vehicle] = vg_members
            push_to_google_sheet(players, vehicles, vehicle_groups, history)
            st.success(f"✅ Group updated for {vg_vehicle}")
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
        manual_selected = st.multiselect(
            "Select vehicles manually:",
            options=vehicles,
            default=[],
            help=f"Select exactly {num_needed} vehicles"
        )
    else:
        manual_selected = []

    if st.button("Select Vehicles"):
        eligible = [v for v in players_today if v in vehicles]

        if selection_mode=="Auto-Select":
            selected = select_vehicles_auto(vehicles, players_today, num_needed, usage, vehicle_groups)
        else:
            if len(manual_selected) != num_needed:
                st.warning(f"⚠️ Please select exactly {num_needed} vehicles")
                selected = []
            else:
                selected = manual_selected
                update_usage(selected, eligible, usage)

        if selected:
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")
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
            history.append(record)
            push_to_google_sheet(players, vehicles, vehicle_groups, history)
else:
    st.info("🔒 Daily player/vehicle selection is admin-only. Please login as admin to modify.")

# -----------------------------
# Vehicle Usage Table & Chart
# -----------------------------
st.header("5️⃣ Vehicle Usage")
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
st.header("6️⃣ Recent Match Records")
if history:
    for r in reversed(history[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {', '.join(r['selected_vehicles'])}")
else:
    st.info("No match records yet")
