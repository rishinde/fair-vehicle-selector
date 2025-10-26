import streamlit as st
from vehicle_management import vehicle_management_ui
from financial_management import financial_management_ui
from datetime import date

# Google Sheets client and player superset loader
from utils import get_gsheet_client, load_gsheet_data

st.set_page_config(page_title="Fair Vehicle Selector", page_icon="🚗", layout="centered")
st.title("Team RRR Management")
st.caption("Management portal for Revanta Risers Ravet")

client = get_gsheet_client()

# Load data once
if client and "gsheet_data" not in st.session_state:
    st.session_state.gsheet_data = load_gsheet_data(client)

if client:
    ws_players, ws_vehicles, ws_groups, ws_history, players, vehicles, vehicle_groups, history, usage = st.session_state.gsheet_data
else:
    st.warning("⚠️ Google Sheets not available. Admin operations disabled.")
    players, vehicles, vehicle_groups, history, usage = [], [], {}, [], {}

# -----------------------------
# Tabs
# -----------------------------
tabs = st.tabs(["Player Superset", "Vehicle Management", "Financial Management"])

# Tab 0: Player Superset
with tabs[0]:
    from player_superset_ui import player_superset_ui
    player_superset_ui(players, ws_players, client)

# Tab 1: Vehicle Management
with tabs[1]:
    vehicle_management_ui(players, vehicles, vehicle_groups, history, usage, ws_players, ws_vehicles, ws_groups, ws_history, client)

# Tab 2: Financial Management
with tabs[2]:
    financial_management_ui(players, client)
