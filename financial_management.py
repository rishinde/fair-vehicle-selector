# financial_management.py
import streamlit as st
import pandas as pd
import time
from datetime import date
import io

# Configuration: adjust delays if you still hit quotas
ROW_WRITE_DELAY = 0.12  # seconds between append_row calls

def _is_quota_error(e):
    msg = str(e).lower()
    return "quota" in msg or "rate limit" in msg or "rate-limit" in msg or "rate_limit" in msg

def _safe_append_rows(ws, rows, header=None):
    """
    Append multiple rows to a gspread worksheet with delays.
    If header provided, prepend the header row (used when rewriting table).
    Returns (ok, message)
    """
    try:
        if header:
            ws.append_row(header)
            time.sleep(ROW_WRITE_DELAY)
        for r in rows:
            # convert to list of strings (gspread-friendly)
            ws.append_row([("" if v is None else v) for v in r])
            time.sleep(ROW_WRITE_DELAY)
        return True, "OK"
    except Exception as e:
        if _is_quota_error(e):
            return False, "quota"
        return False, str(e)

def financial_management(players, client):
    """
    players: list of player names (read-only reference from Player Superset)
    client: gspread client or None
    """

    SHEET_NAME = "Team Financial Data"
    ws_financial = None
    ws_deposit = None

    # -----------------------------
    # Prepare sheets (open / create)
    # -----------------------------
    if client:
        try:
            # try opening or creating the spreadsheet
            existing = [s["name"] for s in client.list_spreadsheet_files()]
            sh = client.open(SHEET_NAME) if SHEET_NAME in existing else client.create(SHEET_NAME)

            # Financials sheet
            try:
                ws_financial = sh.worksheet("Financials")
            except Exception:
                ws_financial = sh.add_worksheet("Financials", rows=200, cols=80)
                ws_financial.append_row(["Player", "Total Deposit", "Balance"])  # header

            # DepositHistory sheet
            try:
                ws_deposit = sh.worksheet("DepositHistory")
            except Exception:
                ws_deposit = sh.add_worksheet("DepositHistory", rows=200, cols=20)
                ws_deposit.append_row(["Player", "Date", "Amount"])  # header
        except Exception as e:
            st.error(f"Failed to open or create Financial Data sheet: {e}")
            ws_financial = None
            ws_deposit = None
    else:
        st.info("Google Sheets not connected — financial module running in local-only mode.")

    # -----------------------------
    # Load existing Financials
    # -----------------------------
    if ws_financial:
        try:
            fin_records = ws_financial.get_all_records()
            df_fin = pd.DataFrame(fin_records)
        except Exception as e:
            st.warning(f"Failed to read Financials sheet: {e}")
            df_fin = pd.DataFrame()
    else:
        df_fin = pd.DataFrame()

    # Normalize column names if empty
    if df_fin.empty:
        df_fin = pd.DataFrame(columns=["Player", "Total Deposit", "Balance"])

    # Ensure 'Player' column is string and strip whitespace
    df_fin["Player"] = df_fin.get("Player", pd.Series(dtype=str)).astype(str).str.strip()
    # Ensure numeric columns exist
    if "Total Deposit" not in df_fin.columns:
        df_fin["Total Deposit"] = 0.0
    if "Balance" not in df_fin.columns:
        df_fin["Balance"] = 0.0

    # Ensure all players from superset are present in df_fin
    existing_players = set(df_fin["Player"].dropna().astype(str))
    new_rows_needed = []
    for p in players:
        p = str(p).strip()
        if p not in existing_players:
            new_rows_needed.append({"Player": p, "Total Deposit": 0.0, "Balance": 0.0})
            existing_players.add(p)
    if new_rows_needed:
        df_fin = pd.concat([df_fin, pd.DataFrame(new_rows_needed)], ignore_index=True)
        df_fin.fillna(0.0, inplace=True)

    # -----------------------------
    # Load existing DepositHistory
    # -----------------------------
    if ws_deposit:
        try:
            dep_records = ws_deposit.get_all_records()
            df_dep = pd.DataFrame(dep_records)
        except Exception as e:
            st.warning(f"Failed to read DepositHistory sheet: {e}")
            df_dep = pd.DataFrame(columns=["Player", "Date", "Amount"])
    else:
        df_dep = pd.DataFrame(columns=["Player", "Date", "Amount"])

    # Fix column dtypes
    if "Amount" in df_dep.columns:
        df_dep["Amount"] = pd.to_numeric(df_dep["Amount"], errors="coerce").fillna(0.0)

    # Make sure Total Deposit matches deposit history (recompute)
    # Recompute total deposits from deposit history to keep consistent.
    if not df_dep.empty:
        deposit_sums = df_dep.groupby("Player", sort=False)["Amount"].sum().to_dict()
        # Add to existing Total Deposit (if sheet had prior totals, we'll prefer recomputed sums)
        # Decide: prefer sheet Total Deposit if present and non-zero? To keep deterministic, use deposit_sums as canonical.
        for idx, row in df_fin.iterrows():
            p = row["Player"]
            if p in deposit_sums:
                df_fin.at[idx, "Total Deposit"] = float(deposit_sums.get(p, 0.0))
    else:
        # ensure numeric
        df_fin["Total Deposit"] = pd.to_numeric(df_fin["Total Deposit"], errors="coerce").fillna(0.0)

    # Recompute balance from existing match columns (any column that isn't Player/Total Deposit/Balance)
    match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
    if match_cols:
        # numeric conversion for match columns
        for c in match_cols:
            df_fin[c] = pd.to_numeric(df_fin[c], errors="coerce").fillna(0.0)
        df_fin["Balance"] = df_fin["Total Deposit"] - df_fin[match_cols].sum(axis=1)
    else:
        df_fin["Balance"] = df_fin["Total Deposit"]

    # -----------------------------
    # UI: Reference & CSV downloads
    # -----------------------------
    st.subheader("Players Reference (read-only)")
    st.write(", ".join(sorted(players)) if players else "No players available")

    st.markdown("---")
    st.subheader("📊 Team Financial Summary")
    # Order columns: Player, Total Deposit, Balance, then match columns sorted
    match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
    match_cols_sorted = sorted(match_cols)
    ordered_cols = ["Player", "Total Deposit", "Balance"] + match_cols_sorted
    # ensure columns exist
    ordered_cols = [c for c in ordered_cols if c in df_fin.columns]
    df_display = df_fin[ordered_cols].copy()
    df_display = df_display.sort_values("Player").reset_index(drop=True)
    df_display.index = df_display.index + 1
    df_display.index.name = "S.No"
    st.dataframe(df_display)

    # CSV download for financials
    csv_buf = io.StringIO()
    df_display.to_csv(csv_buf, index=True)
    st.download_button("📥 Download Financial Summary (CSV)", csv_buf.getvalue(), file_name="financial_summary.csv", mime="text/csv")

    st.markdown("---")
    st.subheader("🧾 Deposit History")
    if not df_dep.empty:
        df_dep_display = df_dep.sort_values(["Date", "Player"], ascending=[False, True]).reset_index(drop=True)
        df_dep_display.index = df_dep_display.index + 1
        df_dep_display.index.name = "S.No"
        st.dataframe(df_dep_display)
        csv_dep = io.StringIO()
        df_dep_display.to_csv(csv_dep, index=True)
        st.download_button("📥 Download Deposit History (CSV)", csv_dep.getvalue(), file_name="deposit_history.csv", mime="text/csv")
    else:
        st.info("No deposits recorded yet.")

    st.markdown("---")
    # -----------------------------
    # Match Fee Entry (in-memory)
    # -----------------------------
    st.subheader("➕ Match Fee Entry (add in-memory)")
    col1, col2 = st.columns([1, 2])
    with col1:
        match_date = st.date_input("Match Date", value=date.today(), key="match_date")
    with col2:
        ground_name = st.text_input("Ground / Ground code (optional)", key="match_ground")

    players_today = st.multiselect("Players Attending", sorted(players), key="match_players")
    total_fee = st.number_input("Total Match Fee (per match)", min_value=0.0, value=0.0, step=1.0, key="match_fee")

    if st.button("Add Match (in memory)"):
        if not players_today:
            st.warning("Select at least one player.")
        elif total_fee <= 0:
            st.warning("Enter a valid total fee (> 0).")
        else:
            # create a clean column name
            base = f"{match_date.isoformat()}"
            if ground_name and ground_name.strip():
                base = f"{base}_{ground_name.strip().replace(' ', '_')}"
            # ensure uniqueness - if same date+ground exists, append counter
            candidate = base + "_Match"
            i = 1
            while f"{candidate}{i}" in df_fin.columns:
                i += 1
            colname = f"{candidate}{i}"

            df_fin[colname] = 0.0
            fee_per_player = round(float(total_fee) / len(players_today), 2)
            for idx, row in df_fin.iterrows():
                if row["Player"] in players_today:
                    df_fin.at[idx, colname] = fee_per_player

            # update balances
            match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
            for c in match_cols:
                df_fin[c] = pd.to_numeric(df_fin[c], errors="coerce").fillna(0.0)
            df_fin["Balance"] = df_fin["Total Deposit"] - df_fin[match_cols].sum(axis=1)

            st.success(f"Match added in memory as '{colname}' (fee per player: {fee_per_player}). Use 'Save Match to Google Sheet' to persist.")

    # Save match to sheet (writes entire Financials sheet)
    if st.button("💾 Save Match to Google Sheet"):
        if not ws_financial:
            st.warning("Google Sheets not connected.")
        else:
            try:
                # Reorder columns before writing
                match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
                ordered_cols = ["Player", "Total Deposit", "Balance"] + sorted(match_cols)
                rows = []
                header = ordered_cols
                for _, r in df_fin[ordered_cols].iterrows():
                    rows.append([r[c] for c in ordered_cols])
                # Clear and write header + rows
                ws_financial.clear()
                ok, msg = _safe_append_rows(ws_financial, rows, header=header)
                if not ok:
                    if msg == "quota":
                        st.error("⚠️ Google Sheets quota exceeded while saving Financials. Try again later.")
                    else:
                        st.error(f"❌ Failed saving Financials: {msg}")
                else:
                    st.success("✅ Financials saved to Google Sheet.")
            except Exception as e:
                if _is_quota_error(e):
                    st.error("⚠️ Google Sheets quota exceeded while saving Financials. Try again later.")
                else:
                    st.error(f"❌ Failed to save Financials: {e}")

    st.markdown("---")
    # -----------------------------
    # Deposit Entry (can select multiple players, same amount applied to all)
    # -----------------------------
    st.subheader("💵 Deposit Entry (add to history in-memory)")
    colp, cola = st.columns([2,1])
    with colp:
        deposit_players = st.multiselect("Select Player(s)", sorted(players), key="deposit_players")
    with cola:
        deposit_amount = st.number_input("Amount (per player)", min_value=0.0, value=0.0, step=1.0, key="deposit_amount")
    deposit_date = st.date_input("Deposit Date", value=date.today(), key="deposit_date_field")

    if st.button("Add Deposit(s) (in memory)"):
        if not deposit_players:
            st.warning("Select at least one player.")
        elif deposit_amount <= 0:
            st.warning("Enter a valid deposit amount (>0).")
        else:
            for pl in deposit_players:
                df_dep = pd.concat([df_dep, pd.DataFrame([{"Player": pl, "Date": str(deposit_date), "Amount": float(deposit_amount)}])], ignore_index=True)
                # update df_fin Total Deposit for that player
                idxs = df_fin.index[df_fin["Player"] == pl].tolist()
                if idxs:
                    idx = idxs[0]
                    df_fin.at[idx, "Total Deposit"] = float(df_fin.at[idx, "Total Deposit"]) + float(deposit_amount)
                else:
                    # add row if player missing
                    df_fin = pd.concat([df_fin, pd.DataFrame([{"Player": pl, "Total Deposit": float(deposit_amount), "Balance": float(deposit_amount)}])], ignore_index=True)
            # recalc balances
            match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
            if match_cols:
                for c in match_cols:
                    df_fin[c] = pd.to_numeric(df_fin[c], errors="coerce").fillna(0.0)
                df_fin["Balance"] = df_fin["Total Deposit"] - df_fin[match_cols].sum(axis=1)
            else:
                df_fin["Balance"] = df_fin["Total Deposit"]
            st.success(f"✅ Added deposits for {len(deposit_players)} player(s). Use 'Save Deposits to Google Sheet' to persist.")

    # Save deposit history to Google Sheet (append all deposit records)
    if st.button("💾 Save Deposits to Google Sheet"):
        if not ws_deposit or not ws_financial:
            st.warning("Google Sheets not connected.")
        else:
            try:
                # Write deposit history: rewrite entire sheet from df_dep
                ws_deposit.clear()
                header = list(df_dep.columns) if not df_dep.empty else ["Player", "Date", "Amount"]
                rows = []
                for _, r in df_dep.iterrows():
                    rows.append([r.get(c, "") for c in header])
                ok, msg = _safe_append_rows(ws_deposit, rows, header=header)
                if not ok:
                    if msg == "quota":
                        st.error("⚠️ Google Sheets quota exceeded while saving deposits. Try again later.")
                    else:
                        st.error(f"❌ Failed saving deposits: {msg}")
                else:
                    st.success("✅ Deposit history saved to Google Sheet.")
                # Now also save the financials (since totals changed)
                # Save df_fin to ws_financial as well
                match_cols = [c for c in df_fin.columns if c not in ["Player", "Total Deposit", "Balance"]]
                ordered_cols = ["Player", "Total Deposit", "Balance"] + sorted(match_cols)
                rows_fin = []
                header_fin = ordered_cols
                for _, r in df_fin[ordered_cols].iterrows():
                    rows_fin.append([r.get(c, "") for c in ordered_cols])
                ws_financial.clear()
                ok2, msg2 = _safe_append_rows(ws_financial, rows_fin, header=header_fin)
                if not ok2:
                    if msg2 == "quota":
                        st.error("⚠️ Google Sheets quota exceeded while saving Financials after deposit. Try again later.")
                    else:
                        st.error(f"❌ Failed saving Financials after deposit: {msg2}")
                else:
                    st.success("✅ Financials updated on Google Sheet after deposit.")
            except Exception as e:
                if _is_quota_error(e):
                    st.error("⚠️ Google Sheets quota exceeded while saving deposits/financials. Try again later.")
                else:
                    st.error(f"❌ Failed to save deposits/financials: {e}")

    st.markdown("---")
    st.info("Note: All writes to Google Sheets are done only when you press the relevant **Save** button. Admins can control when to persist changes to avoid hitting API quotas.")
