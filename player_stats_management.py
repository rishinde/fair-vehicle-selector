import streamlit as st
import pandas as pd
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
from datetime import date
import io
import time

def extract_player_data_from_pdf(uploaded_file):
    """Extract player stats from Cricheroes-style leaderboard PDF (supports OCR fallback)."""
    all_data = []

    # --- Try standard text extraction first ---
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                lines = text.split("\n")
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 5 and parts[0].isdigit():
                        try:
                            rank = parts[0]
                            name = " ".join(parts[1:-3])
                            inns = parts[-3]
                            runs = parts[-2]
                            avg = parts[-1]
                            all_data.append({
                                "Rank": rank,
                                "Player": name,
                                "Innings": inns,
                                "Runs": runs,
                                "Average": avg
                            })
                        except:
                            continue
    except Exception as e:
        st.warning(f"⚠️ PDF text extraction failed: {e}")

    # --- OCR fallback if no text-based data found ---
    if not all_data:
        st.info("🧠 Running OCR on image-based PDF (this may take a few seconds)...")
        try:
            uploaded_file.seek(0)
            images = convert_from_bytes(uploaded_file.read())
            ocr_text = ""
            for img in images:
                ocr_text += pytesseract.image_to_string(img) + "\n"

            lines = ocr_text.split("\n")
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0].isdigit():
                    try:
                        rank = parts[0]
                        name = " ".join(parts[1:-3])
                        inns = parts[-3]
                        runs = parts[-2]
                        avg = parts[-1]
                        all_data.append({
                            "Rank": rank,
                            "Player": name,
                            "Innings": inns,
                            "Runs": runs,
                            "Average": avg
                        })
                    except:
                        continue
        except Exception as e:
            st.error(f"❌ OCR extraction failed: {e}")

    df = pd.DataFrame(all_data)
    return df


def player_stats_management(players, client):
    """Player Stats Management module for Team RRR app."""

    SHEET_NAME = "Team Player Stats"
    ws_stats = None
    df_stats = pd.DataFrame()

    # --- Setup Google Sheet connection ---
    if client:
        try:
            existing_sheets = [s['name'] for s in client.list_spreadsheet_files()]
            sh = client.open(SHEET_NAME) if SHEET_NAME in existing_sheets else client.create(SHEET_NAME)
            try:
                ws_stats = sh.worksheet("PlayerStats")
            except:
                ws_stats = sh.add_worksheet("PlayerStats", rows=200, cols=10)
                ws_stats.append_row(["Rank", "Player", "Innings", "Runs", "Average"])
        except Exception as e:
            st.error(f"Failed to open or create Player Stats sheet: {e}")
            ws_stats = None

    # --- Admin Upload Section ---
    if st.session_state.admin_logged_in:
        st.subheader("📤 Upload Player Stats PDF (Cricheroes Leaderboard)")
        uploaded_file = st.file_uploader("Upload batting leaderboard PDF", type=["pdf"])
        if uploaded_file:
            df_stats = extract_player_data_from_pdf(uploaded_file)
            if not df_stats.empty:
                st.success(f"✅ Extracted {len(df_stats)} player records from PDF.")
                st.dataframe(df_stats)
                if st.button("💾 Save Stats to Google Sheet") and ws_stats is not None:
                    try:
                        ws_stats.clear()
                        ws_stats.append_row(list(df_stats.columns))
                        for _, row in df_stats.iterrows():
                            ws_stats.append_row([row[c] for c in df_stats.columns])
                            time.sleep(0.2)
                        st.success("✅ Player stats saved successfully to Google Sheet!")
                    except Exception as e:
                        if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                            st.error("⚠️ Google Sheets quota exceeded. Please try again later.")
                        else:
                            st.error(f"❌ Failed to save player stats: {e}")
            else:
                st.warning("⚠️ No player data found in this PDF. Please verify formatting.")

    # --- Display Stats from Sheet ---
    st.subheader("📊 Player Stats Overview")
    if ws_stats:
        try:
            records = ws_stats.get_all_records()
            df_stats = pd.DataFrame(records)
            if not df_stats.empty:
                df_stats = df_stats.sort_values("Player")
                df_stats = df_stats.reset_index(drop=True)
                df_stats.index = df_stats.index + 1
                df_stats.index.name = "S.No"
                st.dataframe(df_stats)

                # Highlight Player Superset matches
                st.subheader("🎯 Player Superset vs Stats Availability")
                for p in sorted(players):
                    if p in df_stats["Player"].values:
                        st.write(f"✅ {p} — Stats Available")
                    else:
                        st.write(f"⚠️ {p} — No Data Found")
            else:
                st.info("ℹ️ No stats data available yet. Please upload a leaderboard PDF.")
        except Exception as e:
            st.warning(f"⚠️ Could not load stats data: {e}")
    else:
        st.info("ℹ️ Google Sheets not connected or PlayerStats sheet not available.")
