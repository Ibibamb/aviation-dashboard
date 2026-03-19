import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# 1. Page Configuration (Enforcing the 16:9 minimalist layout)
st.set_page_config(page_title="UK Aviation Recovery", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS FOR MINIMALISM ---
# This hides standard Streamlit borders and makes the KPI cards look like your design
st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #FFFFFF;
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
    db_path = r"C:\Users\Kamiye\Desktop\aviation-dashboard\aviation_dashboard.db"
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM passenger_trends", conn)
    conn.close()
    
    # Ensure correct data types
    df['Year'] = df['Year'].astype(int)
    # Handle month names (e.g. "January") OR numeric months stored as strings
    if df['Month'].dtype == object:
        try:
            # Try parsing full month names like "January", "February" etc.
            df['Month'] = pd.to_datetime(df['Month'], format='%B').dt.month
        except ValueError:
            # Fallback: try abbreviated names like "Jan", "Feb" etc.
            df['Month'] = pd.to_datetime(df['Month'], format='%b').dt.month
    else:
        df['Month'] = df['Month'].astype(int)
    return df

df = load_data()

# 3. The Control Center (Sidebar)
st.sidebar.title("UK Aviation Recovery")
st.sidebar.markdown("*(DSR Evaluation Dashboard)*")
st.sidebar.markdown("---")

# Year Filter
available_years = sorted(df['Year'].unique())
selected_years = st.sidebar.multiselect(
    "Timeline (Select Years)", 
    options=available_years, 
    default=available_years
)

# Airport Filter (Enforcing the Project Constraint!)
available_airports = sorted(df['Airport'].unique())
selected_airports = st.sidebar.multiselect(
    "Compare Airports (Max 3)",
    options=available_airports,
    default=["HEATHROW", "GATWICK"],
    max_selections=3  # Streamlit automatically prevents selecting a 4th!
)

# 4. Apply Filters to Data
filtered_df = df[(df['Year'].isin(selected_years)) & (df['Airport'].isin(selected_airports))]

# 5. The KPI Ribbon (Top Row)
st.markdown("### System Overview")

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
        st.metric(label="Total Passengers", value=f"{total_pax / 1000000:.1f}M")
    with kpi2:
        st.metric(label=trend_label, value=f"{yoy_growth:+.1f}%" if min_year != max_year else "-")
    with kpi3:
        st.metric(label="Volatility Score (CV)", value=f"{cv_score:.3f}", delta="Stable" if cv_score < 0.8 else "Volatile", delta_color="inverse")

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
        markers=True,
        title="Post-Pandemic Recovery Arc"
    )
    
    # Minimalist Plotly Styling
    fig1.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_showgrid=False,
        yaxis_showgrid=True,
        yaxis_gridcolor='#E6E9EF',
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig1, use_container_width=True)
    
    st.markdown("<br>", unsafe_allow_html=True) # Whitespace spacer
    
    # --- THE MICRO VIEW (Bottom Row) ---
    col1, col2 = st.columns(2)
    
    with col1:
        # CHART 2: Market Structure — Horizontal 100% Stacked Bar
        # Using go.Figure with explicit traces: one per segment.
        # px.bar with melted data renders separate rows per year — go.Bar fixes this.
        st.markdown("##### Market Structure (Dom vs Intl)")

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
            text=split_df['Dom_pct'].astype(str) + '%',
            textposition='inside',
            insidetextanchor='middle'
        ))

        # Trace 2: International (large, right segment — navy blue)
        fig2.add_trace(go.Bar(
            y=year_labels,
            x=split_df['Intl_pct'],
            name='International',
            orientation='h',
            marker_color='#1A4F8A',
            text=split_df['Intl_pct'].astype(str) + '%',
            textposition='inside',
            insidetextanchor='middle'
        ))

        fig2.update_layout(
            barmode='stack',
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False, range=[0, 100]),
            yaxis=dict(title=None, type='category'),
            margin=dict(l=0, r=0, t=10, b=40),
            bargap=0.5,
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="left", x=0, title=None)
        )
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        # CHART 3: Recovery Leaderboard (Horizontal Bar)
        st.markdown("##### Growth Leaderboard")
        if min_year != max_year:
            growth_data = []
            for airport in selected_airports:
                start_val = df[(df['Year'] == min_year) & (df['Airport'] == airport)]['Total Passengers'].sum()
                end_val = df[(df['Year'] == max_year) & (df['Airport'] == airport)]['Total Passengers'].sum()
                growth = ((end_val - start_val) / start_val) * 100 if start_val > 0 else 0
                growth_data.append({'Airport': airport, 'Growth (%)': growth})
                
            growth_df = pd.DataFrame(growth_data).sort_values('Growth (%)', ascending=True)
            
            fig3 = px.bar(
                growth_df, 
                x='Growth (%)', 
                y='Airport', 
                orientation='h',
                text_auto='.1f', # Shows the percentage on the bar
                color_discrete_sequence=['#2ca02c'] # Green for growth
            )
            
            fig3.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis_showgrid=False,
                yaxis_showgrid=False,
                margin=dict(l=0, r=0, t=10, b=0)
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info(f"Select multiple years in the sidebar to calculate growth leaderboard.")