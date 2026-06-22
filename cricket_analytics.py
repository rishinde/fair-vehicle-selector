import streamlit as st
import pandas as pd
import datetime


def cricket_analytics(players, client):

    st.header("🏏 Cricket Analytics")

    match_date = st.date_input(
        "Match Date",
        value=datetime.date.today()
    )

    st.subheader("📋 Enter Scorecard")

    out_options = [
        "Out",
        "Not Out",
        "Did Not Bat"
    ]

    rows = []

    st.markdown(
        """
        | Pos | Player | Runs | Balls | Out |
        """
    )

    for pos in range(1, 12):

        c1, c2, c3, c4, c5 = st.columns(
            [1, 3, 1, 1, 2]
        )

        with c1:
            st.text(pos)

        with c2:
            player = st.selectbox(
                "",
                [""] + sorted(players),
                key=f"player_{pos}",
                label_visibility="collapsed"
            )

        with c3:
            runs = st.number_input(
                "",
                min_value=0,
                value=0,
                key=f"runs_{pos}",
                label_visibility="collapsed"
            )

        with c4:
            balls = st.number_input(
                "",
                min_value=0,
                value=0,
                key=f"balls_{pos}",
                label_visibility="collapsed"
            )

        with c5:
            out_type = st.selectbox(
                "",
                out_options,
                key=f"out_{pos}",
                label_visibility="collapsed"
            )

        rows.append({
            "Position": pos,
            "Player": player,
            "Runs": runs,
            "Balls": balls,
            "Out": out_type
        })

    st.markdown("---")

    if st.button("💾 Save Scorecard"):

        used = [
            r["Player"]
            for r in rows
            if r["Player"]
        ]

        duplicates = [
            p for p in used
            if used.count(p) > 1
        ]

        if duplicates:
            st.error(
                f"Duplicate players selected: {set(duplicates)}"
            )
            st.stop()

        scorecard = {
            "date": str(match_date),
            "scorecard": rows
        }

        if "scorecards" not in st.session_state:
            st.session_state["scorecards"] = []

        st.session_state["scorecards"].append(
            scorecard
        )

        st.success("✅ Scorecard Saved")

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True
        )