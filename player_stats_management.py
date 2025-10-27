import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
import pandas as pd
import streamlit as st
import io

def extract_player_data_from_pdf(pdf_file):
    """Extract player stats from Cricheroes-style leaderboard PDF (supports OCR)."""
    all_data = []

    # Try text extraction first
    try:
        with pdfplumber.open(pdf_file) as pdf:
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

    # If text-based extraction failed or no data found, try OCR
    if not all_data:
        st.info("🧠 Running OCR on image-based PDF (this may take a few seconds)...")
        try:
            images = convert_from_bytes(pdf_file.read())
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
