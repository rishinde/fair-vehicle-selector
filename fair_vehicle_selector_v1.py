import streamlit as st
import json
import os
from datetime import date
import pandas as pd
import plotly.express as px

# -----------------------------
# Constants
# -----------------------------
HISTORY_FILE = "vehicle_history.json"
CSV_FILE = "vehicle_history.csv"

# -----------------------------
# Helper Functions
# -----------------------------
def load_data():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        players = data.get("players", [])
        vehicles = data.get("vehicles", [])
        history = data.get("history", [])
        usage = data.get("usage", {})
        # Safeguard: ensure history is list
        if not isinstance(history, list):
            history = []
        if not isinstance(usage, dict):
            usage = {}
        return players, vehicles, history, usage
    else:
        return [], [], [], {}

def save_data(players, vehicles, history, usage):
    data = {"players": players, "vehicles": vehicles, "history": history, "usage": usage}
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=4)
    save_csv(history)

def save_csv(history):
    if history:
        df = pd.DataFrame(history)
        df.to_csv(CSV_FILE, index=False)

def select_vehicles_auto(vehicle_set, player_set, num_needed, usage):
    eligible = [v for v in player_set if v in vehicle_set]
    if not eligible:
        return []
    # Sort by usage ratio
    def usage_ratio(v):
        u = usage.get(v, {"used":0, "present":0})
        return u["used"]/u["present"] if u["present"]>0 else 0
    ordered = sorted(eligible, key=lambda v: (usage_ratio(v), vehicle_set.index(v)))
    selected = ordered[:num_needed]

    # Update usage
    for v in selected:
        if v not in usage:
            usage[v] = {"used":0,"present":0}
        usage[v]["used"] +=1
    for v in eligible:
        if v not in usage:
            usage[v] = {"used":0,"present":0}
        usage[v]["present"] +=1

    return selected

def generate_message(game_date, ground_name, players, selected):
    message = (
        f"🏏 Match / Practice Details\n"
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
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Attendance-aware, fair vehicle distribution with auto/manual select and undo feature")

players, vehicles, history, usage = load_data()

# -----------------------------
# Sidebar: Admin
# -----------------------------
st.sidebar.header("⚙️ Admin Controls")
if st.sidebar.button("🧹 Reset All Data"):
    players, vehicles, history, usage = [], [], [], {}
    save_data(players, vehicles, history, usage)
    st.sidebar.success("✅ All data reset")

if st.sidebar.button("↩ Undo Last Entry"):
    history, usage, undone = undo_last_entry(history, usage)
    save_data(players, vehicles, history, usage)
    if undone:
        st.sidebar.success("✅ Last entry removed")
    else:
        st.sidebar.info("ℹ️ No record to undo")

# -----------------------------
# Player Superset
# -----------------------------
st.header("1️⃣ Players Superset")
new_player = st.text_input("Add new player:")
if st.button("Add Player"):
    if new_player and new_player not in players:
        players.append(new_player)
        save_data(players, vehicles, history, usage)
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
        save_data(players, vehicles, history, usage)
        st.success(f"🗑️ Removed player: {remove_player}")

st.write("**Current Players:**", ", ".join(players))

# -----------------------------
# Vehicle Set
# -----------------------------
st.header("2️⃣ Vehicle Set (subset of players)")
new_vehicle = st.text_input("Add vehicle owner:")
if st.button("Add Vehicle"):
    if new_vehicle and new_vehicle in players and new_vehicle not in vehicles:
        vehicles.append(new_vehicle)
        save_data(players, vehicles, history, usage)
        st.success(f"✅ Added vehicle owner: {new_vehicle}")
    elif new_vehicle not in players:
        st.warning("⚠️ Player must exist in superset")
    elif new_vehicle in vehicles:
        st.warning("⚠️ Already a vehicle owner")

if vehicles:
    remove_vehicle = st.selectbox("Remove vehicle owner:", ["None"] + vehicles)
    if remove_vehicle != "None" and st.button("Remove Vehicle"):
        vehicles.remove(remove_vehicle)
        save_data(players, vehicles, history, usage)
        st.success(f"🗑️ Removed vehicle owner: {remove_vehicle}")

st.write("**Current Vehicle Owners:**", ", ".join(vehicles))

# -----------------------------
# Daily Match Selection
# -----------------------------
st.header("3️⃣ Daily Match Selection")
if not players:
    st.warning("Please add at least one player")
else:
    game_date = st.date_input("Select date:", value=date.today())
    ground_name = st.text_input("Ground name:")
    players_today = st.multiselect("Select players present today:", players)
    num_needed = st.number_input("Number of vehicles needed:", 1, len(vehicles) if vehicles else 1, 1)
    selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"])

    if st.button("Select Vehicles"):
        if selection_mode=="Auto-Select":
            selected = select_vehicles_auto(vehicles, players_today, num_needed, usage)
        else:
            # Manual select
            selected = st.multiselect("Select vehicles manually:", vehicles, default=[])

        if not selected:
            st.warning("⚠️ No vehicles selected")
        else:
            st.success(f"✅ Vehicles selected: {', '.join(selected)}")

            # Emergency swap
            if len(selected)>0:
                swap_choice = st.selectbox("Change last vehicle (if needed):", ["None"] + [v for v in vehicles if v not in selected])
                if swap_choice != "None":
                    replaced = selected[-1]
                    selected[-1] = swap_choice
                    st.info(f"🔁 Replaced {replaced} with {swap_choice}")

            # Generate message
            msg = generate_message(game_date, ground_name, players_today, selected)
            st.subheader("📋 Copy-Ready Message")
            st.text_area("Message:", msg, height=200)

            # Save record
            record = {
                "date": str(game_date),
                "ground": ground_name,
                "players_present": players_today,
                "selected_vehicles": selected,
                "message": msg
            }
            history.append(record)
            save_data(players, vehicles, history, usage)

# -----------------------------
# Download CSV
# -----------------------------
st.header("4️⃣ Download CSV Backup")
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, "rb") as f:
        st.download_button("📥 Download CSV", f, file_name=CSV_FILE)
else:
    st.info("No CSV available yet")

# -----------------------------
# Usage Table & Chart
# -----------------------------
st.header("5️⃣ Vehicle Usage")
if usage:
    df_usage = pd.DataFrame([
        {"Vehicle": k, "Used": v["used"], "Present": v["present"], "Ratio": v["used"]/v["present"] if v["present"]>0 else 0}
        for k,v in usage.items()
    ])
    st.table(df_usage)

    fig = px.bar(df_usage, x="Vehicle", y="Ratio", text="Used", title="Vehicle Usage Fairness")
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
