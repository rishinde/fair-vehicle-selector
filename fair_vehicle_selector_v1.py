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

def open_or_create_sheet(client, sheet_name):
    try:
        sh_list = client.list_spreadsheet_files()
        sheet_titles = [s['name'] for s in sh_list]
        if sheet_name in sheet_titles:
            sh = client.open(sheet_name)
        else:
            sh = client.create(sheet_name)
        return sh
    except Exception as e:
        st.error(f"Failed to open or create spreadsheet: {e}")
        return None

def get_or_create_ws(sh, name, headers):
    try:
        try:
            ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(name, rows=100, cols=20)
            ws.append_row(headers)
        return ws
    except Exception as e:
        st.error(f"Failed to access worksheet '{name}': {e}")
        return None

def safe_append_row(ws, values):
    try:
        ws.append_row(values)
    except Exception as e:
        st.error(f"Failed to append row in '{ws.title}': {e}")

def safe_delete_row(ws, index):
    try:
        ws.delete_rows(index)
    except AttributeError:
        # fallback for new gspread versions
        try:
            ws.delete_row(index)
        except Exception as e:
            st.error(f"Failed to delete row in '{ws.title}': {e}")
    except Exception as e:
        st.error(f"Failed to delete row in '{ws.title}': {e}")

# -----------------------------
# Data Loading & Caching
# -----------------------------
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

if "ws_players" not in st.session_state:
    st.session_state.ws_players = None
if "ws_vehicles" not in st.session_state:
    st.session_state.ws_vehicles = None
if "ws_groups" not in st.session_state:
    st.session_state.ws_groups = None
if "ws_history" not in st.session_state:
    st.session_state.ws_history = None

client = get_gsheet_client()
if client:
    sh = open_or_create_sheet(client, SHEET_NAME)
    if sh:
        st.session_state.ws_players = get_or_create_ws(sh, "Players", ["Player"])
        st.session_state.ws_vehicles = get_or_create_ws(sh, "Vehicles", ["Vehicle"])
        st.session_state.ws_groups = get_or_create_ws(sh, "VehicleGroups", ["Vehicle","Players"])
        st.session_state.ws_history = get_or_create_ws(sh, "History", ["Date","Ground","Players","Vehicles","Message"])

        # Load Players
        try:
            records = st.session_state.ws_players.get_all_records()
            st.session_state.players = [r["Player"] for r in records]
        except:
            st.session_state.players = []

        # Load Vehicles
        try:
            records = st.session_state.ws_vehicles.get_all_records()
            st.session_state.vehicles = [r["Vehicle"] for r in records]
        except:
            st.session_state.vehicles = []

        # Load Vehicle Groups
        try:
            records = st.session_state.ws_groups.get_all_records()
            st.session_state.vehicle_groups = {r["Vehicle"]: r["Players"].split(", ") for r in records}
        except:
            st.session_state.vehicle_groups = {}

        # Load History
        try:
            st.session_state.history = st.session_state.ws_history.get_all_records()
        except:
            st.session_state.history = []

# -----------------------------
# Helper Functions
# -----------------------------
def update_usage(selected_players, eligible_players):
    for p in selected_players:
        if p not in st.session_state.usage:
            st.session_state.usage[p] = {"used":0,"present":0}
        st.session_state.usage[p]["used"] += 1
    for p in eligible_players:
        if p not in st.session_state.usage:
            st.session_state.usage[p] = {"used":0,"present":0}
        st.session_state.usage[p]["present"] +=1

def select_vehicles_auto(vehicle_set, players_today, num_needed):
    selected = []
    eligible = [v for v in players_today if v in vehicle_set]
    for _ in range(num_needed):
        if not eligible:
            break
        def usage_ratio(p):
            u = st.session_state.usage.get(p, {"used":0,"present":0})
            return u["used"]/u["present"] if u["present"]>0 else 0
        ordered = sorted(eligible, key=lambda p: (usage_ratio(p), vehicle_set.index(p)))
        pick = ordered[0]
        selected.append(pick)
        update_usage([pick], eligible)
        # Remove grouped players
        for members in st.session_state.vehicle_groups.values():
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

def reset_all_data():
    backup_data = {
        "Players":[{"Player":p} for p in st.session_state.players],
        "Vehicles":[{"Vehicle":v} for v in st.session_state.vehicles],
        "VehicleGroups":[{"Vehicle":k,"Players":", ".join(v)} for k,v in st.session_state.vehicle_groups.items()],
        "History":st.session_state.history
    }
    st.download_button(
        "📥 Download Backup Before Reset",
        json.dumps(backup_data, indent=4),
        file_name=f"backup_before_reset_{date.today()}.json",
        mime="application/json"
    )
    for ws in [st.session_state.ws_players, st.session_state.ws_vehicles,
               st.session_state.ws_groups, st.session_state.ws_history]:
        if ws:
            try:
                ws.clear()
            except:
                pass
    st.session_state.players.clear()
    st.session_state.vehicles.clear()
    st.session_state.vehicle_groups.clear()
    st.session_state.history.clear()
    st.session_state.usage.clear()
    st.success("✅ All data reset")

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

# -----------------------------
# Sidebar Admin Controls
# -----------------------------
if st.session_state.admin_logged_in:
    st.sidebar.header("⚙️ Admin Controls")
    if st.sidebar.button("🧹 Reset All Data"):
        reset_all_data()
        st.experimental_rerun()

    if st.sidebar.button("↩ Undo Last Entry"):
        if st.session_state.history and st.session_state.ws_history:
            safe_delete_row(st.session_state.ws_history, len(st.session_state.history)+1)
            st.session_state.history.pop()
            st.success("✅ Last entry undone")
            st.experimental_rerun()

    st.sidebar.header("📂 Backup")
    if st.sidebar.button("📥 Download JSON Backup"):
        data = {
            "Players":[{"Player":p} for p in st.session_state.players],
            "Vehicles":[{"Vehicle":v} for v in st.session_state.vehicles],
            "VehicleGroups":[{"Vehicle":k,"Players":", ".join(v)} for k,v in st.session_state.vehicle_groups.items()],
            "History":st.session_state.history
        }
        st.download_button("Download JSON Backup", json.dumps(data, indent=4), "backup.json", "application/json")

    upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
    if upload_file:
        data = json.load(upload_file)
        # Clear existing
        reset_all_data()
        # Restore
        for p in data.get("Players",[]):
            st.session_state.players.append(p["Player"])
            if st.session_state.ws_players:
                safe_append_row(st.session_state.ws_players,[p["Player"]])
        for v in data.get("Vehicles",[]):
            st.session_state.vehicles.append(v["Vehicle"])
            if st.session_state.ws_vehicles:
                safe_append_row(st.session_state.ws_vehicles,[v["Vehicle"]])
        for g in data.get("VehicleGroups",[]):
            st.session_state.vehicle_groups[g["Vehicle"]] = g["Players"].split(", ")
            if st.session_state.ws_groups:
                safe_append_row(st.session_state.ws_groups,[g["Vehicle"],g["Players"]])
        for h in data.get("History",[]):
            st.session_state.history.append(h)
            if st.session_state.ws_history:
                safe_append_row(st.session_state.ws_history,[h["date"],h["ground"],", ".join(h["players_present"]),", ".join(h["selected_vehicles"]),h["message"]])
        st.success("✅ Data restored from backup")
        st.experimental_rerun()

# -----------------------------
# Main UI Sections
# -----------------------------
# 1️⃣ Players Superset
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    new_player = st.text_input("Add new player:")
    if st.button("Add Player"):
        if new_player and new_player not in st.session_state.players:
            st.session_state.players.append(new_player)
            if st.session_state.ws_players:
                safe_append_row(st.session_state.ws_players,[new_player])
            st.success(f"✅ Added player: {new_player}")
            st.experimental_rerun()
    if st.session_state.players:
        remove_player_name = st.selectbox("Remove a player:", ["None"]+st.session_state.players)
        if remove_player_name!="None" and st.button("Remove Player"):
            st.session_state.players.remove(remove_player_name)
            if st.session_state.ws_players:
                # Delete row by searching
                records = st.session_state.ws_players.get_all_records()
                for idx, r in enumerate(records, start=2):
                    if r["Player"]==remove_player_name:
                        safe_delete_row(st.session_state.ws_players, idx)
                        break
            st.success(f"🗑️ Removed player: {remove_player_name}")
            st.experimental_rerun()
st.write("**Current Players:**", ", ".join(st.session_state.players))

# 2️⃣ Vehicle Set
st.header("2️⃣ Vehicle Set")
if st.session_state.admin_logged_in:
    new_vehicle = st.text_input("Add vehicle owner:")
    if st.button("Add Vehicle"):
        if new_vehicle in st.session_state.players and new_vehicle not in st.session_state.vehicles:
            st.session_state.vehicles.append(new_vehicle)
            if st.session_state.ws_vehicles:
                safe_append_row(st.session_state.ws_vehicles,[new_vehicle])
            st.success(f"✅ Added vehicle owner: {new_vehicle}")
            st.experimental_rerun()
        else:
            st.warning("⚠️ Player must exist and not already be a vehicle owner")
    if st.session_state.vehicles:
        remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"]+st.session_state.vehicles)
        if remove_vehicle_name!="None" and st.button("Remove Vehicle"):
            st.session_state.vehicles.remove(remove_vehicle_name)
            if st.session_state.ws_vehicles:
                records = st.session_state.ws_vehicles.get_all_records()
                for idx, r in enumerate(records, start=2):
                    if r["Vehicle"]==remove_vehicle_name:
                        safe_delete_row(st.session_state.ws_vehicles, idx)
                        break
            st.success(f"🗑️ Removed vehicle owner: {remove_vehicle_name}")
            st.experimental_rerun()
st.write("**Current Vehicle Owners:**", ", ".join(st.session_state.vehicles))

# 3️⃣ Vehicle Groups
st.header("3️⃣ Vehicle Groups")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + st.session_state.vehicles)
    vg_members = st.multiselect("Select players sharing this vehicle", st.session_state.players)
    if st.button("Add/Update Vehicle Group"):
        if vg_vehicle:
            st.session_state.vehicle_groups[vg_vehicle] = vg_members
            if st.session_state.ws_groups:
                # Remove old row
                records = st.session_state.ws_groups.get_all_records()
                for idx, r in enumerate(records, start=2):
                    if r["Vehicle"]==vg_vehicle:
                        safe_delete_row(st.session_state.ws_groups, idx)
                        break
                safe_append_row(st.session_state.ws_groups,[vg_vehicle, ", ".join(vg_members)])
            st.success(f"✅ Group updated for {vg_vehicle}")
st.write("**Current Vehicle Groups:**")
if st.session_state.vehicle_groups:
    for v, members in st.session_state.vehicle_groups.items():
        st.write(f"{v}: {', '.join(members)}")
else:
    st.write("No vehicle groups defined.")

# 4️⃣ Daily Match Selection
st.header("4️⃣ Daily Match Selection")
if st.session_state.admin_logged_in:
    game_date = st.date_input("Select date:", value=date.today())
    ground_name = st.text_input("Ground name:")
    players_today = st.multiselect("Select players present today:", st.session_state.players)
    num_needed = st.number_input("Number of vehicles needed:", 1, len(st.session_state.vehicles) if st.session_state.vehicles else 1, 1)
    selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"], key="mode")
    
    if selection_mode == "Manual-Select":
        manual_selected = st.multiselect("Select vehicles manually:", st.session_state.vehicles, default=[])
    else:
        manual_selected = []

    if st.button("Select Vehicles"):
        eligible = [v for v in players_today if v in st.session_state.vehicles]
        if selection_mode=="Auto-Select":
            selected = select_vehicles_auto(st.session_state.vehicles, players_today, num_needed)
        else:
            if len(manual_selected) != num_needed:
                st.warning(f"⚠️ Select exactly {num_needed} vehicles")
                selected = []
            else:
                selected = manual_selected
                update_usage(selected, eligible)
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
            st.session_state.history.append(record)
            if st.session_state.ws_history:
                safe_append_row(st.session_state.ws_history,[record["date"], record["ground"], ", ".join(record["players_present"]), ", ".join(record["selected_vehicles"]), record["message"]])
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")
            st.experimental_rerun()

# 6️⃣ Usage Table & Chart
st.header("6️⃣ Vehicle Usage")
if st.session_state.usage:
    df_usage = pd.DataFrame([
        {"Player": k, "Used": v["used"], "Present": v["present"], "Ratio": v["used"]/v["present"] if v["present"]>0 else 0}
        for k,v in st.session_state.usage.items()
    ])
    st.table(df_usage)
    fig = px.bar(df_usage, x="Player", y="Ratio", text="Used", title="Player Vehicle Usage Fairness")
    st.plotly_chart(fig)
else:
    st.write("Usage data not available yet.")

# 7️⃣ Recent Match History
st.header("7️⃣ Recent Match History")
if st.session_state.history:
    for r in reversed(st.session_state.history[-10:]):
        st.write(f"📅 {r['date']} | 🏟 {r['ground']} | 👥 {', '.join(r['players_present'])} | 🚗 {', '.join(r['selected_vehicles'])}")
else:
    st.write("No match history available.")
