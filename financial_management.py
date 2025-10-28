# financial_management.py
import streamlit as st
import pandas as pd
import time
from datetime import date

def financial_management(players, client):
    """
    Financial management module.
    - players: list of player names (read-only reference from Player Superset)
    - client: Google Sheets client object
    """

    SHEET_NAME = "Team Financial Data"
    ws_financial, ws_deposit = None, None

    # -----------------------------
    # Google Sheet Setup
    # -----------------------------
    if client:
        try:
            existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
            sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)

            try:
                ws_financial = sh.worksheet("Financials")
            except:
                ws_financial = sh.add_worksheet("Financials", rows=100, cols=50)
                ws_financial.append_row(["Player", "Total Deposit", "Balance"])

            try:
                ws_deposit = sh.worksheet("DepositHistory")
            except:
                ws_deposit = sh.add_worksheet("DepositHistory", rows=100, cols=10)
                ws_deposit.append_row(["Player", "Date", "Amount"])
        except Exception as e:
            st.error(f"Failed to open or create Financial Data sheet: {e}")
            ws_financial, ws_deposit = None, None

    # -----------------------------
    # Load Financial Data
    # -----------------------------
    if ws_financial:
        try:
            df_financial = pd.DataFrame(ws_financial.get_all_records())
        except:
            df_financial = pd.DataFrame()
    else:
        df_financial = pd.DataFrame()

    # Ensure all players are present in the sheet
    existing_players = set(df_financial["Player"].astype(str).str.strip()) if "Player" in df_financial.columns else set()
    for p in players:
        if p.strip() not in existing_players:
            df_financial = pd.concat(
                [df_financial, pd.DataFrame([{"Player": p.strip(), "Total Deposit": 0.0, "Balance": 0.0}])],
                ignore_index=True
            )
    df_financial.fillna(0.0, inplace=True)

    # -----------------------------
    # Load Deposit History
    # -----------------------------
    if ws_deposit:
        try:
            df_deposit = pd.DataFrame(ws_deposit.get_all_records())
        except:
            df_deposit = pd.DataFrame(columns=["Player", "Date", "Amount"])
    else:
        df_deposit = pd.DataFrame(columns=["Player", "Date", "Amount"])

    # -----------------------------
    # Match Fee Section
    # -----------------------------
    st.subheader("🏏 Match Fee Entry")
    match_date = st.date_input("Select Match Date", value=date.today())
    ground_name = st.text_input("Ground Name")
    players_today = st.multiselect("Players Attending", sorted(players))
    total_fee = st.number_input("Total Match Fee (₹)", min_value=0, value=0, step=1)

    if st.button("➕ Add Match Fee"):
        if not players_today:
            st.warning("⚠️ Select at least one player.")
        elif total_fee <= 0:
            st.warning("⚠️ Enter a valid match fee.")
        else:
            fee_per_player = round(total_fee / len(players_today), 2)
            match_id = f"{match_date}_{ground_name.strip() or 'Match'}"
            match_id = match_id.replace(" ", "_")

            if match_id not in df_financial.columns:
                df_financial[match_id] = 0.0

            for idx, row in df_financial.iterrows():
                if row["Player"] in players_today:
                    df_financial.at[idx, match_id] = fee_per_player

            # Update balances
            match_cols = [c for c in df_financial.columns if c not in ["Player", "Total Deposit", "Balance"]]
            df_financial["Balance"] = df_financial["Total Deposit"] - df_financial[match_cols].sum(axis=1)
            st.success(f"✅ Match '{match_id}' added. Fee per player: ₹{fee_per_player}")

    # -----------------------------
    # Deposit Section
    # -----------------------------
    st.subheader("💵 Player Deposit Entry")
    deposit_player = st.selectbox("Select Player", sorted(players))
    deposit_amount = st.number_input("Deposit Amount (₹)", min_value=0, value=0, step=1)
    deposit_date = st.date_input("Deposit Date", value=date.today(), key="deposit_date")

    if st.button("➕ Add Deposit"):
        if deposit_amount <= 0:
            st.warning("⚠️ Enter a valid amount.")
        else:
            df_deposit = pd.concat(
                [df_deposit, pd.DataFrame([{"Player": deposit_player, "Date": str(deposit_date), "Amount": deposit_amount}])],
                ignore_index=True
            )
            idx = df_financial.index[df_financial["Player"] == deposit_player][0]
            df_financial.at[idx, "Total Deposit"] += deposit_amount
            match_cols = [c for c in df_financial.columns if c not in ["Player", "Total Deposit", "Balance"]]
            df_financial.at[idx, "Balance"] = df_financial.at[idx, "Total Deposit"] - df_financial.loc[idx, match_cols].sum()
            st.success(f"✅ Added ₹{deposit_amount} for {deposit_player}")

    # -----------------------------
    # Display Financial Table
    # -----------------------------
    st.subheader("📊 Team Financial Summary")
    df_financial = df_financial.sort_values("Player").reset_index(drop=True)
    df_financial.index = df_financial.index + 1
    df_financial.index.name = "S.No"
    st.dataframe(df_financial)

    # -----------------------------
    # Deposit History
    # -----------------------------
    st.subheader("🧾 Deposit History")
    if not df_deposit.empty:
        df_deposit = df_deposit.sort_values(["Date", "Player"]).reset_index(drop=True)
        df_deposit.index = df_deposit.index + 1
        df_deposit.index.name = "S.No"
        st.dataframe(df_deposit)
    else:
        st.info("No deposits yet.")

    # -----------------------------
    # Save to Google Sheets
    # -----------------------------
    if st.button("💾 Save Financial Data to Google Sheets"):
        if ws_financial and ws_deposit:
            try:
                # Save Financial Sheet
                ws_financial.clear()
                ws_financial.append_row(list(df_financial.columns))
                for _, r in df_financial.iterrows():
                    ws_financial.append_row([r.get(c, "") for c in df_financial.columns])
                    time.sleep(0.1)

                # Save Deposit Sheet
                ws_deposit.clear()
                ws_deposit.append_row(list(df_deposit.columns))
                for _, r in df_deposit.iterrows():
                    ws_deposit.append_row([r.get(c, "") for c in df_deposit.columns])
                    time.sleep(0.1)

                st.success("✅ Financial data and deposit history saved successfully!")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Try again later.")
                else:
                    st.error(f"❌ Error saving data: {e}")
        else:
            st.warning("⚠️ Google Sheets not connected.")
