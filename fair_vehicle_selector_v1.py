import streamlit as st
import json
import os
from datetime import date
import pandas as pd
import plotly.express as px
import base64
import urllib.parse

# -----------------------------
# Constants
# -----------------------------
HISTORY_FILE = "vehicle_history.json"
BACKUP_FILE = "vehicle_history_backup.csv"
DEFAULT_VEHICLES = ["Alice", "Bob", "Charlie", "David"]

# -----------------------------
# Helper Functions
# -----------------------------
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        return (
            data.get("history", {}),
            data.get("last_index", -1),
            data.get("vehicle_set", []),
            data.get("records", [])
        )
    else:
        return {}, -1, DEFAULT_VEHICLES.copy(), []

def save_history(history, last_index, vehicle_set, records):
    with open(HISTORY_FILE, "w") as f:
        json.dump({
            "history": history,
            "last_index": last_index,
            "vehicle_set": vehicle_set,
            "records": records
        }, f, indent=4)
    backup_csv(history)

def backup_csv(history):
    if history:
        df = pd.DataFrame([
            {"Vehicle": k, "Used": v["used"], "Present": v["present"]}
            for k, v in history.items()
        ])
        df.to_csv(BACKUP_FILE, index=False)

def select_vehicles(vehicle_set, player_set, num_needed, game_date, ground_name):
    history, last_index, _, records = load_history()

    for v in vehicle_set:
        if v not in history:
            history[v] = {"used": 0, "present": 0}
    for old_v in list(history.keys()):
        if old_v not in vehicle_set:
            del history[old_v]

    # Update presence
    for v in player_set:
        history[v]["present"] += 1

    # Determine eligible
    eligible = [v for v in vehicle_set if v in player_set]
    if not eligible:
        return [], history, last_index, records

    # Sort by usage ratio then round-robin
    ordered = sorted(
        eligible,
        key=lambda v: (
            history[v]["used"] / history[v]["present"] if history[v]["present"] > 0 else 0,
            (vehicle_set.index(v) - last_index) % len(vehicle_set)
        )
    )

    selected = ordered[:num_needed]

    # Update usage
    for v in selected:
        history[v]["used"] += 1
    if selected:
        last_index = vehicle_set.index(selected[-1])

    # Log record
    record = {
        "date": str(game_date),
        "ground": ground_name,
        "players": player_set,
        "selected": selected
    }
    records.append(record)

    save_history(history, last_index, vehicle_set, records)
    return selected, history, last_index, records


def undo_last_entry():
    """Removes the most recent game record and adjusts usage counts."""
    history, last_index, vehicle_set, records = load_history()
    if not records:
        return False, history, last_index, vehicle_set, records

    last_record = records.pop()
    for v in last_record["selected"]:
        if v in history and history[v]["used"] > 0:
            history[v]["used"] -= 1

    save_history(history, last_index, vehicle_set, records)
    return True, history, last_index, vehicle_set, records


def generate_whatsapp_message(game_date, ground_name, players, selected):
    message = (
        f"🏏 *Match / Practice Details*\n"
        f"📅 Date: {game_date}\n"
        f"📍 Venue: {ground_name}\n\n"
        f"👥 Team:\n" + "\n".join([f"- {p}" for p in players]) + "\n\n"
        f"🚗 Vehicles:\n" + "\n".join([f"- {v}" for v in selected])
    )
    encoded = urllib.parse.quote(message)
    link = f"https://wa.me/?text={encoded}"
    return message, link


# -----------------------------
# Streamlit Interface
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector")
st.caption("Round-robin, attendance-aware selection with WhatsApp message & undo feature")

history, last_index, vehicle_set, records = load_history()

# --- Reset ---
st.sidebar.subheader("⚙️ Admin Controls")
if st.sidebar.button("🧹 Reset All Data"):
    history = {}
    last_index = -1
    records = []
    vehicle_set = DEFAULT_VEHICLES.copy()
    save_history(history, last_index, vehicle_set, records)
    st.sidebar.success("✅ All data has been reset.")

# --- Undo last entry ---
if st.sidebar.button("↩ Undo Last Entry"):
    undone, history, last_index, vehicle_set, records = undo_last_entry()
    if undone:
        st.sidebar.success("✅ Last record removed successfully.")
    else:
        st.sidebar.info("ℹ️ No record found to undo.")

# --- Manage vehicles ---
st.header("1️⃣ Manage Vehicle Set")
new_vehicle = st.text_input("Add new vehicle owner:")
if st.button("Add Vehicle"):
    if new_vehicle and new_vehicle not in vehicle_set:
        vehicle_set.append(new_vehicle)
        history[new_vehicle] = {"used": 0, "present": 0}
        save_history(history, last_index, vehicle_set, records)
        st.success(f"✅ Added {new_vehicle}")
    elif new_vehicle in vehicle_set:
        st.warning("⚠️ Vehicle already exists.")
    else:
        st.warning("Please enter a name.")

if vehicle_set:
    remove_vehicle = st.selectbox("Remove a vehicle (optional):", ["None"] + vehicle_set)
    if remove_vehicle != "None" and st.button("Remove Vehicle"):
        vehicle_set.remove(remove_vehicle)
        if remove_vehicle in history:
            del history[remove_vehicle]
        save_history(history, last_index, vehicle_set, records)
        st.success(f"🗑️ Removed {remove_vehicle}")

st.write("**Current Vehicles:**", ", ".join(vehicle_set))

# --- Game selection ---
st.header("2️⃣ Daily Game Selection")
if not vehicle_set:
    st.warning("Please add at least one vehicle owner first.")
else:
    game_date = st.date_input("Select game date:", value=date.today())
    ground_name = st.text_input("Ground name:")
    players_today = st.multiselect("Select players present today:", vehicle_set)
    num_needed = st.number_input("Number of vehicles needed:", 1, len(vehicle_set), 1)

    if st.button("Select Vehicles"):
        selected, history, last_index, records = select_vehicles(
            vehicle_set, players_today, num_needed, game_date, ground_name
        )

        if not selected:
            st.warning("⚠️ No eligible vehicles today.")
        else:
            st.success(f"✅ Vehicles selected for {game_date} ({ground_name}): {', '.join(selected)}")

            # Allow emergency manual swap of last vehicle
            if len(selected) > 0:
                swap_choice = st.selectbox("Change last vehicle (if needed):", ["None"] + [v for v in vehicle_set if v not in selected])
                if swap_choice != "None":
                    replaced = selected[-1]
                    selected[-1] = swap_choice
                    st.info(f"🔁 Replaced {replaced} with {swap_choice}")

            # Generate WhatsApp message
            msg, link = generate_whatsapp_message(game_date, ground_name, players_today, selected)
            st.subheader("📋 WhatsApp-Ready Message")
            st.text_area("Formatted message:", msg, height=200)
            st.markdown(f"[📲 Open in WhatsApp]({link})", unsafe_allow_html=True)
            st.button("📋 Copy to Clipboard (manually)")

# --- History table ---
st.header("3️⃣ Vehicle Usage History")
if history:
    table = pd.DataFrame([
        {"Vehicle": k, "Used": v["used"], "Present": v["present"]}
        for k, v in history.items()
    ])
    st.table(table)
else:
    st.info("No history yet.")

# --- Chart ---
st.header("📊 Usage Fairness Chart")
if history:
    df_chart = pd.DataFrame([
        {"Vehicle": k, "Used": v["used"], "Present": v["present"]}
        for k, v in history.items()
    ])
    df_chart["Usage Ratio"] = df_chart["Used"] / df_chart["Present"]
    fig = px.bar(df_chart, x="Vehicle", y="Usage Ratio", text="Used", title="Vehicle Usage Fairness")
    fig.update_traces(textposition='outside')
    fig.update_layout(yaxis=dict(range=[0, 1.2]))
    st.plotly_chart(fig, use_container_width=True)

# --- Records ---
st.header("4️⃣ Recent Game Records")
if records:
    for r in reversed(records[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {', '.join(r['selected'])}")
else:
    st.info("No records yet.")
