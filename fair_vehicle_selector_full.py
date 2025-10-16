import streamlit as st
import json
import os
from datetime import date
import pandas as pd
import plotly.express as px

HISTORY_FILE = "vehicle_history.json"
BACKUP_FILE = "vehicle_history_backup.csv"

# -----------------------------
# Default Vehicle Set
# -----------------------------
DEFAULT_VEHICLES = ["Alice", "Bob", "Charlie", "David"]

# -----------------------------
# Utility Functions
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

def backup_csv(history):
    """Automatically save a CSV backup of history"""
    if history:
        df = pd.DataFrame([
            {"Vehicle": k, "Used": v["used"], "Present": v["present"]}
            for k, v in history.items()
        ])
        df.to_csv(BACKUP_FILE, index=False)

def select_vehicles(vehicle_set, player_set, num_needed, game_date, ground_name):
    history, last_index, old_vehicle_set, records = load_history()

    for v in vehicle_set:
        if v not in history:
            history[v] = {"used": 0, "present": 0}

    for old_v in list(history.keys()):
        if old_v not in vehicle_set:
            del history[old_v]

    # Update presence
    for v in player_set:
        history[v]["present"] = history.get(v, {"used": 0, "present": 0})["present"] + 1

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

    # Update usage and round-robin pointer
    for v in selected:
        history[v]["used"] += 1
    if selected:
        last_index = vehicle_set.index(selected[-1])

    # Log record
    records.append({
        "date": str(game_date),
        "ground": ground_name,
        "selected": selected
    })

    save_history(history, last_index, vehicle_set, records)
    backup_csv(history)  # <-- automatic CSV backup

    return selected, history, last_index, records

# -----------------------------
# Streamlit Interface
# -----------------------------
st.set_page_config(page_title="Fair Vehicle Selector Cloud", page_icon="🚗", layout="centered")
st.title("🚗 Fair Vehicle Selector (Cloud Ready)")
st.caption("Attendance-aware selection with automatic CSV backup, import/export, charts, and reset option.")

history, last_index, vehicle_set, records = load_history()

# --- Reset Button ---
st.subheader("⚙️ Admin Controls")
if st.button("🧹 Reset History and Records"):
    history = {}
    last_index = -1
    records = []
    vehicle_set = DEFAULT_VEHICLES.copy()
    save_history(history, last_index, vehicle_set, records)
    st.success("✅ History and records have been reset.")

# --- Import CSV to Restore History ---
uploaded_file = st.file_uploader("📂 Upload history CSV to restore", type="csv")
if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)
        history = {}
        records = []
        last_index = -1
        vehicle_set = list(df['Vehicle'].unique())
        for _, row in df.iterrows():
            history[row['Vehicle']] = {"used": int(row['Used']), "present": int(row['Present'])}
        save_history(history, last_index, vehicle_set, records)
        backup_csv(history)
        st.success("✅ History restored from CSV")
    except Exception as e:
        st.error(f"⚠️ Failed to restore CSV: {e}")

# --- Export History CSV ---
if history:
    export_df = pd.DataFrame([
        {"Vehicle": k, "Used": v["used"], "Present": v["present"]}
        for k, v in history.items()
    ])
    csv_data = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="💾 Download History as CSV",
        data=csv_data,
        file_name="vehicle_history.csv",
        mime="text/csv"
    )

# --- Section 1: Manage Vehicle Set ---
st.header("1️⃣ Manage Vehicle Set")
new_vehicle = st.text_input("Add new vehicle owner:")
if st.button("Add Vehicle"):
    if new_vehicle and new_vehicle not in vehicle_set:
        vehicle_set.append(new_vehicle)
        history[new_vehicle] = {"used": 0, "present": 0}
        save_history(history, last_index, vehicle_set, records)
        backup_csv(history)
        st.success(f"✅ Added {new_vehicle}")
    elif new_vehicle in vehicle_set:
        st.warning("⚠️ Already exists.")
    else:
        st.warning("Please enter a valid name.")

if vehicle_set:
    remove_vehicle = st.selectbox("Remove a vehicle owner (optional):", ["None"] + vehicle_set)
    if remove_vehicle != "None" and st.button("Remove Vehicle"):
        vehicle_set.remove(remove_vehicle)
        if remove_vehicle in history:
            del history[remove_vehicle]
        save_history(history, last_index, vehicle_set, records)
        backup_csv(history)
        st.success(f"🗑️ Removed {remove_vehicle}")

st.subheader("Current Vehicle Set:")
st.write(vehicle_set if vehicle_set else "No vehicles yet.")

# --- Section 2: Daily Game Selection ---
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
            st.success(f"✅ Vehicles selected for {game_date} ({ground_name}):")
            st.write(selected)

# --- Section 3: Usage History Table ---
st.header("3️⃣ Vehicle Usage History")
if history:
    table_data = {k: f"{v['used']} / {v['present']}" for k, v in history.items()}
    st.table(table_data)
else:
    st.info("No data yet for history.")

# --- Section 3b: Usage vs Attendance Chart ---
st.header("📊 Usage vs Attendance Chart")
if history:
    chart_data = pd.DataFrame([
        {"Vehicle": k, "Used": v["used"], "Present": v["present"]}
        for k, v in history.items()
    ])
    chart_data["Usage Ratio"] = chart_data["Used"] / chart_data["Present"]
    fig = px.bar(
        chart_data,
        x="Vehicle",
        y="Usage Ratio",
        text="Used",
        hover_data=["Used", "Present"],
        labels={"Usage Ratio": "Used / Present"},
        title="Vehicle Usage Fairness Ratio"
    )
    fig.update_traces(texttemplate='%{text}', textposition='outside')
    fig.update_layout(yaxis=dict(range=[0, 1.1]))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data yet for chart.")

# --- Section 4: Past Game Records ---
st.header("4️⃣ Recent Game Records")
if records:
    for r in reversed(records[-10:]):
        st.write(f"📅 {r['date']} — {r['ground']} — 🚘 {', '.join(r['selected'])}")
else:
    st.info("No game records yet.")
