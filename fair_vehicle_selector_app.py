# fair_vehicle_selector_app.py

import streamlit as st
import json
import os

HISTORY_FILE = "vehicle_history.json"


# -----------------------------
# Utility Functions
# -----------------------------
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        return data.get("history", {}), data.get("last_index", -1), data.get("vehicle_set", [])
    else:
        return {}, -1, []


def save_history(history, last_index, vehicle_set):
    with open(HISTORY_FILE, "w") as f:
        json.dump({
            "history": history,
            "last_index": last_index,
            "vehicle_set": vehicle_set
        }, f, indent=4)


def select_vehicles(vehicle_set, player_set, num_needed):
    history, last_index, old_vehicle_set = load_history()

    # Add new vehicles if not seen before
    for v in vehicle_set:
        if v not in history:
            history[v] = 0

    # Remove old ones if deleted
    for old_v in list(history.keys()):
        if old_v not in vehicle_set:
            del history[old_v]

    # Filter eligible
    eligible = [v for v in vehicle_set if v in player_set]
    if not eligible:
        return [], history, last_index

    # Fair round robin sorting
    ordered = sorted(
        eligible,
        key=lambda v: (
            history.get(v, 0),
            (vehicle_set.index(v) - last_index) % len(vehicle_set)
        )
    )

    selected = ordered[:num_needed]

    # Update history
    for v in selected:
        history[v] = history.get(v, 0) + 1

    if selected:
        last_index = vehicle_set.index(selected[-1])

    save_history(history, last_index, vehicle_set)

    return selected, history, last_index


# -----------------------------
# Streamlit Interface
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")

st.title("🚗 Fair Vehicle Selector")
st.write("A simple round-robin algorithm to select vehicles fairly based on attendance and past usage.")

# Load previous state
history, last_index, vehicle_set = load_history()

# --- Section 1: Manage Vehicle Set ---
st.header("1️⃣ Manage Vehicle Set")
new_vehicle = st.text_input("Add a new vehicle owner:")
if st.button("Add Vehicle"):
    if new_vehicle and new_vehicle not in vehicle_set:
        vehicle_set.append(new_vehicle)
        history[new_vehicle] = 0
        save_history(history, last_index, vehicle_set)
        st.success(f"✅ Added new vehicle owner: {new_vehicle}")
    elif new_vehicle in vehicle_set:
        st.warning("⚠️ This vehicle owner already exists.")
    else:
        st.warning("Please enter a valid name.")

if vehicle_set:
    remove_vehicle = st.selectbox("Remove a vehicle owner (optional):", ["None"] + vehicle_set)
    if remove_vehicle != "None" and st.button("Remove Vehicle"):
        vehicle_set.remove(remove_vehicle)
        if remove_vehicle in history:
            del history[remove_vehicle]
        save_history(history, last_index, vehicle_set)
        st.success(f"🗑️ Removed {remove_vehicle} from the vehicle set.")

st.subheader("Current Vehicle Set:")
st.write(vehicle_set if vehicle_set else "No vehicles yet.")

# --- Section 2: Daily Selection ---
st.header("2️⃣ Daily Selection")
if not vehicle_set:
    st.warning("Please add at least one vehicle owner before selecting.")
else:
    players_today = st.multiselect("Select players present today:", vehicle_set)
    num_needed = st.number_input("Number of vehicles needed:", min_value=1, max_value=len(vehicle_set), value=1)

    if st.button("Select Vehicles"):
        selected, history, last_index = select_vehicles(vehicle_set, players_today, num_needed)
        if not selected:
            st.warning("⚠️ No eligible vehicle owners available today.")
        else:
            st.success("✅ Selected Vehicles for Today:")
            st.write(selected)

# --- Section 3: History Overview ---
st.header("3️⃣ Usage History")
if history:
    sorted_history = dict(sorted(history.items(), key=lambda x: x[1]))
    st.table(sorted_history)
else:
    st.info("No history yet. Start by adding vehicles and making selections.")
