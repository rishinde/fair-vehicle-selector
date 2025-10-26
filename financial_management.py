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

    # -----------------------------
    # Google Sheet Setup
    # -----------------------------
    SHEET_NAME = "Team Financial Data"
    ws_financial, ws_deposit = None, None

    if client:
        try:
            existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
            sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)

            # Financials sheet
            try:
                ws_financial = sh.worksheet("Financials")
            except:
                ws_financial = sh.add_worksheet("Financials", rows=100, cols=50)
                ws_financial.append_row(["Player", "Total Deposit", "Balance"])

            # DepositHistory sheet
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
            records = ws_financial.get_all_records()
            df_financial = pd.DataFrame(records)
        except:
            df_financial = pd.DataFrame()
    else:
        df_financial = pd.DataFrame()

    # Ensure all players exist
    for p in players:
        existing_players = set(df_financial["Player"].str.strip()) if "Player" in df_financial.columns else set()
        for p in players:
            if p.strip() not in existing_players:
                df_financial = pd.concat(
                    [df_financial, pd.DataFrame([{"Player": p.strip(), "Total Deposit": 0.0, "Balance": 0.0}])],
                    ignore_index=True
                )

        #if p not in df_financial.get("Player", []):
        #    df_financial = pd.concat(
        #        [df_financial, pd.DataFrame([{"Player": p, "Total Deposit": 0.0, "Balance": 0.0}])],
        #        ignore_index=True
        #    )
    df_financial.fillna(0.0, inplace=True)

    # -----------------------------
    # Load Deposit History
    # -----------------------------
    if ws_deposit:
        try:
            deposit_records = ws_deposit.get_all_records()
            df_deposit = pd.DataFrame(deposit_records)
        except:
            df_deposit = pd.DataFrame(columns=["Player", "Date", "Amount"])
    else:
        df_deposit = pd.DataFrame(columns=["Player", "Date", "Amount"])

    # -----------------------------
    # Player Reference
    # -----------------------------
    st.subheader("Players Reference (read-only)")
    st.write(", ".join(sorted(players)))

    # -----------------------------
    # Match Fee Section
    # -----------------------------
    st.subheader("Enter Match Fee Details")
    match_date = st.date_input("Select Match Date", value=date.today())
    ground_name = st.text_input("Ground Name")
    players_today = st.multiselect("Select Players Attending", sorted(players))
    total_fee = st.number_input("Total Match Fee", min_value=0, value=0, step=1)

    if st.button("Add Match Fee"):
        if not players_today:
            st.warning("⚠️ Select at least one player for the match.")
        elif total_fee <= 0:
            st.warning("⚠️ Enter a valid match fee.")
        else:
            fee_per_player = round(total_fee / len(players_today), 2)
            existing_match_cols = [c for c in df_financial.columns if "_Match" in c]
            match_number = len(existing_match_cols) + 1
            new_col_name = f"{match_date}_Match{match_number}"
            df_financial[new_col_name] = 0.0
            for idx, row in df_financial.iterrows():
                if row["Player"] in players_today:
                    df_financial.at[idx, new_col_name] = fee_per_player
            # Update balance
            fee_cols = [c for c in df_financial.columns if "_Match" in c]
            df_financial["Balance"] = df_financial["Total Deposit"] - df_financial[fee_cols].sum(axis=1)
            st.success(f"✅ Match fees added for {len(players_today)} players. Fee per player: {fee_per_player}")

    # -----------------------------
    # Deposit Section
    # -----------------------------
    st.subheader("Add Deposit for Player")
    deposit_player = st.selectbox("Select Player", sorted(players))
    deposit_amount = st.number_input("Deposit Amount", min_value=0, value=0, step=1)
    deposit_date = st.date_input("Deposit Date", value=date.today(), key="deposit_date")

    if st.button("Add Deposit"):
        if deposit_amount <= 0:
            st.warning("⚠️ Enter a valid deposit amount.")
        else:
            # Update deposit history
            df_deposit = pd.concat(
                [df_deposit, pd.DataFrame([{"Player": deposit_player, "Date": str(deposit_date), "Amount": deposit_amount}])],
                ignore_index=True
            )
            # Update df_financial
            idx = df_financial.index[df_financial["Player"] == deposit_player][0]
            df_financial.at[idx, "Total Deposit"] += deposit_amount
            fee_cols = [c for c in df_financial.columns if "_Match" in c]
            df_financial.at[idx, "Balance"] = df_financial.at[idx, "Total Deposit"] - df_financial.loc[idx, fee_cols].sum()
            st.success(f"✅ Added deposit of {deposit_amount} for {deposit_player}")

    # -----------------------------
    # Display Financial Table
    # -----------------------------
    st.subheader("Team Financial Data")
    df_financial = df_financial.sort_values("Player").reset_index(drop=True)
    df_financial.index = df_financial.index + 1
    df_financial.index.name = "S.No"
    st.dataframe(df_financial)

    # -----------------------------
    # Display Deposit History
    # -----------------------------
    st.subheader("Deposit History")
    if not df_deposit.empty:
        df_deposit_display = df_deposit.sort_values(["Date", "Player"]).reset_index(drop=True)
        df_deposit_display.index = df_deposit_display.index + 1
        df_deposit_display.index.name = "S.No"
        st.dataframe(df_deposit_display)
    else:
        st.info("No deposits yet.")

    # -----------------------------
    # Save to Google Sheet
    # -----------------------------
    if st.button("💾 Save Financial Data to Google Sheet") and ws_financial and ws_deposit:
        try:
            # Save Financials
            ws_financial.clear()
            ws_financial.append_row(list(df_financial.columns))
            for _, r in df_financial.iterrows():
                ws_financial.append_row([r[c] for c in df_financial.columns])
                time.sleep(0.1)  # small delay to avoid quota issues
            # Save Deposit History
            ws_deposit.clear()
            ws_deposit.append_row(list(df_deposit.columns))
            for _, r in df_deposit.iterrows():
                ws_deposit.append_row([r[c] for c in df_deposit.columns])
                time.sleep(0.1)
            st.success("✅ Financial data and deposit history saved to Google Sheet")
        except Exception as e:
            st.error(f"❌ Failed to save data: {e}")
