import streamlit as st
import pandas as pd
import pdfplumber
import re
import time
import json

def player_stats_management(client):
    """
    Handles player stats upload (PDF → Google Sheet).
    Requires a valid gspread client with write access.
    """

    st.header("📊 Player Stats Management")
    st.caption("Upload batting leaderboard PDFs, extract player data, and save to Google Sheets")

    SHEET_NAME = "Team Management Data"
    STATS_TAB = "PlayerStats"

    # -----------------------------
    # Helper: Get or Create Sheet
    # -----------------------------
    ws_stats = None
    if client:
        try:
            existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
            sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)
            try:
                ws_stats = sh.worksheet(STATS_TAB)
            except:
                ws_stats = sh.add_worksheet(STATS_TAB, rows=200, cols=10)
                ws_stats.append_row(["Player", "Innings", "Runs", "Average", "StrikeRate"])
        except Exception as e:
            st.error(f"❌ Failed to open or create Google Sheet: {e}")
            ws_stats = None
    else:
        st.warning("⚠️ Google Sheets not available.")
        ws_stats = None

    # -----------------------------
    # PDF Upload Section
    # -----------------------------
    st.subheader("📤 Upload Batting Leaderboard PDF")
    uploaded_pdf = st.file_uploader("Upload leaderboard PDF", type=["pdf"])

    parsed_df = None

    if uploaded_pdf:
        try:
            with pdfplumber.open(uploaded_pdf) as pdf:
                text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
            
            # Regex pattern for lines like: "PlayerName   10   250   25.0   120.5"
            pattern = r"([A-Za-z\s]+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)"
            matches = re.findall(pattern, text)

            if matches:
                parsed_df = pd.DataFrame(matches, columns=["Player", "Innings", "Runs", "Average", "StrikeRate"])
                parsed_df["Innings"] = parsed_df["Innings"].astype(int)
                parsed_df["Runs"] = parsed_df["Runs"].astype(int)
                parsed_df["Average"] = parsed_df["Average"].astype(float)
                parsed_df["StrikeRate"] = parsed_df["StrikeRate"].astype(float)
                parsed_df["Player"] = parsed_df["Player"].str.strip()

                st.success(f"✅ Parsed {len(parsed_df)} player records from PDF")
                st.dataframe(parsed_df)
            else:
                st.warning("⚠️ No player data found in this PDF. Please verify formatting.")

        except Exception as e:
            st.error(f"❌ Failed to parse PDF: {e}")

    # -----------------------------
    # Save Parsed Data to Google Sheets
    # -----------------------------
    if parsed_df is not None and ws_stats:
        if st.button("💾 Save Stats to Google Sheet"):
            try:
                ws_stats.clear()
                ws_stats.append_row(list(parsed_df.columns))
                for _, row in parsed_df.iterrows():
                    ws_stats.append_row(row.tolist())
                    time.sleep(0.4)  # Prevent rate-limit errors
                st.success("✅ Player stats saved to Google Sheet successfully")
            except Exception as e:
                if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    st.error("⚠️ Google Sheets quota exceeded. Try again later.")
                else:
                    st.error(f"❌ Failed to save stats: {e}")

    # -----------------------------
    # Display Current Saved Stats
    # -----------------------------
    st.subheader("📈 Current Player Stats (from Google Sheet)")
    if ws_stats:
        try:
            records = ws_stats.get_all_records()
            if records:
                df_stats = pd.DataFrame(records)
                df_stats = df_stats.sort_values("Player").reset_index(drop=True)
                df_stats.index = df_stats.index + 1
                df_stats.index.name = "S.No"
                st.dataframe(df_stats)
            else:
                st.info("No player stats found yet. Upload a PDF to begin.")
        except Exception as e:
            st.warning(f"⚠️ Could not load PlayerStats from Google Sheet: {e}")
    else:
        st.info("Google Sheets connection unavailable.")
