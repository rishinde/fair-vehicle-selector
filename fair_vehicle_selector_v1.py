# fair_vehicle_selector_stable.py
import streamlit as st
import json
from datetime import date
import pandas as pd
import plotly.express as px

# Google Sheets integration (optional)
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

# Google scopes and sheet name
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Team Management Data"

# -----------------------------
# Utility: user-friendly messaging
# -----------------------------
def ui_success(msg): st.success(msg)
def ui_info(msg): st.info(msg)
def ui_warn(msg): st.warning(msg)
def ui_error(msg): st.error(msg)

# -----------------------------
# Google Sheets helpers
# -----------------------------
def get_gsheet_client():
    """Return authorized gspread client using st.secrets['gcp_service_account'] if present."""
    if not GOOGLE_SHEETS_AVAILABLE:
        ui_warn("gspread/google-auth not installed. Google Sheets features are disabled.")
        return None
    if "gcp_service_account" not in st.secrets:
        ui_warn("No Google Cloud service account found in Streamlit secrets. Google Sheets disabled.")
        return None
    try:
        sa_info = st.secrets["gcp_service_account"]
        if isinstance(sa_info, str):
            sa_info = json.loads(sa_info)
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        ui_error(f"Failed to create Google Sheets client: {e}")
        return None

def open_or_create_spreadsheet(client):
    """Open existing spreadsheet by name or create it. Handles both dict and object returns."""
    try:
        # client.list_spreadsheet_files() may return list of dicts or list of objects depending on gspread version
        sheets_meta = []
        try:
            sheets_meta = client.list_spreadsheet_files()
        except Exception:
            # fallback to empty list
            sheets_meta = []
        existing_names = []
        for item in sheets_meta:
            if isinstance(item, dict) and "name" in item:
                existing_names.append(item["name"])
            else:
                # object-like (older gspread) may have title attribute
                existing_names.append(getattr(item, "title", ""))
        if SHEET_NAME in existing_names:
            try:
                sh = client.open(SHEET_NAME)
            except Exception as e:
                # sometimes opening by name fails; try search by id
                sh = client.open(SHEET_NAME)
        else:
            sh = client.create(SHEET_NAME)
        return sh
    except Exception as e:
        ui_error(f"Failed to open/create spreadsheet '{SHEET_NAME}': {e}")
        return None

def get_or_create_worksheet(sh, name, headers):
    """Get or create worksheet; ensure headers exist if newly created."""
    try:
        try:
            ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=200, cols=20)
            ws.append_row(headers)
        # If worksheet exists but empty, ensure headers
        values = ws.get_all_values()
        if not values:
            ws.append_row(headers)
        return ws
    except Exception as e:
        ui_error(f"Failed to get/create worksheet '{name}': {e}")
        return None

# -----------------------------
# Load / initialize sheet data (no caching of worksheets)
# -----------------------------
def init_and_load_sheet_data():
    """Initialize worksheets and load serializable data into session_state (players/vehicles/groups/history/usage)."""
    client = get_gsheet_client()
    if not client:
        # no sheets available; initialize empty in-memory structures
        return None, None, None, None, [], [], {}, [], {}

    sh = open_or_create_spreadsheet(client)
    if not sh:
        return None, None, None, None, [], [], {}, [], {}

    ws_players = get_or_create_worksheet(sh, "Players", ["Player"])
    ws_vehicles = get_or_create_worksheet(sh, "Vehicles", ["Vehicle"])
    ws_groups = get_or_create_worksheet(sh, "VehicleGroups", ["Vehicle", "Players"])
    ws_history = get_or_create_worksheet(sh, "History", ["Date", "Ground", "Players", "Vehicles", "Message"])

    # Read serializable data
    try:
        players = [r["Player"] for r in ws_players.get_all_records()] if ws_players else []
        vehicles = [r["Vehicle"] for r in ws_vehicles.get_all_records()] if ws_vehicles else []
        vehicle_groups = {}
        if ws_groups:
            for r in ws_groups.get_all_records():
                key = r.get("Vehicle", "")
                val = r.get("Players", "")
                # handle empty string
                vehicle_groups[key] = [p.strip() for p in val.split(",")] if val else []
        history = ws_history.get_all_records() if ws_history else []

        # compute usage (present/used) from history
        usage = {}
        for rec in history:
            players_field = rec.get("Players", "")
            vehicles_field = rec.get("Vehicles", "")
            # players present increment
            for p in [x.strip() for x in players_field.split(",")] if players_field else []:
                if not p:
                    continue
                usage.setdefault(p, {"used": 0, "present": 0})
                usage[p]["present"] += 1
            # vehicles (owners) used increment
            for v in [x.strip() for x in vehicles_field.split(",")] if vehicles_field else []:
                if not v:
                    continue
                usage.setdefault(v, {"used": 0, "present": 0})
                usage[v]["used"] += 1

        return ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage
    except Exception as e:
        ui_error(f"Failed to read data from worksheets: {e}")
        return ws_players, ws_vehicles, ws_groups, ws_history, [], [], {}, [], {}

# -----------------------------
# Safe operations (minimal API usage)
# -----------------------------
def safe_append_row(ws, row):
    """Append a row (list of strings) safely with user-friendly errors."""
    if not ws:
        ui_warn("Worksheet unavailable for append.")
        return False
    try:
        # convert all to str
        r = ["" if x is None else str(x) for x in row]
        ws.append_row(r)
        return True
    except Exception as e:
        ui_error(f"Failed to append row to sheet '{ws.title}': {e}")
        return False

def safe_delete_last_row(ws):
    """Delete last row if present."""
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
        ui_error(f"Failed to delete last row from '{ws.title}': {e}")
        return False

def safe_delete_row_by_match(ws, key_col_name, key_value):
    """Delete first row where column key_col_name equals key_value (case-sensitive)."""
    if not ws:
        ui_warn("Worksheet unavailable for delete.")
        return False
    try:
        records = ws.get_all_records()
        for idx, rec in enumerate(records, start=2):  # 1-based + header
            if rec.get(key_col_name) == key_value:
                ws.delete_row(idx)
                return True
        return False
    except Exception as e:
        ui_error(f"Failed to delete row in '{ws.title}': {e}")
        return False

def safe_update_group(ws_groups, vehicle, members):
    """Replace existing group for vehicle or append if not present."""
    if not ws_groups:
        ui_warn("VehicleGroups worksheet unavailable.")
        return False
    try:
        # delete existing row if any
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
    """Clear all worksheets and re-add headers (if possible)."""
    for ws, headers in [(ws_players, ["Player"]), (ws_vehicles, ["Vehicle"]),
                        (ws_groups, ["Vehicle", "Players"]), (ws_history, ["Date", "Ground", "Players", "Vehicles", "Message"])]:
        if not ws:
            continue
        try:
            ws.clear()
            ws.append_row(headers)
        except Exception as e:
            ui_error(f"Failed to reset worksheet '{getattr(ws, 'title', str(ws))}': {e}")

# -----------------------------
# Vehicle selection logic (unchanged behavior)
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
        # exclude entire group members if pick belongs to one
        excluded = False
        for members in vehicle_groups.values():
            if pick in members:
                eligible = [e for e in eligible if e not in members]
                excluded = True
                break
        if not excluded:
            eligible.remove(pick)
    return selected

def generate_message(game_date, ground_name, players_list, selected):
    msg = f"🏏 Match Details\n📅 Date: {game_date}\n📍 Venue: {ground_name}\n\n"
    msg += "👥 Team:\n" + "\n".join([f"- {p}" for p in players_list]) + "\n\n"
    msg += "🚗 Vehicles:\n" + "\n".join([f"- {v}" for v in selected])
    return msg

# -----------------------------
# Streamlit UI & state init
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector (stable v1.0)", page_icon="🚗", layout="wide")
st.title("🚗 Fair Vehicle Selector — stable v1.0")
st.write("Attendance-aware, fair vehicle distribution with incremental Google Sheets persistence.")

# Admin login (simple)
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    with st.expander("🔒 Admin Login (expand to sign in)"):
        u = st.text_input("Username", key="login_user")
        p = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login as Admin"):
            if u == "admin" and p == "admin123":
                st.session_state.admin_logged_in = True
                ui_success("Logged in as admin.")
                st.experimental_rerun()
            else:
                ui_error("Incorrect username or password.")

# Initialize worksheet objects and load data once
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

# Try to initialize once
if not st.session_state.ws_initialized:
    client = get_gsheet_client()
    if client:
        ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = init_and_load_sheet_data()
        # store worksheets and data in session_state (worksheets stored as objects, but we didn't cache them)
        st.session_state.ws_players = ws_players
        st.session_state.ws_vehicles = ws_vehicles
        st.session_state.ws_groups = ws_groups
        st.session_state.ws_history = ws_history
        st.session_state.players = players
        st.session_state.vehicles = vehicles
        st.session_state.vehicle_groups = vehicle_groups
        st.session_state.history = history
        st.session_state.usage = usage
    else:
        # No client: keep empty lists already created
        st.session_state.players = st.session_state.players or []
        st.session_state.vehicles = st.session_state.vehicles or []
        st.session_state.vehicle_groups = st.session_state.vehicle_groups or {}
        st.session_state.history = st.session_state.history or []
        st.session_state.usage = st.session_state.usage or {}
    st.session_state.ws_initialized = True

# aliases for readability
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
# Sidebar admin controls (Reset/Undo/Backup/Upload)
# -----------------------------
with st.sidebar:
    st.header("⚙️ Admin Controls")
    if st.session_state.admin_logged_in:
        # Reset All Data (download backup automatically)
        if st.button("🧹 Reset All Data"):
            if history or players or vehicles:
                backup = {
                    "Players": [{"Player": p} for p in players],
                    "Vehicles": [{"Vehicle": v} for v in vehicles],
                    "VehicleGroups": [{"Vehicle": k, "Players": ", ".join(v)} for k, v in vehicle_groups.items()],
                    "History": history
                }
                st.download_button("📥 Download Backup (before reset)", json.dumps(backup, indent=2),
                                   file_name=f"backup_before_reset_{date.today()}.json",
                                   mime="application/json")
            safe_reset_all(ws_players, ws_vehicles, ws_groups, ws_history)
            # clear session_state
            st.session_state.players = []
            st.session_state.vehicles = []
            st.session_state.vehicle_groups = {}
            st.session_state.history = []
            st.session_state.usage = {}
            ui_success("All data reset (sheets cleared).")
            st.experimental_rerun()

        # Undo last entry (history)
        if st.button("↩ Undo Last Entry"):
            ok = safe_delete_last_row(ws_history)
            if ok:
                # also remove last from in-memory history if present
                if history:
                    history.pop()
                    st.session_state.history = history
                ui_success("Last history entry undone (sheet + memory).")
            st.experimental_rerun()

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
                # Reset sheets then restore
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
                st.experimental_rerun()
            except Exception as e:
                ui_error(f"Failed to restore backup: {e}")

    else:
        st.info("Admin-only controls. Login as admin to modify data.")

# -----------------------------
# Main UI - Players / Vehicles / Groups
# -----------------------------
st.header("1️⃣ Players Superset")
if st.session_state.admin_logged_in:
    colp1, colp2 = st.columns([3,1])
    with colp1:
        new_player = st.text_input("Add new player", key="new_player_input")
    with colp2:
        if st.button("Add Player"):
            if not new_player:
                ui_warn("Provide a valid name.")
            elif new_player in players:
                ui_warn("Player already exists.")
            else:
                ok = safe_append_row(ws_players, [new_player])
                if ok:
                    players.append(new_player)
                    st.session_state.players = players
                    ui_success(f"Player '{new_player}' added.")
                    st.experimental_rerun()

    if players:
        rem = st.selectbox("Remove a player", ["None"] + players, key="remove_player_select")
        if st.button("Remove Player"):
            if rem == "None":
                ui_info("Select a player to remove.")
            else:
                ok = safe_delete_row_by_match(ws_players, "Player", rem)
                if ok:
                    if rem in players:
                        players.remove(rem)
                        st.session_state.players = players
                    ui_success(f"Removed player '{rem}'.")
                    # remove from vehicles if present
                    if rem in vehicles:
                        # also remove from vehicles sheet
                        safe_delete_row_by_match(ws_vehicles, "Vehicle", rem)
                        vehicles.remove(rem)
                        st.session_state.vehicles = vehicles
                    st.experimental_rerun()

st.write("**Current Players:**", ", ".join(players) if players else "No players defined.")

st.markdown("---")
st.header("2️⃣ Vehicle Set (subset of players)")
if st.session_state.admin_logged_in:
    colv1, colv2 = st.columns([3,1])
    with colv1:
        new_vehicle = st.text_input("Add vehicle owner (must be in Players list)", key="new_vehicle_input")
    with colv2:
        if st.button("Add Vehicle"):
            if not new_vehicle:
                ui_warn("Provide a valid name.")
            elif new_vehicle not in players:
                ui_warn("Vehicle owner must be a player in superset.")
            elif new_vehicle in vehicles:
                ui_warn("Vehicle already exists.")
            else:
                ok = safe_append_row(ws_vehicles, [new_vehicle])
                if ok:
                    vehicles.append(new_vehicle)
                    st.session_state.vehicles = vehicles
                    ui_success(f"Vehicle owner '{new_vehicle}' added.")
                    st.experimental_rerun()

    if vehicles:
        remv = st.selectbox("Remove a vehicle owner", ["None"] + vehicles, key="remove_vehicle_select")
        if st.button("Remove Vehicle"):
            if remv == "None":
                ui_info("Select a vehicle owner to remove.")
            else:
                ok = safe_delete_row_by_match(ws_vehicles, "Vehicle", remv)
                if ok:
                    if remv in vehicles:
                        vehicles.remove(remv)
                        st.session_state.vehicles = vehicles
                    ui_success(f"Vehicle owner '{remv}' removed.")
                    st.experimental_rerun()

st.write("**Current Vehicle Owners:**", ", ".join(vehicles) if vehicles else "No vehicle owners defined.")

st.markdown("---")
st.header("3️⃣ Vehicle Groups (players sharing same vehicle)")
if st.session_state.admin_logged_in:
    vg_vehicle = st.selectbox("Select vehicle owner to define group for", [""] + vehicles, key="vg_vehicle_select")
    vg_members = st.multiselect("Select players (group) who share the same vehicle", players, key="vg_members_select")
    if st.button("Add/Update Vehicle Group"):
        if not vg_vehicle:
            ui_warn("Select a vehicle owner first.")
        else:
            ok = safe_update_group(ws_groups, vg_vehicle, vg_members)
            if ok:
                vehicle_groups[vg_vehicle] = vg_members
                st.session_state.vehicle_groups = vehicle_groups
                ui_success(f"Group updated for '{vg_vehicle}'.")
                st.experimental_rerun()

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
    st.info("Daily match selection is admin-only. Login to proceed.")
else:
    game_date = st.date_input("Select match date", value=date.today())
    ground_name = st.text_input("Ground name", key="ground_name")
    players_today = st.multiselect("Select players present today", players, key="players_today_multi")

    # number of vehicles needed: min 1 max len(vehicles)
    max_vehicles = len(vehicles) if vehicles else 1
    num_needed = st.number_input("Number of vehicles needed", min_value=1, max_value=max_vehicles, value=1, step=1)

    selection_mode = st.radio("Vehicle selection mode", ["Auto-Select", "Manual-Select"], index=0, key="sel_mode")
    manual_selected = []
    if selection_mode == "Manual-Select":
        manual_selected = st.multiselect("Manual select vehicle owners", vehicles, key="manual_select_vehicles")

    if st.button("Select Vehicles for Match"):
        # validation
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
                # emergency swap: allow admin to swap last vehicle before finalizing
                swap_options = ["None"] + [v for v in vehicles if v not in selected]
                swap_choice = st.selectbox("If emergency, change LAST selected vehicle to:", swap_options, key="swap_select")
                if swap_choice and swap_choice != "None":
                    replaced = selected[-1]
                    selected[-1] = swap_choice
                    ui_info(f"Replaced {replaced} with {swap_choice} for this match.")

                # generate message
                message = generate_message(game_date, ground_name, players_today, selected)
                st.subheader("📋 Copy-ready message")
                st.text_area("Match Details (copy-paste ready)", message, height=260)

                # record (append once)
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
                    # update usage counts in session
                    update_usage_counts(selected, eligible, usage)
                    st.session_state.usage = usage
                    ui_success(f"Vehicles selected and recorded: {', '.join(selected)}")
                    st.experimental_rerun()

# -----------------------------
# Usage Table & Chart (read-only for guests)
# -----------------------------
st.markdown("---")
st.header("6️⃣ Vehicle Usage")
if usage:
    df_usage = pd.DataFrame([{"Player": k, "Used": v["used"], "Present": v["present"],
                              "Ratio": (v["used"] / v["present"]) if v["present"] > 0 else 0.0}
                             for k, v in usage.items()])
    # sort by ratio desc
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

# -----------------------------
# Footer / help
# -----------------------------
st.markdown("---")
st.write("Notes:")
st.write("- Admin login required to add/remove players, vehicles, groups, and to make selections.")
st.write("- The app writes minimal rows to Google Sheets to reduce quota usage (incremental pattern).")
st.write("- If Sheets operations fail, check service account in Streamlit secrets and Sheets API quotas/permissions.")
