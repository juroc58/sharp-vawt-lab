"""Streamlit dashboard for analyzing time-series CSV data.

Handles both Weather Station data (Wind Speed, Solar) and VAWT Prototype data 
(Power_W, RPM, etc.).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="VAWT & Weather Dashboard", layout="wide")
st.title("📈 Time Series Visualization & Analysis Dashboard")

DEFAULT_CSV = "data/weather_data.csv"

@st.cache_data
def load_data(file):
    # 1. Load the file (handles both path strings and UploadedFile objects)
    if isinstance(file, str):
        df = pd.read_csv(file, na_values=["--", "", " ", "NaN", "null"])
    else:
        # If it's an uploaded file, check extension
        if file.name.endswith('.xlsx') or file.name.endswith('.xls'):
            df = pd.read_excel(file, na_values=["--", "", " ", "NaN", "null"])
        else:
            df = pd.read_csv(file, na_values=["--", "", " ", "NaN", "null"])

    # 2. Auto-detect timestamp column
    time_col = None
    for col in df.columns:
        if "time" in col.lower() or "date" in col.lower():
            time_col = col
            break

    if time_col:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col).reset_index(drop=True)
        if time_col != "Time":
            df.rename(columns={time_col: "Time"}, inplace=True)
    else:
        st.error("No valid timestamp/time column found in the file.")
        st.stop()

    # Clean numeric columns
    for col in df.columns:
        if col != "Time":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 3. Conditionally add VAWT calculations if columns exist
    # (Matches the schema in data/measured_template.csv)
    if "Power_W" in df.columns and "Wind_Speed_m_s" in df.columns:
        df["Power_kW"] = df["Power_W"] / 1000.0
        # Cp = P / (0.5 * rho * A * v^3). Area for R=0.906 is 2.58 m^2
        area = np.pi * 0.906**2
        df["Cp"] = df["Power_W"] / (0.5 * 1.225 * (df["Wind_Speed_m_s"] ** 3) * area)
        
    return df


def compute_time_integral(series, time_series, unit="hours"):
    valid_data = pd.DataFrame({"t": time_series, "v": series}).dropna()
    if len(valid_data) < 2:
        return np.nan
    seconds = (valid_data["t"] - valid_data["t"].min()).dt.total_seconds()
    time_delta = seconds / 3600.0 if unit == "hours" else seconds
    if hasattr(np, "trapezoid"):
        return np.trapezoid(valid_data["v"], time_delta)
    else:
        return np.trapz(valid_data["v"], time_delta)


# --- Sidebar Data Source ---
st.sidebar.header("📁 Data Source")
uploaded_file = st.sidebar.file_uploader(
    "Choose a CSV or Excel file", type=["csv", "xlsx"]
)

try:
    if uploaded_file is not None:
        df = load_data(uploaded_file)
        st.sidebar.success(f"Loaded: `{uploaded_file.name}`")
    else:
        df = load_data(DEFAULT_CSV)
        st.sidebar.info(f"Using default file: `{DEFAULT_CSV}`")
except Exception as e:
    st.sidebar.warning(f"Could not load default file. Please upload one. ({e})")
    st.stop()

# --- Axis Selection ---
numeric_cols = [
    col for col in df.columns
    if col not in ["Time", "Timestamp"] and pd.api.types.is_numeric_dtype(df[col])
]

st.sidebar.subheader("Axis Selection")
primary_vars = st.sidebar.multiselect(
    "Primary Y-Axis Quantities:",
    options=numeric_cols,
    default=[numeric_cols[0]] if numeric_cols else [],
)
secondary_cols = [c for c in numeric_cols if c not in primary_vars]
secondary_vars = st.sidebar.multiselect(
    "Secondary Y-Axis Quantities:",
    options=secondary_cols,
    default=[secondary_cols[0]] if len(secondary_cols) > 0 else [],
)

chart_type = st.sidebar.radio("Chart Type:", options=["Line", "Scatter"])

# --- Plotting ---
selected_quantities = primary_vars + secondary_vars

if not selected_quantities:
    st.warning("Please select at least one quantity for Primary or Secondary Y-Axis.")
else:
    fig = go.Figure()
    mode = "lines" if chart_type == "Line" else "markers"

    for col in primary_vars:
        fig.add_trace(go.Scatter(
            x=df["Time"], y=df[col], mode=mode, name=f"{col} (Primary)", yaxis="y", connectgaps=True
        ))
    for col in secondary_vars:
        fig.add_trace(go.Scatter(
            x=df["Time"], y=df[col], mode=mode, name=f"{col} (Secondary)", yaxis="y2", connectgaps=True
        ))

    fig.update_layout(
        title="Time Series Plot (Zoom/Drag on graph to update statistics)",
        xaxis=dict(title="Time"),
        yaxis=dict(title=", ".join(primary_vars) if primary_vars else "Primary Axis", side="left"),
        yaxis2=dict(
            title=", ".join(secondary_vars) if secondary_vars else "Secondary Axis",
            side="right", overlaying="y", showgrid=False,
        ),
        hovermode="x unified",
        legend=dict(x=0, y=1.1, orientation="h"),
        template="plotly_white",
        height=520,
    )

    chart_event = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun", selection_mode=["box", "lasso"], key="time_series_chart"
    )

    # --- Graph Interaction Filtering ---
    stats_df_source = df
    graph_subset_active = False

    if chart_event and "selection" in chart_event:
        selection_data = chart_event["selection"]
        if "points" in selection_data and len(selection_data["points"]) > 0:
            selected_x_vals = pd.to_datetime(list(set(p["x"] for p in selection_data["points"] if "x" in p)))
            if len(selected_x_vals) > 0:
                stats_df_source = df[df["Time"].isin(selected_x_vals)].sort_values("Time")
                graph_subset_active = True
        elif "box" in selection_data and len(selection_data["box"]) > 0:
            x_bounds = selection_data["box"][0].get("x", [])
            if len(x_bounds) == 2:
                t_start, t_end = pd.to_datetime(x_bounds[0]), pd.to_datetime(x_bounds[1])
                stats_df_source = df[(df["Time"] >= t_start) & (df["Time"] <= t_end)]
                graph_subset_active = True

    # --- Status & Statistics ---
    st.markdown(
        f"**Active Data Range:** `{stats_df_source['Time'].min()}` to `{stats_df_source['Time'].max()}` | "
        f"**Records Evaluated:** `{len(stats_df_source)}`"
    )

    st.markdown("---")
    st.subheader("📊 Descriptive Statistics & Time Integrals")

    if graph_subset_active:
        st.info("💡 Statistics updated from graph selection. Double-click the graph to reset.")

    if not stats_df_source.empty:
        stats_summary = stats_df_source[selected_quantities].describe().T
        stats_summary = stats_summary.rename(columns={
            "count": "Count", "mean": "Mean", "std": "Std Dev", "min": "Min",
            "25%": "25th Pct", "50%": "Median", "75%": "75th Pct", "max": "Max",
        })

        integrals_hr = []
        for col in selected_quantities:
            i_hr = compute_time_integral(stats_df_source[col], stats_df_source["Time"], unit="hours")
            integrals_hr.append(i_hr)

        stats_summary["Integral (val · hr)"] = integrals_hr
        st.dataframe(stats_summary.style.format("{:.2f}"), use_container_width=True)
    else:
        st.warning("No records found in current selection.")

    # --- Conditionally Show VAWT Analysis if it's prototype data ---
    if "Power_W" in stats_df_source.columns:
        st.markdown("---")
        st.subheader("💨 VAWT Performance Analysis")
        
        col1, col2 = st.columns(2)
        with col1:
            fig_pv = go.Figure()
            fig_pv.add_trace(go.Scatter(
                x=stats_df_source["Wind_Speed_m_s"], y=stats_df_source["Power_W"],
                mode="markers", name="Power vs Wind Speed",
                marker={"color": "purple", "size": 6, "opacity": 0.6},
            ))
            fig_pv.update_layout(title="Power vs Wind Speed", xaxis_title="Wind Speed (m/s)", yaxis_title="Power (W)")
            st.plotly_chart(fig_pv, use_container_width=True)
            
        with col2:
            fig_cp = go.Figure()
            fig_cp.add_trace(go.Scatter(
                x=stats_df_source["Wind_Speed_m_s"], y=stats_df_source["Cp"],
                mode="markers", name="Cp vs Wind Speed",
                marker={"color": "red", "size": 6, "opacity": 0.6},
            ))
            fig_cp.update_layout(title="Cp vs Wind Speed", xaxis_title="Wind Speed (m/s)", yaxis_title="Cp")
            st.plotly_chart(fig_cp, use_container_width=True)

    st.subheader("Raw Data")
    st.dataframe(stats_df_source, use_container_width=True)