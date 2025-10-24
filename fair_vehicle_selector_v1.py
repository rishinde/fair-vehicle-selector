# fair_vehicle_selector_v1.py
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
except Exception:
    GOOGLE_SHEETS_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Team Management Data"

# -----------------------------
# Small UI helpers
# -----------------------------
def ui_success(msg): st.success(msg)
def ui_info(msg): st.info(msg)
def ui_warn(msg): st.warning(msg)
def ui_error(msg): st.error(msg)

# -----------------------------
# Google Sheets helpers
# -----------------------------
def get_gsheet_client():
    """Return a gspread client using st.secrets['gcp_service_account'] if present."""
    if not GOOGLE_SHEETS_AVAILABLE:
        ui_warn("gspread/google-auth not available in environment. Google Sheets features disabled.")
        return None
    if "gcp_service_account" not in st.secrets:
        ui_warn("No 'gcp_service_account' found in Streamlit secrets. Google Sheets disabled.")
        return None
    try:
        sa_info = st.secrets["gcp_service_account"]
        if isinstance(sa_info, str):
            sa_info = json.loads(sa_info)
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        ui_error(f"Failed to authorize Google Sheets: {e}")
        return None

def open_or_create_spreadsheet(client):
    """Open the spreadsheet if present, else create it. Handles list_spreadsheet_files returning dicts or objects."""
    try:
        try:
            sheets_meta = client.list_spreadsheet_files()
        except Exception:
            sheets_meta = []
        existing_names = []
        for item in sheets_meta:
            if isinstance(item, dict) and "name" in item:
                existing_names.append(item["name"])
            else:
                existing_names.append(getattr(item, "title", ""))
        if SHEET_NAME in existing_names:
            try:
                sh = client.open(SHEET_NAME)
            except Exception as e:
                # fallback attempt
                sh = client.open(SHEET_NAME)
        else:
            sh = client.create(SHEET_NAME)
        return sh
    except Exception as e:
        ui_error(f"Failed to open/create spreadsheet '{SHEET_NAME}': {e}")
        return None

def get_or_create_worksheet(sh, name, headers):
    """Get worksheet or create with headers."""
    try:
        try:
            ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=200, cols=20)
            ws.append_row(headers)
        # ensure headers exist if worksheet empty
        vals = ws.get_all_values()
        if not vals:
            ws.append_row(headers)
        return ws
    except Exception as e:
        ui_error(f"Failed to get/create worksheet '{name}': {e}")
        return None

# -----------------------------
# Init and load sheet data (worksheets not cached)
# -----------------------------
def init_and_load_sheet_data():
    client = get_gsheet_client()
    if not client:
        return None, None, None, None, [], [], {}, [], {}

    sh = open_or_create_spreadsheet(client)
    if not sh:
        return None, None, None, None, [], [], {}, [], {}

    ws_players = get_or_create_worksheet(sh, "Players", ["Player"])
    ws_vehicles = get_or_create_worksheet(sh, "Vehicles", ["Vehicle"])
    ws_groups = get_or_create_worksheet(sh, "VehicleGroups", ["Vehicle", "Players"])
    ws_history = get_or_create_worksheet(sh, "History", ["Date", "Ground", "Players", "Vehicles", "Message"])

    # Load serializable data
    try:
        players = [r["Player"] for r in ws_players.get_all_records()] if ws_players else []
    except Exception:
        players = []
    try:
        vehicles = [r["Vehicle"] for r in ws_vehicles.get_all_records()] if ws_vehicles else []
    except Exception:
        vehicles = []
    vehicle_groups = {}
    try:
        if ws_groups:
            for r in ws_groups.get_all_records():
                key = r.get("Vehicle", "")
                val = r.get("Players", "")
                vehicle_groups[key] = [p.strip() for p in val.split(",")] if val else []
    except Exception:
        vehicle_groups = {}

    try:
        history = ws_history.get_all_records() if ws_history else []
    except Exception:
        history = []

    # compute usage
    usage = {}
    try:
        for rec in history:
            players_field = rec.get("Players", "")
            vehicles_field = rec.get("Vehicles", "")
            if players_field:
                for p in [x.strip() for x in players_field.split(",")]:
                    if not p:
                        continue
                    usage.setdefault(p, {"used": 0, "present": 0})
                    usage[p]["present"] += 1
            if vehicles_field:
                for v in [x.strip() for x in vehicles_field.split(",")]:
                    if not v:
                        continue
                    usage.setdefault(v, {"used": 0, "present": 0})
                    usage[v]["used"] += 1
    except Exception:
        usage = {}

    return ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage

# -----------------------------
# Safe sheet operations
# -----------------------------
def safe_append_row(ws, row):
    if not ws:
        ui_warn("Worksheet unavailable for append.")
        return False
    try:
        row_str = ["" if x is None else str(x) for x in row]
        ws.append_row(row_str)
        return True
    except Exception as e:
        ui_error(f"Failed to append row to '{getattr(ws, 'title', str(ws))}': {e}")
        return False

def safe_delete_last_row(ws):
    if not ws:
        ui_warn("Worksheet unavailable for delete.")
        return False
    try:
        vals = ws.get_all_values()
        if len(vals) <= 1:
            ui_info("No data rows to delete.")
            return False
        ws.delete_row(len(vals))
        return True
    except Exception as e:
        ui_error(f"Failed to delete last row from '{getattr(ws, 'title', str(ws))}': {e}")
        return False

def safe_delete_row_by_column(ws, col_name, match_value):
    if not ws:
        ui_warn("Worksheet unavailable for delete.")
        return False
    try:
        recs = ws.get_all_records()
        for idx, r in enumerate(recs, start=2):
            if r.get(col_name) == match_value:
                ws.delete_row(idx)
                return True
        return False
    except Exception as e:
        ui_error(f"Failed to delete row in '{getattr(ws, 'title', str(ws))}': {e}")
        return False

def safe_update_group(ws_groups, vehicle, members):
    if not ws_groups:
        ui_warn("VehicleGroups worksheet unavailable.")
        return False
    try:
        recs = ws_groups.get_all_records()
        for idx, r in enumerate(recs, start=2):
            if r.get("Vehicle") == vehicle:
                ws_groups.delete_row(idx)
                break
        ws_groups.append_row([vehicle, ", ".join(members)])
        return True
    except Exception as e:
        ui_error(f"Failed to update vehicle group: {e}")
        return False

def safe_reset_all(ws_players, ws_vehicles, ws_groups, ws_history):
    for ws, headers in [
        (ws_players, ["Player"]),
        (ws_vehicles, ["Vehicle"]),
        (ws_groups, ["Vehicle", "Players"]),
        (ws_history, ["Date", "Ground", "Players", "Vehicles", "Message"])
    ]:
        if not ws:
            continue
        try:
            ws.clear()
            ws.append_row(headers)
        except Exception as e:
            ui_error(f"Failed to reset worksheet '{getattr(ws, 'title', str(ws))}': {e}")

# -----------------------------
# Vehicle selection logic
# -----------------------------
def update_usage_counts(selected_players, eligible_players, usage):
    for p in selected_players:
        usage.setdefault(p, {"used": 0, "present": 0})
        usage[p]["used"] += 1
    for p in eligible_players:
        usage.setdefault(p, {"used": 0, "present": 0})
        usage[p]["present"] += 1

def select_vehicles_auto(vehicle_set, players_today, num_needed, usage, vehicle_groups):
    selected = []
    eligible = [v for v in players_today if v in vehicle_set]
    for _ in range(num_needed):
        if not eligible:
            break
        def usage_ratio(p):
            u = usage.get(p, {"used": 0, "present": 0})
            return u["used"] / u["present"] if u["present"] > 0 else 0
        ordered = sorted(eligible, key=lambda p: (usage_ratio(p), vehicle_set.index(p)))
        pick = ordered[0]
        selected.append(pick)
        update_usage_counts([pick], eligible, usage)
        # remove group members if pick belongs to a group
        removed = False
        for members in vehicle_groups.values():
            if pick in members:
                eligible = [e for e in eligible if e not in members]
                removed = True
                break
        if not removed:
            eligible.remove(pick)
    return selected

def generate_message(game_date, ground_name, players_list, selected):
    msg = f"🏏 Match Details\n📅 Date: {game_date}\n📍 Venue: {ground_name}\n\n"
    msg += "👥 Team:\n" + "\n".join([f"- {p}" for p in players_list]) + "\n\n"
    msg += "🚗 Vehicles:\n" + "\n".join([f"- {v}" for v in selected])
    return msg

# -----------------------------
# Streamlit UI initialization
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector (stable)", page_icon="🚗", layout="wide")
st.title("🚗 Fair Vehicle Selector — stable")
st.write("Attendance-aware vehicle distribution with incremental Google Sheets persistence.")

# Admin login simple check
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    with st.expander("🔒 Admin Login (expand to sign in)"):
        txt_user = st.text_input("Username", key="login_user")
        txt_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login as Admin"):
            if txt_user == "admin" and txt_pass == "admin123":
                st.session_state.admin_logged_in = True
                ui_success("Logged in as admin.")
                st.rerun()
            else:
                ui_error("Incorrect username or password.")

# Load sheets and data once into session_state
if "ws_initialized" not in st.session_state:
    st.session_state.ws_players = None
    st.session_state.ws_vehicles = None
    st.session_state.ws_groups = None
    st.session_state.ws_history = None
    st.session_state.players = []
    st.session_state.vehicles = []
    st.session_state.vehicle_groups = {}
    st.session_state.history = []
    st.session_state.usage = {}
    st.session_state.ws_initialized = False

if not st.session_state.ws_initialized:
    ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = init_and_load_sheet_data()
    st.session_state.ws_players = ws_players
    st.session_state.ws_vehicles = ws_vehicles
    st.session_state.ws_groups = ws_groups
    st.session_state.ws_history = ws_history
    st.session_state.players = players
    st.session_state.vehicles = vehicles
    st.session_state.vehicle_groups = vehicle_groups
    st.session_state.history = history
    st.session_state.usage = usage
    st.session_state.ws_initialized = True

# local aliases
ws_players = st.session_state.ws_players
ws_vehicles = st.session_state.ws_vehicles
ws_groups = st.session_state.ws_groups
ws_history = st.session_state.ws_history
players = st.session_state.players
vehicles = st.session_state.vehicles
vehicle_groups = st.session_state.vehicle_groups
history = st.session_state.history
usage = st.session_state.usage

# -----------------------------
# Sidebar admin controls
# -----------------------------
with st.sidebar:
    st.header("⚙️ Admin Controls")
    if st.session_state.admin_logged_in:
        if st.button("🧹 Reset All Data"):
            if history or players or vehicles:
                backup_data = {
                    "Players": [{"Player": p} for p in players],
                    "Vehicles": [{"Vehicle": v} for v in vehicles],
                    "VehicleGroups": [{"Vehicle": k, "Players": ", ".join(v)} for k, v in vehicle_groups.items()],
                    "History": history
                }
                st.download_button("📥 Download Backup (before reset)", json.dumps(backup_data, indent=2),
                                   file_name=f"backup_before_reset_{date.today()}.json",
                                   mime="application/json")
            safe_reset_all(ws_players, ws_vehicles, ws_groups, ws_history)
            st.session_state.players = []
            st.session_state.vehicles = []
            st.session_state.vehicle_groups = {}
            st.session_state.history = []
            st.session_state.usage = {}
            ui_success("All data reset.")
            st.rerun()

        if st.button("↩ Undo Last Entry"):
            ok = safe_delete_last_row(ws_history)
            if ok and history:
                history.pop()
                st.session_state.history = history
            st.rerun()

        st.markdown("---")
        st.header("📂 Backup / Restore")
        if st.button("📥 Download Current Data (JSON)"):
            download_data = {
                "Players": [{"Player": p} for p in players],
                "Vehicles": [{"Vehicle": v} for v in vehicles],
                "VehicleGroups": [{"Vehicle": k, "Players": ", ".join(v)} for k, v in vehicle_groups.items()],
                "History": history
            }
            st.download_button("Download data JSON", json.dumps(download_data, indent=2),
                               file_name=f"current_data_{date.today()}.json",
                               mime="application/json")

        uploaded = st.file_uploader("Upload Backup JSON to restore", type="json")
        if uploaded:
            try:
                data = json.load(uploaded)
                safe_reset_all(ws_players, ws_vehicles, ws_groups, ws_history)
                # restore players
                for p in data.get("Players", []):
                    name = p.get("Player")
                    if name:
                        safe_append_row(ws_players, [name])
                # restore vehicles
                for v in data.get("Vehicles", []):
                    name = v.get("Vehicle")
                    if name:
                        safe_append_row(ws_vehicles, [name])
                # restore groups
                for g in data.get("VehicleGroups", []):
                    veh = g.get("Vehicle")
                    members = g.get("Players", "")
                    safe_append_row(ws_groups, [veh, members])
                # restore history
                for h in data.get("History", []):
                    date_ = h.get("date", "")
                    ground = h.get("ground", "")
                    players_present = ", ".join(h.get("players_present", [])) if isinstance(h.get("players_present", []), list) else h.get("players_present", "")
                    vehicles_sel = ", ".join(h.get("selected_vehicles", [])) if isinstance(h.get("selected_vehicles", []), list) else h.get("selected_vehicles", "")
                    msg = h.get("message", "")
                    safe_append_row(ws_history, [date_, ground, players_present, vehicles_sel, msg])
                ui_success("Backup restored to Google Sheets.")
                # reload session data
                st.session_state.ws_initialized = False
                st.rerun()
            except Exception as e:
                ui_error(f"Failed to restore backup: {e}")

    else:
        st.info("Admin-only controls. Login as admin to modify data.")

# -----------------------------
# Main UI: Players / Vehicles / Groups
# -----------------------------
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    c1, c2 = st.columns([3,1])
    with c1:
        new_player = st.text_input("Add new player", key="new_player_input")
    with c2:
        if st.button("Add Player"):
            if not new_player:
                ui_warn("Enter a valid name.")
            elif new_player in players:
                ui_warn("Player already exists.")
            else:
                ok = safe_append_row(ws_players, [new_player])
                if ok:
                    players.append(new_player)
                    st.session_state.players = players
                    ui_success(f"Added player '{new_player}'.")
                    st.rerun()

    if players:
        rem = st.selectbox("Remove a player", ["None"] + players, key="remove_player_select")
        if st.button("Remove Player"):
            if rem == "None":
                ui_info("Select a player to remove.")
            else:
                ok = safe_delete_row_by_column(ws_players, "Player", rem)
                if ok:
                    if rem in players:
                        players.remove(rem)
                        st.session_state.players = players
                    ui_success(f"Removed player '{rem}'.")
                    # Also remove vehicle if same name
                    if rem in vehicles:
                        safe_delete_row_by_column(ws_vehicles, "Vehicle", rem)
                        vehicles.remove(rem)
                        st.session_state.vehicles = vehicles
                    st.rerun()

st.write("**Current Players:**", ", ".join(players) if players else "No players defined.")

st.markdown("---")
st.header("2️⃣ Vehicle Set (subset of players)")
if st.session_state.admin_logged_in:
    c3, c4 = st.columns([3,1])
    with c3:
        new_vehicle = st.text_input("Add vehicle owner (must exist in players)", key="new_vehicle_input")
    with c4:
        if st.button("Add Vehicle"):
            if not new_vehicle:
                ui_warn("Enter a valid name.")
            elif new_vehicle not in players:
                ui_warn("Vehicle owner must be in players list.")
            elif new_vehicle in vehicles:
                ui_warn("Vehicle already exists.")
            else:
                ok = safe_append_row(ws_vehicles, [new_vehicle])
                if ok:
                    vehicles.append(new_vehicle)
                    st.session_state.vehicles = vehicles
                    ui_success(f"Added vehicle owner '{new_vehicle}'.")
                    st.rerun()

    if vehicles:
        remv = st.selectbox("Remove a vehicle owner", ["None"] + vehicles, key="remove_vehicle_select")
        if st.button("Remove Vehicle"):
            if remv == "None":
                ui_info("Select a vehicle owner to remove.")
            else:
                ok = safe_delete_row_by_column(ws_vehicles, "Vehicle", remv)
                if ok:
                    if remv in vehicles:
                        vehicles.remove(remv)
                        st.session_state.vehicles = vehicles
                    ui_success(f"Removed vehicle owner '{remv}'.")
                    st.rerun()

st.write("**Current Vehicle Owners:**", ", ".join(vehicles) if vehicles else "No vehicle owners defined.")

st.markdown("---")
st.header("3️⃣ Vehicle Groups (players sharing same vehicle)")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle owner to define group for", [""] + vehicles, key="vg_vehicle_select")
    vg_members = st.multiselect("Select players (group) who share the same vehicle", players, key="vg_members_select")
    if st.button("Add/Update Vehicle Group"):
        if not vg_vehicle:
            ui_warn("Choose a vehicle owner.")
        else:
            ok = safe_update_group(ws_groups, vg_vehicle, vg_members)
            if ok:
                vehicle_groups[vg_vehicle] = vg_members
                st.session_state.vehicle_groups = vehicle_groups
                ui_success(f"Group updated for '{vg_vehicle}'.")
                st.rerun()

st.write("**Current Vehicle Groups:**")
if vehicle_groups:
    for k, v in vehicle_groups.items():
        st.write(f"- {k}: {', '.join(v) if v else '(no members)'}")
else:
    st.write("No groups defined.")

# -----------------------------
# Daily Match Selection
# -----------------------------
st.markdown("---")
st.header("4️⃣ Daily Match Selection")
if not st.session_state.admin_logged_in:
    st.info("Daily match selection is admin-only. Login as admin to proceed.")
else:
    game_date = st.date_input("Select match date", value=date.today())
    ground_name = st.text_input("Ground name", key="ground_name")
    players_today = st.multiselect("Select players present today", players, key="players_today_multi")

    max_vehicles = len(vehicles) if vehicles else 1
    num_needed = st.number_input("Number of vehicles needed", min_value=1, max_value=max_vehicles, value=1, step=1)

    selection_mode = st.radio("Vehicle selection mode", ["Auto-Select", "Manual-Select"], index=0, key="sel_mode")
    manual_selected = []
    if selection_mode == "Manual-Select":
        manual_selected = st.multiselect("Manual select vehicle owners", vehicles, key="manual_select_vehicles")

    if st.button("Select Vehicles for Match"):
        eligible = [v for v in players_today if v in vehicles]
        if not eligible:
            ui_warn("No eligible vehicle owners present among selected players.")
        else:
            if selection_mode == "Auto-Select":
                selected = select_vehicles_auto(vehicles, players_today, num_needed, usage, vehicle_groups)
            else:
                if len(manual_selected) != num_needed:
                    ui_warn(f"Please select exactly {num_needed} vehicles in Manual mode.")
                    selected = []
                else:
                    selected = manual_selected
                    update_usage_counts(selected, eligible, usage)
            if not selected:
                ui_warn("No vehicles selected.")
            else:
                swap_options = ["None"] + [v for v in vehicles if v not in selected]
                swap_choice = st.selectbox("If emergency, change LAST selected vehicle to:", swap_options, key="swap_select")
                if swap_choice and swap_choice != "None":
                    replaced = selected[-1]
                    selected[-1] = swap_choice
                    ui_info(f"Replaced {replaced} with {swap_choice} for this match.")

                message = generate_message(game_date, ground_name, players_today, selected)
                st.subheader("📋 Copy-ready message")
                st.text_area("Match Details (copy-paste ready)", message, height=260)

                record = {
                    "date": str(game_date),
                    "ground": ground_name,
                    "players_present": players_today,
                    "selected_vehicles": selected,
                    "message": message
                }
                ok = safe_append_row(ws_history, [record["date"], record["ground"], ", ".join(record["players_present"]), ", ".join(record["selected_vehicles"]), record["message"]])
                if ok:
                    history.append(record)
                    st.session_state.history = history
                    update_usage_counts(selected, eligible, usage)
                    st.session_state.usage = usage
                    ui_success(f"Vehicles selected and recorded: {', '.join(selected)}")
                    st.rerun()

# -----------------------------
# Usage Table & Chart
# -----------------------------
st.markdown("---")
st.header("6️⃣ Vehicle Usage")
if usage:
    df_usage = pd.DataFrame([{"Player": k, "Used": v["used"], "Present": v["present"],
                              "Ratio": (v["used"] / v["present"]) if v["present"] > 0 else 0.0}
                             for k, v in usage.items()])
    df_usage = df_usage.sort_values(by="Ratio", ascending=False).reset_index(drop=True)
    st.dataframe(df_usage, use_container_width=True)
    fig = px.bar(df_usage, x="Player", y="Ratio", text="Used", title="Player Vehicle Usage Fairness")
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No usage data available yet.")

# -----------------------------
# Recent Match Records
# -----------------------------
st.markdown("---")
st.header("7️⃣ Recent Match Records")
if history:
    for rec in reversed(history[-10:]):
        date_s = rec.get("date", "")
        ground_s = rec.get("ground", "")
        vehicles_s = ", ".join(rec.get("selected_vehicles", [])) if isinstance(rec.get("selected_vehicles", []), list) else rec.get("selected_vehicles", "")
        st.write(f"📅 {date_s} — {ground_s} — 🚗 {vehicles_s}")
else:
    st.info("No match records yet.")

# Footer
st.markdown("---")
st.write("Notes:")
st.write("- Admin login required to add/remove players, vehicles, groups, and to make selections.")
st.write("- The app writes minimal rows to Google Sheets to reduce quota usage (incremental pattern).")
st.write("- If Sheets operations fail, check the service account in Streamlit secrets and Sheets API quotas/permissions.")
