"""Streamlit dashboard for analyzing time-series CSV data from the VAWT prototype.

Usage:
    streamlit run tools/dashboard.py

Reads a CSV with columns:
    Time, Wind_Speed_m_s, Wind_Direction_deg, RPM, DC_Voltage_V, DC_Current_A, Power_W
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DEFAULT_CSV = "data/202609A.csv"


def load_csv(path: str) -> pd.DataFrame:
    """Load and parse the prototype measurement CSV."""
    df = pd.read_csv(path)
    df["Time"] = pd.to_datetime(df["Time"])
    df["Power_kW"] = df["Power_W"] / 1000.0
    df["Cp"] = (
        df["Power_W"]
        / (0.5 * 1.225 * (df["Wind_Speed_m_s"] ** 3) * (3.14159 * 0.906**2))
    )
    return df


def main():
    st.set_page_config(page_title="VAWT Prototype Dashboard", layout="wide")
    st.title("VAWT Prototype — Time-Series Analysis")

    # Sidebar controls
    st.sidebar.header("Data Source")
    csv_path = st.sidebar.text_input("CSV path", value=DEFAULT_CSV)

    try:
        df = load_csv(csv_path)
    except FileNotFoundError:
        st.error(f"CSV file not found: {csv_path}")
        st.stop()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error loading CSV: {exc}")
        st.stop()

    st.sidebar.header("Filters")
    power_min, power_max = st.sidebar.slider(
        "Power range (kW)",
        float(df["Power_kW"].min()),
        float(df["Power_kW"].max()),
        (float(df["Power_kW"].min()), float(df["Power_kW"].max())),
    )
    mask = (df["Power_kW"] >= power_min) & (df["Power_kW"] <= power_max)
    df_f = df[mask]

    st.metric("Data points", len(df_f))
    st.metric("Mean power (kW)", f"{df_f['Power_kW'].mean():.3f}")
    st.metric("Mean wind speed (m/s)", f"{df_f['Wind_Speed_m_s'].mean():.2f}")
    st.metric("Mean Cp", f"{df_f['Cp'].mean():.3f}")

    col1, col2 = st.columns(2)

    with col1:
        fig_power = go.Figure()
        fig_power.add_trace(
            go.Scatter(
                x=df_f["Time"],
                y=df_f["Power_kW"],
                mode="lines",
                name="Power (kW)",
                line={"color": "green"},
            )
        )
        fig_power.update_layout(
            title="Power vs Time",
            xaxis_title="Time",
            yaxis_title="Power (kW)",
            hovermode="x unified",
        )
        st.plotly_chart(fig_power, use_container_width=True)

    with col2:
        fig_wind = go.Figure()
        fig_wind.add_trace(
            go.Scatter(
                x=df_f["Time"],
                y=df_f["Wind_Speed_m_s"],
                mode="lines",
                name="Wind Speed (m/s)",
                line={"color": "blue"},
            )
        )
        fig_wind.update_layout(
            title="Wind Speed vs Time",
            xaxis_title="Time",
            yaxis_title="Wind Speed (m/s)",
            hovermode="x unified",
        )
        st.plotly_chart(fig_wind, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        fig_rpm = go.Figure()
        fig_rpm.add_trace(
            go.Scatter(
                x=df_f["Time"],
                y=df_f["RPM"],
                mode="lines",
                name="RPM",
                line={"color": "orange"},
            )
        )
        fig_rpm.update_layout(
            title="RPM vs Time",
            xaxis_title="Time",
            yaxis_title="RPM",
            hovermode="x unified",
        )
        st.plotly_chart(fig_rpm, use_container_width=True)

    with col4:
        fig_cp = go.Figure()
        fig_cp.add_trace(
            go.Scatter(
                x=df_f["Time"],
                y=df_f["Cp"],
                mode="lines",
                name="Cp",
                line={"color": "red"},
            )
        )
        fig_cp.update_layout(
            title="Power Coefficient Cp vs Time",
            xaxis_title="Time",
            yaxis_title="Cp",
            hovermode="x unified",
        )
        st.plotly_chart(fig_cp, use_container_width=True)

    # Power vs wind speed scatter
    fig_pv = go.Figure()
    fig_pv.add_trace(
        go.Scatter(
            x=df_f["Wind_Speed_m_s"],
            y=df_f["Power_kW"],
            mode="markers",
            name="Power vs Wind Speed",
            marker={"color": "purple", "size": 6, "opacity": 0.6},
        )
    )
    fig_pv.update_layout(
        title="Power vs Wind Speed",
        xaxis_title="Wind Speed (m/s)",
        yaxis_title="Power (kW)",
        hovermode="closest",
    )
    st.plotly_chart(fig_pv, use_container_width=True)

    # Raw data table
    st.subheader("Raw Data")
    st.dataframe(df_f, use_container_width=True)


if __name__ == "__main__":
    main()