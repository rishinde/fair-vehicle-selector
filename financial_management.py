import streamlit as st
import pandas as pd
from datetime import date
from utils import get_or_create_financial_ws, safe_get_financial_records

def financial_management_ui(players, client):
    st.header("3️⃣ Financial Management")

    if not players:
        st.info("No players available in superset")
        return

    # 1️⃣ Select players for this match
    selected_players = st.multiselect("Select players for this match:", sorted(players))

    # 2️⃣ Enter total match fee
    match_fee = st.number_input("Enter total match fee for this match:", min_value=0, step=100)

    # 3️⃣ Record fee
    if st.button("Record Match Fee") and selected_players and match_fee>0 and client:
        ws_financial = get_or_create_financial_ws(client)
        df = pd.DataFrame(safe_get_financial_records(ws_financial))

        # If no existing data, initialize
        for p in players:
            if p not in df['Player Name'].values:
                df = pd.concat([df, pd.DataFrame({"Player Name":[p], "Deposit":[0]})], ignore_index=True)

        # Add new column for this match
        match_col = "Match_" + date.today().strftime("%Y%m%d")
        if match_col not in df.columns:
            df[match_col] = 0

        # Distribute fee equally
        per_player_fee = match_fee / len(selected_players)
        df.loc[df['Player Name'].isin(selected_players), match_col] = per_player_fee

        # Compute balance
        fee_cols = [c for c in df.columns if c.startswith("Match_")]
        df['Balance'] = df['Deposit'] - df[fee_cols].sum(axis=1)

        # Save back to Google Sheet
        try:
            ws_financial.clear()
            ws_financial.append_row(df.columns.tolist())
            for i, row in df.iterrows():
                ws_financial.append_row(row.tolist())
            st.success(f"✅ Match fee recorded for {', '.join(selected_players)}")
        except Exception as e:
            st.error(f"❌ Failed to save financial data: {e}")

    # 4️⃣ Display financial table
    if client:
        ws_financial = get_or_create_financial_ws(client)
        df_display = pd.DataFrame(safe_get_financial_records(ws_financial))
        if not df_display.empty:
            st.dataframe(df_display)
