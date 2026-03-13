import streamlit as st
import json
import datetime
import pandas as pd
import plotly.express as px
import time

def update_usage(selected_players, eligible_players, usage):
    for p in selected_players:
        if p not in usage:
            usage[p] = {"used":0,"present":0}
        usage[p]["used"] += 1
    for p in eligible_players:
        if p not in usage:
            usage[p] = {"used":0,"present":0}
        usage[p]["present"] +=1
"""
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
"""
"""
def select_vehicles_auto(vehicle_set, players_today, num_needed, usage, vehicle_groups, history):
    selected = []
    eligible = [v for v in players_today if v in vehicle_set]

    # --- Step 1: Safely fetch last completed match ---
    recently_used = set()
    if history and isinstance(history, list) and len(history) > 0:
        last_match = history[-1]  # last *saved* match only
        last_selected = last_match.get("selected_vehicles", [])
        st.write("🕓 Last match vehicles:", last_selected)
        if isinstance(last_selected, str):
            last_selected = [v.strip() for v in last_selected.split(",") if v.strip()]
        
        # Add last vehicles + all their group members
        for v in last_selected:
            recently_used.add(v)
            for members in vehicle_groups.values():
                if v in members:
                    recently_used.update(members)
                    break
        st.write("🕓 Recently Used vehicles:",recently_used)

    # --- Step 2: Exclude those vehicles/groups from current eligible list ---
    filtered_eligible = [v for v in eligible if v not in recently_used]

    st.write("🕓 Eligible vehicles for Selection:",filtered_eligible)
    if not filtered_eligible:
        # Fall back: allow selection if everyone was filtered out
        filtered_eligible = eligible

    # --- Step 3: Fair selection using least usage ratio ---
    for _ in range(num_needed):
        if not filtered_eligible:
            break

        def usage_ratio(p):
            u = usage.get(p, {"used": 0, "present": 0})
            return u["used"] / u["present"] if u["present"] > 0 else 0

        ordered = sorted(filtered_eligible, key=lambda p: (usage_ratio(p), vehicle_set.index(p)))
        pick = ordered[0]
        selected.append(pick)
        update_usage([pick], eligible, usage)

        # Remove all from same group to avoid duplicates
        for members in vehicle_groups.values():
            if pick in members:
                filtered_eligible = [e for e in filtered_eligible if e not in members]
                break
        else:
            filtered_eligible.remove(pick)

    return selected
"""

def select_vehicles_auto(vehicle_set, players_today, num_needed, usage, vehicle_groups, history):
    """
    Fairly select vehicles with following logic:
    ✅ Exclude vehicles (and their groups) used in the last match.
    ✅ Prioritize least-used (usage ratio).
    ✅ Break ties by least recently used overall (based on history).
    """
    import streamlit as st

    selected = []
    eligible = [v for v in players_today if v in vehicle_set]

    # --- Step 1: Collect vehicles used in last match ---
    recently_used = set()
    if history and isinstance(history, list) and len(history) > 0:
        last_match = history[-1]
        last_selected = last_match.get("selected_vehicles", [])
        st.write("🕓 Last match vehicles:", last_selected)

        if isinstance(last_selected, str):
            last_selected = [v.strip() for v in last_selected.split(",") if v.strip()]

        for v in last_selected:
            recently_used.add(v)
            # Include group members of last used vehicle
            for members in vehicle_groups.values():
                if v in members:
                    recently_used.update(members)
                    break

        st.write("🕓 Recently Used Vehicles (including group members):", recently_used)

    # --- Step 2: Compute last used order for LRU scoring ---
    last_used_order = {}
    if history:
        for match_index, match in enumerate(reversed(history)):
            match_selected = match.get("selected_vehicles", [])
            if isinstance(match_selected, str):
                match_selected = [v.strip() for v in match_selected.split(",") if v.strip()]
            for v in match_selected:
                if v not in last_used_order:
                    last_used_order[v] = match_index  # smaller = more recent
    # Default for unseen = large number (never used)
    st.write("📜 Last used order map:", last_used_order)

    # --- Step 3: Exclude recently used vehicles/groups from current selection ---
    filtered_eligible = [v for v in eligible if v not in recently_used]
    if not filtered_eligible:
        st.warning("⚠️ All vehicles were recently used — using fallback eligibility.")
        filtered_eligible = eligible.copy()

    st.write("✅ Eligible for selection:", filtered_eligible)

    # --- Step 4: Selection Loop ---
    for _ in range(num_needed):
        if not filtered_eligible:
            break

        def usage_ratio(p):
            u = usage.get(p, {"used": 0, "present": 0})
            return u["used"] / u["present"] if u["present"] > 0 else 0

        def recency_score(p):
            # Higher = longer ago used (or never used)
            return last_used_order.get(p, float('inf'))

        # Sort by: 1️⃣ least used, 2️⃣ least recently used, 3️⃣ list order
        ordered = sorted(
            filtered_eligible,
            key=lambda p: (usage_ratio(p), -recency_score(p), vehicle_set.index(p))
        )

        pick = ordered[0]
        selected.append(pick)
        st.write(f"🎯 Selected: {pick}")

        # Update usage tracking
        #update_usage([pick], eligible, usage)

        # Remove picked vehicle + all in same group
        for members in vehicle_groups.values():
            if pick in members:
                filtered_eligible = [e for e in filtered_eligible if e not in members]
                break
        else:
            filtered_eligible.remove(pick)

    # --- Step 5: Return Final Selection ---
    st.write("🚗 Final selected vehicles:", selected)
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


def vehicle_management(players, vehicles, vehicle_groups, history, usage, client,
                           ws_players, ws_vehicles, ws_groups, ws_history):
    
    if st.session_state.admin_logged_in and client:
        st.sidebar.subheader("⚙️ Admin Controls - Vehicle Management")
        # Initialize backup flag
        if "backup_downloaded" not in st.session_state:
            st.session_state.backup_downloaded = False

        # Prepare backup data
        backup_data = {
            "Players":[{"Player":p} for p in players],
            "Vehicles":[{"Vehicle":v} for v in vehicles],
            "VehicleGroups":[{"Vehicle":k,"Players":", ".join(v)} for k,v in vehicle_groups.items()],
            "History":history
        }

        # Download backup button
        if st.sidebar.download_button(
            "📥 Download Backup",
            json.dumps(backup_data, indent=4),
            file_name=f"backup_before_reset_{datetime.date.today()}.json",
            mime="application/json"
        ):
            st.session_state.backup_downloaded = True
            st.sidebar.success("✅ Backup downloaded. You can now reset data.")

        # Reset button: disabled until backup is downloaded
        reset_disabled = not st.session_state.backup_downloaded
        if st.sidebar.button("🧹 Reset All (Backup Mandatory)", disabled=reset_disabled):
            try:
                # Clear in-memory data
                players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}
                # Clear Google Sheets
                ws_players.clear()
                ws_players.append_row(["Player"])
                ws_vehicles.clear()
                ws_vehicles.append_row(["Vehicle"])
                ws_groups.clear()
                ws_groups.append_row(["Vehicle","Players"])
                ws_history.clear()
                ws_history.append_row(["date","ground","players_present","selected_vehicles","message"])
                st.sidebar.success("✅ All data reset")
                # Reset backup flag
                st.session_state.backup_downloaded = False
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.sidebar.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.sidebar.error(f"❌ Failed to reset Google Sheet: {e}")

        # Undo last entry
        if st.sidebar.button("↩ Undo Last Entry"):
            if history:
                history.pop()
                st.sidebar.success("✅ Last entry removed from memory, save history to google sheet in section 4")

        # Upload
        upload_file = st.sidebar.file_uploader("Upload Backup JSON", type="json")
        if upload_file:
            data = json.load(upload_file)
            players = [p["Player"] for p in data.get("Players",[])]
            vehicles = [v["Vehicle"] for v in data.get("Vehicles",[])]
            vehicle_groups = {g["Vehicle"]: g["Players"].split(", ") for g in data.get("VehicleGroups",[])}
            history = data.get("History",[])
            st.sidebar.success("✅ Data restored from backup, press respective save buttons to save in google sheet")

    st.header("1️⃣ Vehicle Set")
    with st.expander("⚙️ Manage Vehicle Set (Admin Access Required)", expanded=False):
    #if st.session_state.admin_logged_in:
        admin_disabled = not st.session_state.admin_logged_in
        new_vehicle = st.text_input("Add vehicle owner:", disabled=admin_disabled)
        if st.button("Add Vehicle",disabled=admin_disabled):
            if new_vehicle in players and new_vehicle not in vehicles:
                vehicles.append(new_vehicle)
                st.success(f"✅ Added vehicle owner: {new_vehicle}")
            else:
                st.warning("⚠️ Vehicle owner must exist in players and not duplicate")
        if vehicles:
            remove_vehicle_name = st.selectbox("Remove vehicle owner:", ["None"]+vehicles, disabled=admin_disabled)
            if remove_vehicle_name!="None" and st.button("Remove Vehicle",disabled=admin_disabled):
                vehicles.remove(remove_vehicle_name)
                st.success(f"🗑️ Removed vehicle: {remove_vehicle_name}")
        if st.button("💾 Save Vehicles to Google Sheet",disabled=admin_disabled) and client:
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
                    st.error(f"❌ Failed to save vehicles: {e}, contact admin")

    st.write("**Current Vehicle Owners:**", ", ".join(sorted(vehicles)))

    # -----------------------------
    # Vehicle Groups
    # -----------------------------
    st.header("2️⃣ Vehicle Groups")
    st.info("Vehicles from given group wont be selected on same day")
    with st.expander("⚙️ Manage Vehicle Groups (Admin Access Required)", expanded=False):
        admin_disabled = not st.session_state.admin_logged_in
        vg_vehicle = st.selectbox("Select vehicle to assign group", [""] + vehicles, disabled=admin_disabled)
        vg_members = st.multiselect("Select players sharing this vehicle", players,disabled=admin_disabled)
        if st.button("Add/Update Vehicle Group",disabled=admin_disabled):
            if vg_vehicle:
                vehicle_groups[vg_vehicle] = vg_members
                st.success(f"✅ Group updated for {vg_vehicle}")
        if st.button("💾 Save Vehicle Groups to Google Sheet",disabled=admin_disabled) and client:
            try:
                ws_groups.clear()
                ws_groups.append_row(["Vehicle","Players"])
                for k,v in vehicle_groups.items():
                    ws_groups.append_row([k, ", ".join(v)])
                st.success("✅ Vehicle groups saved to Google Sheet")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.error(f"❌ Failed to save vehicle groups: {e}, contact admin")

    st.write("**Current Vehicle Groups:**")
    if vehicle_groups:
        for v, members in vehicle_groups.items():
            st.write(f"{v}: {', '.join(members)}")
    else:
        st.write("No vehicle groups defined.")

    # -----------------------------
    # Daily Match Selection
    # -----------------------------
    st.header("3️⃣ Daily Match Selection")
    with st.expander("⚙️ Manage Match Selection (Admin Access Required)", expanded=False):

        admin_disabled = not st.session_state.admin_logged_in

        game_date = st.date_input("Select date:", value=datetime.date.today(),disabled=admin_disabled)
        ground_name = st.text_input("Ground name:",disabled=admin_disabled)
        players_today = st.multiselect("Select players present today:", sorted(players),disabled=admin_disabled)
        num_needed = st.number_input("Number of vehicles needed:", 1, len(vehicles) if vehicles else 1, 1, disabled=admin_disabled)
        selection_mode = st.radio("Vehicle Selection Mode:", ["Auto-Select", "Manual-Select"], key="mode",disabled=admin_disabled)
        
        if selection_mode == "Manual-Select":
            manual_selected = st.multiselect("Select vehicles manually:", sorted(vehicles), default=[],disabled=admin_disabled)
        else:
            manual_selected = []

        if st.button("Select Vehicles",disabled=admin_disabled):
            eligible = [v for v in players_today if v in vehicles]
            if selection_mode=="Auto-Select":
                selected = select_vehicles_auto(vehicles, players_today, num_needed, usage, vehicle_groups, history)
                update_usage(selected, eligible, usage)
            else:
                if len(manual_selected) != num_needed:
                    st.warning(f"⚠️ Select exactly {num_needed} vehicles")
                    selected = []
                else:
                    selected = manual_selected
                    update_usage(selected, eligible, usage)
            if selected:
                msg = generate_message(game_date, ground_name, players_today, selected)
                st.subheader("📋 Copy-Ready Message")
                st.text_area("Message:", msg, height=200)
                # Store in memory
                history.append({
                    "date": str(game_date),
                    "ground": ground_name,
                    "players_present": players_today,
                    "selected_vehicles": selected,
                    "message": msg
                })
                st.success(f"✅ Vehicles selected: {', '.join(selected)}")

        if st.button("💾 Save Match History to Google Sheet", disabled=admin_disabled) and client:
            try:
                data = [["date","ground","players_present","selected_vehicles","message"]]
        
                for r in history:
                    players_str = ", ".join(r["players_present"]) if isinstance(r["players_present"], list) else r["players_present"]
                    vehicles_str = ", ".join(r["selected_vehicles"]) if isinstance(r["selected_vehicles"], list) else r["selected_vehicles"]
        
                    data.append([
                        r["date"],
                        r["ground"],
                        players_str,
                        vehicles_str,
                        r["message"]
                    ])
        
                ws_history.clear()
                ws_history.update("A1", data)   # ← SINGLE API CALL
        
                st.success("✅ Match history saved to Google Sheet")
        
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Please try again after a few minutes.")
                else:
                    st.error(f"❌ Failed to save match history: {e}")

    # -----------------------------
    # Vehicle Usage Table & Chart
    # -----------------------------
    st.header("4️⃣ Vehicle Usage")
    if usage:
        df_usage = pd.DataFrame([
            {"Player": k, "Vehicle Used": v["used"], "Matches Played": v["present"], "Ratio": v["used"]/v["present"] if v["present"]>0 else 0}
            for k,v in usage.items() if k in vehicles
        ])
        df_usage = df_usage.sort_values("Player").reset_index(drop=True)
        df_usage.index = df_usage.index + 1
        df_usage.index.name = "S.No"
        st.table(df_usage)
        fig = px.bar(df_usage, x="Player", y="Ratio", text="Vehicle Used", title="Player Vehicle Usage Fairness")
        fig.update_traces(textposition='outside')
        fig.update_layout(yaxis=dict(range=[0,1.2]))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No usage data yet")

    # -----------------------------
    # Recent Match Records
    # -----------------------------
    st.header("5️⃣ Recent Vehicle Records")
    if history:
        for r in reversed(history[-10:]):
            vehicles_value = r["selected_vehicles"]
            if isinstance(vehicles_value, list):
                display_vehicles = ", ".join(vehicles_value)
            else:
                display_vehicles = vehicles_value
            st.write(f"📅 {r['date']} — {r['ground']} — 🚗 {display_vehicles}")
    else:
        st.info("No match records yet")
    
    if history:
        st.header("6️⃣ Download Vehicle History")
        df_history = pd.DataFrame(history)  # columns: date, ground, players_present, selected_vehicles, message
        import io
        csv_buffer = io.StringIO()
        df_history.to_csv(csv_buffer, index=False)
        st.download_button(
            "📥 Download History as CSV",
            data=csv_buffer.getvalue(),
            file_name="match_history.csv",
            mime="text/csv"
        )

    return vehicles, vehicle_groups, history, usage
