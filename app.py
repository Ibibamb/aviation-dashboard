import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

# 1. Page Configuration (Enforcing the 16:9 minimalist layout)
st.set_page_config(page_title="UK Aviation Recovery", layout="wide", initial_sidebar_state="collapsed")

# --- CUSTOM CSS ---
# This hides standard Streamlit borders and makes the KPI cards look like your design
st.markdown("""
    <style>
    /* Reduce native Streamlit top padding to reclaim whitespace */
    .block-container {
        padding-top: 2rem !important;
    }
    div[data-testid="stMetric"] {
        border: 1px solid #E6E9EF;
        padding: 5% 5% 5% 10%;
        border-radius: 8px;
        box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.05);
    }
    </style>
""", unsafe_allow_html=True)

# 2. Data Engine (Enforcing the 3-Second Performance Rule)
@st.cache_data
def load_data():
    """Loads data from SQLite and caches it in RAM so filters apply instantly."""
    # Update this path if your DB is saved elsewhere
    db_path = "aviation_dashboard.db"
    
    # Auto-seed the database if it doesn't exist (e.g. on Streamlit Cloud deployment)
    if not os.path.exists(db_path):
        csv_path = "aviation_dashboard.csv"
        if os.path.exists(csv_path):
            seed_df = pd.read_csv(csv_path)
            conn = sqlite3.connect(db_path)
            seed_df.to_sql("passenger_trends", conn, if_exists="replace", index=False)
            conn.close()
        else:
            st.error(f"Missing data source! Both `{db_path}` and `{csv_path}` are missing.")
            st.stop()

    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM passenger_trends", conn)
    conn.close()
    
    # Ensure correct data types
    df['Year'] = df['Year'].astype(int)
    # Handle month names (e.g. "January") OR numeric months stored as strings.
    # NOTE: Pandas 3.x changed string column dtype from `object` to `string[pyarrow]`,
    # so we can no longer rely on `dtype == object` to detect string columns.
    # Instead, we check if the column actually contains non-numeric values.
    month_sample = df['Month'].dropna().iloc[0] if not df['Month'].dropna().empty else None
    if month_sample is not None and not str(month_sample).isdigit():
        try:
            # Try parsing full month names like "January", "February" etc.
            df['Month'] = pd.to_datetime(df['Month'].astype(str), format='%B').dt.month
        except ValueError:
            # Fallback: try abbreviated names like "Jan", "Feb" etc.
            df['Month'] = pd.to_datetime(df['Month'].astype(str), format='%b').dt.month
    else:
        df['Month'] = pd.to_numeric(df['Month'], errors='coerce').astype('Int64')
    return df

df = load_data()

# 3. Dashboard Header
st.title("UK Aviation Recovery")
st.markdown("*(Analytics Dashboard)*")
st.markdown("---")

# 4. The Control Center (Top Navbar)
available_years = sorted(df['Year'].unique())
available_airports = sorted(df['Airport'].unique())

# Define a consistent corporate color palette for all airports across charts
# 5 airports in DB → 5 distinct, high-contrast colors
THEME_COLORS = ['#1A4F8A', '#00A896', '#82A6CB', '#E8724A', '#6C5CE7']  # Navy, Teal, Sky, Coral, Violet
airport_colors = {airport: THEME_COLORS[i % len(THEME_COLORS)] for i, airport in enumerate(available_airports)}

# Side-by-side Layout for Filters
filter_col1, filter_col2 = st.columns(2, gap="large")

with filter_col1:
    selected_years = st.multiselect(
        "Timeline (Select Years)", 
        options=available_years, 
        default=available_years
    )

with filter_col2:
    selected_airports = st.multiselect(
        "Compare Airports (Max 3)",
        options=available_airports,
        default=["HEATHROW", "GATWICK"],
        max_selections=3  # Streamlit automatically prevents selecting a fourth option
    )

# 5. Apply Filters to Data
filtered_df = df[(df['Year'].isin(selected_years)) & (df['Airport'].isin(selected_airports))]

# 5. The KPI Ribbon (Top Row)
st.markdown("### Overview")

if not filtered_df.empty:
    kpi1, kpi2, kpi3 = st.columns(3)
    
    # Calculate Total Passengers
    total_pax = filtered_df['Total Passengers'].sum()
    
    # Calculate System Volatility (CV) for the selected data
    mean_pax = filtered_df.groupby(['Year', 'Month'])['Total Passengers'].sum().mean()
    std_pax = filtered_df.groupby(['Year', 'Month'])['Total Passengers'].sum().std()
    cv_score = std_pax / mean_pax if mean_pax > 0 else 0
    
    # Calculate rough YoY trend (comparing max selected year to min selected year)
    min_year = min(selected_years)
    max_year = max(selected_years)
    if min_year != max_year:
        start_pax = df[(df['Year'] == min_year) & (df['Airport'].isin(selected_airports))]['Total Passengers'].sum()
        end_pax = df[(df['Year'] == max_year) & (df['Airport'].isin(selected_airports))]['Total Passengers'].sum()
        yoy_growth = ((end_pax - start_pax) / start_pax) * 100 if start_pax > 0 else 0
        trend_label = f"Growth ({min_year}-{max_year})"
    else:
        yoy_growth = 0
        trend_label = "Select multiple years for growth"

    # Render the Cards
    with kpi1:
        st.metric(label="Total Passengers", value=f"{total_pax / 1000000:.1f}M", delta="—", delta_color="off")
    with kpi2:
        st.metric(label=trend_label, value=f"{yoy_growth:+.1f}%" if min_year != max_year else "-", delta="—", delta_color="off")
    with kpi3:
        st.metric(
            label="Volatility Score (CV)", 
            value=f"{cv_score:.3f}", 
            delta="Stable" if cv_score < 0.8 else "Volatile", 
            delta_color="inverse",
            help="Coefficient of Variation (Standard Deviation ÷ Mean). Scores under 0.8 mark stable, predictable traffic. Scores over 0.8 indicate highly volatile/seasonal swings."
        )

else:
    st.warning("Please select at least one Year and one Airport from the sidebar to view data.")

st.markdown("---")

# ==========================================
# PHASE 2: DASHBOARD VISUALIZATIONS
# ==========================================

st.markdown("### Aviation Recovery Trends")

if not filtered_df.empty:
    
    # --- CHART 1: The Macro View (Time-Series) ---
    # Prepare chronological data
    monthly_trend = filtered_df.groupby(['Year', 'Month', 'Airport'])['Total Passengers'].sum().reset_index()
    # Create a proper datetime object so Plotly automatically sorts chronologically
    monthly_trend['Date'] = pd.to_datetime(monthly_trend['Year'].astype(str) + '-' + monthly_trend['Month'].astype(str).str.zfill(2) + '-01')
    
    fig1 = px.line(
        monthly_trend, 
        x='Date', 
        y='Total Passengers', 
        color='Airport',
        color_discrete_map=airport_colors, # Unify palette mapping
        markers=True,
        title="Post-Pandemic Recovery Arc"
    )
    
    # Minimalist Plotly Styling
    fig1.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(showgrid=True, gridcolor='#E6E9EF', title=None),
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig1, width='stretch')
    
    st.markdown("<br>", unsafe_allow_html=True) # Whitespace spacer
    
    # --- THE MICRO VIEW (Bottom Row) ---
    col1, col2 = st.columns(2, gap="large")
    
    with col1:
        # CHART 2: Market Structure — Horizontal 100% Stacked Bar
        # Using go.Figure with explicit traces: one per segment.
        # px.bar with melted data renders separate rows per year — go.Bar fixes this.
        st.markdown("##### Domestic vs International Passengers")

        split_df = filtered_df.groupby('Year')[['Domestic Passengers', 'International Passengers']].sum().reset_index()

        # Compute % share per year in pandas first
        split_df['Total'] = split_df['Domestic Passengers'] + split_df['International Passengers']
        split_df['Dom_pct']   = (split_df['Domestic Passengers']      / split_df['Total'] * 100).round(1)
        split_df['Intl_pct']  = (split_df['International Passengers'] / split_df['Total'] * 100).round(1)

        # Year labels as strings so Plotly treats them as categories, not numbers
        year_labels = split_df['Year'].astype(str).tolist()

        fig2 = go.Figure()

        # Trace 1: Domestic (small, left segment — grey)
        fig2.add_trace(go.Bar(
            y=year_labels,
            x=split_df['Dom_pct'],
            name='Domestic',
            orientation='h',
            marker_color='#BFCAD5',
            text=["<b>" + str(val) + "%</b>" for val in split_df['Dom_pct']],
            textposition='inside',
            insidetextanchor='middle',
            textangle=0                # Force horizontal text — never rotate
        ))

        # Trace 2: International (large, right segment — navy blue)
        fig2.add_trace(go.Bar(
            y=year_labels,
            x=split_df['Intl_pct'],
            name='International',
            orientation='h',
            marker_color='#1A4F8A',
            text=["<b>" + str(val) + "%</b>" for val in split_df['Intl_pct']],
            textposition='inside',
            insidetextanchor='middle'
        ))

        fig2.update_traces(marker_cornerradius=10, textfont=dict(size=15)) # Larger font and pill edges
        fig2.update_layout(
            barmode='stack',
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False, range=[0, 100]),
            yaxis=dict(title=None, type='category'),
            margin=dict(l=0, r=0, t=10, b=40),
            bargap=0.5,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None),
            uniformtext=dict(minsize=8, mode='hide')  # Hide labels that can't fit horizontally
        )
        st.plotly_chart(fig2, width='stretch')

    with col2:
        # CHART 3: Recovery Leaderboard (Horizontal Bar)
        st.markdown(f"##### Growth Leaderboard (%) ({min_year} to {max_year})")
        if min_year != max_year:
            growth_data = []
            for airport in selected_airports:
                start_val = df[(df['Year'] == min_year) & (df['Airport'] == airport)]['Total Passengers'].sum()
                end_val = df[(df['Year'] == max_year) & (df['Airport'] == airport)]['Total Passengers'].sum()
                growth = ((end_val - start_val) / start_val) * 100 if start_val > 0 else 0
                growth_data.append({'Airport': airport, 'Growth (%)': growth})
                
            growth_df = pd.DataFrame(growth_data).sort_values('Growth (%)', ascending=True)
            
            # Build the chart manually with go.Bar to avoid px.bar's grouped-mode alignment bug
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=growth_df['Growth (%)'],
                y=growth_df['Airport'],
                orientation='h',
                marker_color=[airport_colors.get(a, '#1A4F8A') for a in growth_df['Airport']],
                marker_cornerradius=10, # Add beautiful modern rounded corners to the bars
                text=[f"<b>{val:.1f}%</b>" for val in growth_df['Growth (%)']],
                textposition='inside',
                textfont=dict(size=15),
                insidetextanchor='end',
                showlegend=False
            ))
            
            fig3.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False, title=None),
                margin=dict(l=0, r=0, t=10, b=0),
                bargap=0.4
            )
            st.plotly_chart(fig3, width='stretch')
        else:
            st.info(f"Select multiple years in the sidebar to calculate growth leaderboard.")