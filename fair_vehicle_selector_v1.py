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
# App State
# -----------------------------
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if "players" not in st.session_state:
    st.session_state.players = []
if "vehicles" not in st.session_state:
    st.session_state.vehicles = []
if "vehicle_groups" not in st.session_state:
    st.session_state.vehicle_groups = {}
if "history" not in st.session_state:
    st.session_state.history = []
if "usage" not in st.session_state:
    st.session_state.usage = {}

# -----------------------------
# Helper Functions
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
    if not history:
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
# Admin Sidebar
# -----------------------------
if st.session_state.admin_logged_in:
    st.sidebar.header("⚙️ Admin Controls")
    
    if st.sidebar.button("🧹 Reset All Data"):
        st.session_state.players = []
        st.session_state.vehicles = []
        st.session_state.vehicle_groups = {}
        st.session_state.history = []
        st.session_state.usage = {}
        st.success("✅ All data reset")

    if st.sidebar.button("↩ Undo Last Entry"):
        st.session_state.history, st.session_state.usage, undone = undo_last_entry(st.session_state.history, st.session_state.usage)
        if undone:
            st.success("✅ Last entry removed")
        else:
            st.info("ℹ️ No record to undo")

    # Google Sheets
    st.sidebar.header("📂 Google Sheets & Backup")
    if st.sidebar.button("💾 Push All Data to Google Sheets"):
        push_to_google_sheet(st.session_state.players, st.session_state.vehicles, st.session_state.vehicle_groups, st.session_state.history)
    if st.sidebar.button("📥 Download All Data from Google Sheets"):
        data = download_from_google_sheet()
        if data:
            st.sidebar.download_button("Download JSON Backup", json.dumps(data, indent=4), "backup.json", "application/json")
    upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
    if upload_file:
        data = json.load(upload_file)
        st.session_state.players = [p["Player"] for p in data.get("Players",[])]
        st.session_state.vehicles = [v["Vehicle"] for v in data.get("Vehicles",[])]
        st.session_state.vehicle_groups = {g["Vehicle"]: g["Players"].split(", ") for g in data.get("VehicleGroups",[])}
        st.session_state.history = data.get("History",[])
        st.session_state.usage = {}
        for record in st.session_state.history:
            for p in record.get("players_present",[]):
                if p not in st.session_state.usage:
                    st.session_state.usage[p] = {"used":0,"present":0}
                st.session_state.usage[p]["present"] +=1
            for v in record.get("selected_vehicles",[]):
                if v not in st.session_state.usage:
                    st.session_state.usage[v] = {"used":0,"present":0}
                st.session_state.usage[v]["used"] +=1
        st.success("✅ Data restored from backup JSON")
    if st.sidebar.button("🗑 Reset Google Sheet"):
        reset_google_sheet()
    if st.sidebar.button("🔄 Load Data from Google Sheet"):
        players, vehicles, vehicle_groups, history, usage = load_from_google_sheet()
        st.session_state.players = players
        st.session_state.vehicles = vehicles
        st.session_state.vehicle_groups = vehicle_groups
        st.session_state.history = history
        st.session_state.usage = usage

# -----------------------------
# Main UI
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with admin control and vehicle grouping")

# --- Admin Login ---
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

# --- Players Superset ---
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_players = st.text_area("Add new players (comma-separated):")
    if st.button("Add Players"):
        for np in [p.strip() for p in new_players.split(",") if p.strip()]:
            if np not in st.session_state.players:
                st.session_state.players.append(np)
    remove_player = st.selectbox("Remove a player:", ["None"] + st.session_state.players)
    if remove_player != "None" and st.button("Remove Player"):
        st.session_state.players.remove(remove_player)
st.write("**Current Players:**", ", ".join(st.session_state.players))

# --- Vehicle Set ---
st.header("2️⃣ Vehicle Set (subset of players)")
if st.session_state.admin_logged_in:
    new_vehicles = st.text_area("Add vehicle owners (comma-separated from players):")
    if st.button("Add Vehicles"):
        for nv in [v.strip() for v in new_vehicles.split(",") if v.strip()]:
            if nv in st.session_state.players and nv not in st.session_state.vehicles:
                st.session_state.vehicles.append(nv)
    remove_vehicle = st.selectbox("Remove vehicle owner:", ["None"] + st.session_state.vehicles)
    if remove_vehicle != "None" and st.button("Remove Vehicle"):
        st.session_state.vehicles.remove(remove_vehicle)
st.write("**Current Vehicle Owners:**", ", ".join(st.session_state.vehicles))

# --- Vehicle Groups ---
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + st.session_state.vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", st.session_state.players)
    if st.button("Add/Update Vehicle Group"):
        if vg_vehicle:
            st.session_state.vehicle_groups[vg_vehicle] = vg_members
st.write("**Current Vehicle Groups:**")
if st.session_state.vehicle_groups:
    for v, members in st.session_state.vehicle_groups.items():
        st.write(f"{v}: {', '.join(members)}")
else:
    st.write("No vehicle groups defined.")

# --- Daily Match Selection ---
st.header("4️⃣ Daily Match Selection")
if st.session_state.admin_logged_in:
    game_date = st.date_input("Select date:", value=date.today())
    ground_name = st.text_input("Ground name:")
    players_today = st.multiselect("Select players present today:", st.session_state.players)
    num_needed = st.number_input("Number of vehicles needed:", 1, len(st.session_state.vehicles) if st.session_state.vehicles else 1, 1)
    selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"], key="mode")
    
    if selection_mode == "Manual-Select":
        manual_selected = st.multiselect("Select vehicles manually:", st.session_state.vehicles, [])
    else:
        manual_selected = []

    if st.button("Select Vehicles"):
        eligible = [v for v in players_today if v in st.session_state.vehicles]

        if selection_mode=="Auto-Select":
            selected = select_vehicles_auto(st.session_state.vehicles, players_today, num_needed, st.session_state.usage, st.session_state.vehicle_groups)
        else:
            if len(manual_selected) != num_needed:
                st.warning(f"⚠️ Please select exactly {num_needed} vehicles")
                selected = []
            else:
                selected = manual_selected
                update_usage(selected, eligible, st.session_state.usage)

        if selected:
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")
            msg = generate_message(game_date, ground_name, players_today, selected)
            st.subheader("📋 Copy-Ready Message")
            st.text_area("Message:", msg, height=200)
            st.session_state.history.append({"date": str(game_date), "ground": ground_name, "players_present": players_today, "selected_vehicles": selected, "message": msg})

# --- Usage Table & Chart ---
st.header("5️⃣ Vehicle Usage")
if st.session_state.usage:
    df_usage = pd.DataFrame([{"Player": k, "Used": v["used"], "Present": v["present"], "Ratio": v["used"]/v["present"] if v["present"]>0 else 0} for k,v in st.session_state.usage.items()])
    st.table(df_usage)
    fig = px.bar(df_usage, x="Player", y="Ratio", text="Used", title="Player Vehicle Usage Fairness")
    fig.update_traces(textposition='outside')
    fig.update_layout(yaxis=dict(range=[0,1.2]))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No usage data yet")

# --- Recent Match Records ---
st.header("6️⃣ Recent Match Records")
if st.session_state.history:
    for r in reversed(st.session_state.history[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {', '.join(r['selected_vehicles'])}")
else:
    st.info("No match records yet")
