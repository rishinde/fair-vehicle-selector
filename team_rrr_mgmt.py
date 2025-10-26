# vehicle_management.py
import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import date

# -----------------------------
# Vehicle Management Logic
# -----------------------------
def vehicle_management(players, vehicles, vehicle_groups, history, usage, ws_vehicles=None, ws_groups=None, ws_history=None):
    st.header("🚗 Vehicle Management")
    st.caption("Manage vehicle owners, groups, and daily match selection")

    # -----------------------------
    # 1️⃣ Display Player Superset (Read-Only)
    # -----------------------------
    st.subheader("Player Superset (Read-Only)")
    if players:
        st.write(", ".join(sorted(players)))
    else:
        st.info("No players defined. Please add players in Player Superset tab.")

    # -----------------------------
    # 2️⃣ Vehicle Set Management
    # -----------------------------
    st.subheader("Vehicle Set")
    if st.session_state.get("admin_logged_in", False):
        new_vehicle = st.text_input("Add vehicle owner:")
        if st.button("Add Vehicle"):
            if new_vehicle in players and new_vehicle not in vehicles:
                vehicles.append(new_vehicle)
                st.success(f"✅ Added vehicle owner: {new_vehicle}")
            else:
                st.warning("⚠️ Vehicle owner must exist in Player Superset and not duplicate")

        if vehicles:
            remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"] + sorted(vehicles))
            if remove_vehicle_name != "None" and st.button("Remove Vehicle"):
                vehicles.remove(remove_vehicle_name)
                st.success(f"🗑️ Removed vehicle: {remove_vehicle_name}")

        if st.button("💾 Save Vehicles to Google Sheet") and ws_vehicles:
            try:
                ws_vehicles.clear()
                ws_vehicles.append_row(["Vehicle"])
                for v in vehicles:
                    ws_vehicles.append_row([v])
                st.success("✅ Vehicles saved to Google Sheet")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.error(f"❌ Failed to save vehicles: {e}")

    st.write("**Current Vehicle Owners:**", ", ".join(sorted(vehicles)) if vehicles else "No vehicles defined.")

    # -----------------------------
    # 3️⃣ Vehicle Groups Management
    # -----------------------------
    st.subheader("Vehicle Groups")
    if st.session_state.get("admin_logged_in", False):
        vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + sorted(vehicles))
        vg_members = st.multiselect("Select players sharing this vehicle", sorted(players))
        if st.button("Add/Update Vehicle Group"):
            if vg_vehicle:
                vehicle_groups[vg_vehicle] = vg_members
                st.success(f"✅ Group updated for {vg_vehicle}")

        if st.button("💾 Save Vehicle Groups to Google Sheet") and ws_groups:
            try:
                ws_groups.clear()
                ws_groups.append_row(["Vehicle", "Players"])
                for k, v in vehicle_groups.items():
                    ws_groups.append_row([k, ", ".join(v)])
                st.success("✅ Vehicle groups saved to Google Sheet")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.error(f"❌ Failed to save vehicle groups: {e}")

    if vehicle_groups:
        st.write("**Current Vehicle Groups:**")
        for v, members in vehicle_groups.items():
            st.write(f"{v}: {', '.join(members)}")
    else:
        st.write("No vehicle groups defined.")

    # -----------------------------
    # 4️⃣ Daily Match Selection
    # -----------------------------
    st.subheader("Daily Match Selection")
    if st.session_state.get("admin_logged_in", False):
        game_date = st.date_input("Select date:", value=date.today())
        players_today = st.multiselect("Select players present today:", sorted(players))
        num_needed = st.number_input("Number of vehicles needed:", 1, len(vehicles) if vehicles else 1, 1)
        selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"], key="mode")

        if selection_mode == "Manual-Select":
            manual_selected = st.multiselect("Select vehicles manually:", sorted(vehicles), default=[])
        else:
            manual_selected = []

        if st.button("Select Vehicles"):
            eligible = [v for v in players_today if v in vehicles]

            # Auto-selection logic
            if selection_mode == "Auto-Select":
                selected = select_vehicles_auto(vehicles, players_today, num_needed, usage, vehicle_groups)
            else:
                if len(manual_selected) != num_needed:
                    st.warning(f"⚠️ Select exactly {num_needed} vehicles")
                    selected = []
                else:
                    selected = manual_selected
                    update_usage(selected, eligible, usage)

            if selected:
                msg = generate_message(game_date, players_today, selected)
                st.subheader("📋 Copy-Ready Message")
                st.text_area("Message:", msg, height=200)

                # Store in memory
                history.append({
                    "date": str(game_date),
                    "players_present": players_today,
                    "selected_vehicles": selected,
                    "message": msg
                })
                st.success(f"✅ Vehicles selected: {', '.join(selected)}")

        if st.button("💾 Save Match History to Google Sheet") and ws_history:
            try:
                ws_history.clear()
                ws_history.append_row(["date", "players_present", "selected_vehicles", "message"])
                for r in history:
                    players_str = ", ".join(r["players_present"]) if isinstance(r["players_present"], list) else r["players_present"]
                    vehicles_str = ", ".join(r["selected_vehicles"]) if isinstance(r["selected_vehicles"], list) else r["selected_vehicles"]
                    ws_history.append_row([r["date"], players_str, vehicles_str, r["message"]])
                st.success("✅ Match history saved to Google Sheet")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.error(f"❌ Failed to save match history: {e}")

    # -----------------------------
    # 5️⃣ Vehicle Usage Table & Chart
    # -----------------------------
    st.subheader("Vehicle Usage")
    if usage:
        df_usage = pd.DataFrame([
            {"Player": k, "Vehicle_Used": v["used"], "Matches_Played": v["present"],
             "Ratio": v["used"]/v["present"] if v["present"] > 0 else 0}
            for k, v in usage.items() if k in vehicles
        ])
        df_usage = df_usage.sort_values("Player").reset_index(drop=True)
        df_usage.index = df_usage.index + 1
        df_usage.index.name = "S.No"
        st.table(df_usage)

        fig = px.bar(df_usage, x="Player", y="Ratio", text="Vehicle_Used", title="Player Vehicle Usage Fairness")
        fig.update_traces(textposition='outside')
        fig.update_layout(yaxis=dict(range=[0, 1.2]))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No usage data yet.")

# -----------------------------
# Supporting Functions
# -----------------------------
def update_usage(selected_players, eligible_players, usage):
    for p in selected_players:
        if p not in usage:
            usage[p] = {"used":0, "present":0}
        usage[p]["used"] += 1
    for p in eligible_players:
        if p not in usage:
            usage[p] = {"used":0, "present":0}
        usage[p]["present"] += 1

def select_vehicles_auto(vehicle_set, players_today, num_needed, usage, vehicle_groups):
    selected = []
    eligible = [v for v in players_today if v in vehicle_set]

    for _ in range(num_needed):
        if not eligible:
            break
        def usage_ratio(p):
            u = usage.get(p, {"used":0, "present":0})
            return u["used"]/u["present"] if u["present"]>0 else 0

        ordered = sorted(eligible, key=lambda p: (usage_ratio(p), vehicle_set.index(p)))
        pick = ordered[0]
        selected.append(pick)
        update_usage([pick], eligible, usage)

        # Remove all players sharing same vehicle
        for members in vehicle_groups.values():
            if pick in members:
                eligible = [e for e in eligible if e not in members]
                break
        else:
            eligible.remove(pick)

    return selected

def generate_message(game_date, players_today, selected):
    message = (
        f"🏏 Match Details\n"
        f"📅 Date: {game_date}\n\n"
        f"👥 Team:\n" + "\n".join([f"- {p}" for p in players_today]) + "\n\n"
        f"🚗 Vehicles:\n" + "\n".join([f"- {v}" for v in selected])
    )
    return message
