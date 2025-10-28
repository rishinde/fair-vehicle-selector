# financial_management.py
import streamlit as st
import pandas as pd
import time
from datetime import date

ROW_DELAY = 0.15  # delay to avoid quota issues
SHEET_NAME = "Team Financial Data"

def financial_management(players, client):
    """Financial management - Simple one-time load with direct writes."""

    if not client:
        st.warning("⚠️ Google Sheets not connected. Financial operations disabled.")
        return

    # -----------------------------
    # Open or create Google Sheets
    # -----------------------------
    try:
        existing = [s['name'] for s in client.list_spreadsheet_files()]
        sh = client.open(SHEET_NAME) if SHEET_NAME in existing else client.create(SHEET_NAME)

        try:
            ws_fin = sh.worksheet("Financials")
        except:
            ws_fin = sh.add_worksheet("Financials", rows=200, cols=20)
            ws_fin.append_row(["Player", "Total Deposit", "Balance"])

        try:
            ws_dep = sh.worksheet("DepositHistory")
        except:
            ws_dep = sh.add_worksheet("DepositHistory", rows=200, cols=20)
            ws_dep.append_row(["Player", "Date", "Amount"])
    except Exception as e:
        st.error(f"❌ Failed to connect to Google Sheets: {e}")
        return

    # -----------------------------
    # Load existing data
    # -----------------------------
    try:
        fin_records = ws_fin.get_all_records()
        df_fin = pd.DataFrame(fin_records)
    except:
        df_fin = pd.DataFrame(columns=["Player", "Total Deposit", "Balance"])

    try:
        dep_records = ws_dep.get_all_records()
        df_dep = pd.DataFrame(dep_records)
    except:
        df_dep = pd.DataFrame(columns=["Player", "Date", "Amount"])

    # Ensure all players exist
    for p in players:
        if p not in df_fin["Player"].values:
            df_fin = pd.concat([df_fin, pd.DataFrame([{"Player": p, "Total Deposit": 0.0, "Balance": 0.0}])], ignore_index=True)

    df_fin.fillna(0.0, inplace=True)

    # -----------------------------
    # Display existing summary
    # -----------------------------
    st.header("📊 Team Financial Summary")
    df_show = df_fin.sort_values("Player").reset_index(drop=True)
    df_show.index = df_show.index + 1
    st.dataframe(df_show, use_container_width=True)

    # -----------------------------
    # 1️⃣ Match Fee Entry
    # -----------------------------
    st.subheader("🏏 Add Match Fee Entry (One Match at a Time)")

    match_date = st.date_input("Match Date", value=date.today())
    ground = st.text_input("Ground Name", "")
    players_today = st.multiselect("Players Present", sorted(players))
    total_fee = st.number_input("Total Match Fee (₹)", min_value=0.0, step=50.0)

    if st.button("💾 Save Match Entry to Google Sheet"):
        if not players_today or total_fee <= 0:
            st.warning("⚠️ Select players and enter valid match fee.")
        else:
            fee_per_player = round(total_fee / len(players_today), 2)
            col_name = f"{match_date.strftime('%Y-%m-%d')} ({ground or 'Match'})"

            # Add new column for this match
            if col_name not in df_fin.columns:
                df_fin[col_name] = 0.0

            # Update each player’s match fee
            for idx, row in df_fin.iterrows():
                if row["Player"] in players_today:
                    df_fin.at[idx, col_name] = fee_per_player

            # Recalculate balance
            match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
            df_fin["Balance"] = df_fin["Total Deposit"] - df_fin[match_cols].sum(axis=1)

            # Write back to Google Sheets
            try:
                ws_fin.clear()
                ws_fin.append_row(df_fin.columns.tolist())
                for _, r in df_fin.iterrows():
                    ws_fin.append_row([r[c] for c in df_fin.columns])
                    time.sleep(ROW_DELAY)
                st.success(f"✅ Match entry added and saved (₹{fee_per_player}/player).")
            except Exception as e:
                st.error(f"❌ Failed to save match entry: {e}")

    # -----------------------------
    # 2️⃣ Player Deposit Entry
    # -----------------------------
    st.subheader("💵 Add Deposit Entry (One Player at a Time)")

    deposit_player = st.selectbox("Select Player", sorted(players))
    deposit_amount = st.number_input("Deposit Amount (₹)", min_value=0.0, step=50.0)
    deposit_date = st.date_input("Deposit Date", value=date.today())

    if st.button("💾 Save Deposit Entry to Google Sheet"):
        if deposit_amount <= 0:
            st.warning("⚠️ Enter a valid deposit amount.")
        else:
            # Add to deposit history
            df_dep = pd.concat([
                df_dep,
                pd.DataFrame([{"Player": deposit_player, "Date": str(deposit_date), "Amount": deposit_amount}])
            ], ignore_index=True)

            # Update total deposit and balance
            if deposit_player in df_fin["Player"].values:
                idx = df_fin.index[df_fin["Player"] == deposit_player][0]
                df_fin.at[idx, "Total Deposit"] += deposit_amount

            match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
            df_fin["Balance"] = df_fin["Total Deposit"] - df_fin[match_cols].sum(axis=1)

            # Write both sheets
            try:
                ws_fin.clear()
                ws_fin.append_row(df_fin.columns.tolist())
                for _, r in df_fin.iterrows():
                    ws_fin.append_row([r[c] for c in df_fin.columns])
                    time.sleep(ROW_DELAY)

                ws_dep.clear()
                ws_dep.append_row(df_dep.columns.tolist())
                for _, r in df_dep.iterrows():
                    ws_dep.append_row([r[c] for c in df_dep.columns])
                    time.sleep(ROW_DELAY)

                st.success(f"✅ Deposit of ₹{deposit_amount} added for {deposit_player} and saved.")
            except Exception as e:
                st.error(f"❌ Failed to save deposit: {e}")

    # -----------------------------
    # 3️⃣ Deposit History
    # -----------------------------
    st.subheader("🧾 Deposit History")
    if not df_dep.empty:
        df_dep = df_dep.sort_values(["Date", "Player"]).reset_index(drop=True)
        df_dep.index = df_dep.index + 1
        st.dataframe(df_dep, use_container_width=True)
    else:
        st.info("No deposits recorded yet.")
