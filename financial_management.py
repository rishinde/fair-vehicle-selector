# financial_management.py
import streamlit as st
import pandas as pd
import json
from datetime import date

def financial_management(players, client):
    """
    Financial management module.
    - players: list of player names (read-only reference from Player Superset)
    - client: Google Sheets client object
    """

    # -----------------------------
    # Load or create 'Team Financial Data' worksheet
    # -----------------------------
    SHEET_NAME = "Team Financial Data"

    ws_financial = None
    df_financial = pd.DataFrame()
    
    if client:
        try:
            existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
            sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)
            try:
                ws_financial = sh.worksheet("Financials")
            except:
                ws_financial = sh.add_worksheet("Financials", rows=100, cols=50)
                # Initialize with Player + Total Deposit + Balance
                ws_financial.append_row(["Player", "Total Deposit", "Balance"])
        except Exception as e:
            st.error(f"Failed to open or create Financial Data sheet: {e}")
            ws_financial = None

    # -----------------------------
    # Load data into DataFrame
    # -----------------------------
    if ws_financial:
        try:
            records = ws_financial.get_all_records()
            df_financial = pd.DataFrame(records)
            # Ensure all players are present
            for p in players:
                if p not in df_financial.get("Player", []):
                    df_financial = pd.concat([df_financial, pd.DataFrame([{"Player": p, "Total Deposit": 0, "Balance": 0}])], ignore_index=True)
            df_financial.fillna(0, inplace=True)
        except Exception as e:
            st.warning(f"Failed to read financial data: {e}")
            df_financial = pd.DataFrame([{"Player": p, "Total Deposit": 0, "Balance": 0} for p in players])
    else:
        df_financial = pd.DataFrame([{"Player": p, "Total Deposit": 0, "Balance": 0} for p in players])

    # -----------------------------
    # Display Player Superset Reference
    # -----------------------------
    st.subheader("Players Reference (read-only)")
    st.write(", ".join(sorted(players)))

    # -----------------------------
    # Match Fee Entry Section
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
            # Calculate fee per player
            fee_per_player = round(total_fee / len(players_today), 2)
            # Create column name: YYYY-MM-DD_MatchN
            existing_match_cols = [c for c in df_financial.columns if "_Match" in c]
            match_number = len(existing_match_cols) + 1
            new_col_name = f"{match_date}_Match{match_number}"
            df_financial[new_col_name] = 0.0

            # Assign fees to selected players
            for idx, row in df_financial.iterrows():
                if row["Player"] in players_today:
                    df_financial.at[idx, new_col_name] = fee_per_player

            # Recalculate Balance
            fee_cols = [c for c in df_financial.columns if "_Match" in c]
            df_financial["Balance"] = df_financial["Total Deposit"] - df_financial[fee_cols].sum(axis=1)

            st.success(f"✅ Match fees added for {len(players_today)} players. Fee per player: {fee_per_player}")
    
    # -----------------------------
    # Display Financial Table
    # -----------------------------
    st.subheader("Team Financial Data")
    df_financial = df_financial.sort_values("Player")
    df_financial = df_financial.reset_index(drop=True)
    df_financial.index = df_financial.index + 1
    df_financial.index.name = "S.No"
    st.dataframe(df_financial)

    # -----------------------------
    # Save to Google Sheet
    # -----------------------------
    if st.button("💾 Save Financial Data to Google Sheet") and ws_financial:
        try:
            ws_financial.clear()
            ws_financial.append_row(list(df_financial.columns))
            for _, r in df_financial.iterrows():
                ws_financial.append_row([r[c] for c in df_financial.columns])
            st.success("✅ Financial data saved to Google Sheet")
        except Exception as e:
            st.error(f"❌ Failed to save financial data: {e}")

