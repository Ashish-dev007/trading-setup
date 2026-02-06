import streamlit as st
import pandas as pd
import numpy as np
import io
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

# --- PAGE CONFIG ---
st.set_page_config(page_title="Institutional ZQ/SR1 Terminal", layout="wide")

# --- CUSTOM CSS FOR CLEAN LOOK ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; }
    </style>
    """, unsafe_allow_html=True)

# --- CALENDAR SETUP ---
holidays = USFederalHolidayCalendar()
usb = CustomBusinessDay(calendar=holidays)
all_days = pd.date_range(start="2026-01-01", end="2027-12-31", freq='D')
biz_days_set = set(pd.date_range(start="2026-01-01", end="2027-12-31", freq=usb))

fomc_dates = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16", "2027-07-28", "2027-09-22", "2027-11-03", "2027-12-15"
]
month_options = pd.date_range("2026-01-01", periods=24, freq='MS').strftime('%b-%y').tolist()

# --- SIDEBAR: CONTROLS ---
st.sidebar.header("🏦 Market Baseline")
effr_spot = st.sidebar.number_input('Spot EFFR %', value=3.7500, format="%.4f", step=0.0001)
sofr_spot = st.sidebar.number_input('Spot SOFR %', value=3.7300, format="%.4f", step=0.0001)
lot_size = st.sidebar.number_input('Position (Lots)', value=100, step=10)
trade_side = st.sidebar.selectbox("Trade Direction", ['Long (Buy)', 'Short (Sell)'])

st.sidebar.header("⏳ Liquidity Turn (bps)")
y_prem = st.sidebar.number_input('Year-End Turn', value=15.0)
q_prem = st.sidebar.number_input('Quarter-End Turn', value=5.0)
m_prem = st.sidebar.number_input('Month-End Turn', value=2.0)

# --- MAIN INTERFACE ---
st.title("🏛️ Institutional ZQ & SR1 Terminal v11.0")
st.markdown("---")

c1, c2, c3 = st.columns(3)
with c1:
    dashboard_mode = st.selectbox("Dashboard Mode", ['Outright Analysis', 'Spread Analysis'])
with c2:
    contract_type = st.selectbox("Instrument", ['ZQ (Fed Funds)', 'SR1 (SOFR)'])
with c3:
    target_month = st.selectbox("Target Analysis Month", month_options)

st.header("📅 FOMC Meeting Risk Adjustments")
st.caption("Enter manual Bps move (Hike (+) / Cut (-)) and the Probability percentage.")

# Create a grid for manual meeting inputs
fomc_input_data = {}
cols = st.columns(4)
for i, date in enumerate(fomc_dates):
    with cols[i % 4]:
        st.subheader(f"📅 {date}")
        bps = st.number_input("Bps Move", value=0.0, step=1.0, key=f"bps_{date}")
        prob = st.number_input("Prob (%)", value=0.0, step=1.0, key=f"prob_{date}", min_value=0.0, max_value=100.0)
        fomc_input_data[date] = {"bps": bps, "prob": prob}

st.markdown("---")

# --- CALCULATION ENGINE ---
def calculate_path(base, mp, qp, yp):
    s = pd.Series(base, index=all_days)
    curr = base
    for d in sorted(fomc_dates):
        nxt = pd.Timestamp(d) + usb
        # Effective Move Calculation
        move = (fomc_input_data[d]['bps'] / 100) * (fomc_input_data[d]['prob'] / 100)
        curr += move
        s.loc[nxt:] = curr
    
    # Apply Turn Premiums
    for (yr, mt), grp in s.groupby([s.index.year, s.index.month]):
        bz = [d for d in grp.index if d in biz_days_set]
        if bz:
            lwd = max(bz)
            p = yp if lwd.month == 12 else (qp if lwd.month in [3,6,9] else mp)
            s.loc[lwd] += (p/100)
    return s

if st.button("🚀 RUN SCENARIO & GENERATE REPORT", use_container_width=True):
    effr_path = calculate_path(effr_spot, m_prem, q_prem, y_prem)
    sofr_path = calculate_path(sofr_spot, m_prem, q_prem, y_prem)
    
    # Generate Master DataFrame
    master_df = pd.DataFrame(index=month_options)
    master_df['EFFR_Avg'] = effr_path.groupby([effr_path.index.year, effr_path.index.month]).mean().values
    master_df['SOFR_Avg'] = sofr_path.groupby([sofr_path.index.year, sofr_path.index.month]).mean().values
    master_df['ZQ_Outright'] = (100 - master_df['EFFR_Avg']).round(4)
    master_df['SR1_Outright'] = (100 - master_df['SOFR_Avg']).round(4)
    
    # Add Spread Columns ($Month_n - Month_{n+1}$)
    master_df['ZQ_1M_Spread'] = (master_df['ZQ_Outright'] - master_df['ZQ_Outright'].shift(-1)).round(4)
    master_df['SR1_1M_Spread'] = (master_df['SR1_Outright'] - master_df['SR1_Outright'].shift(-1)).round(4)
    
    # Selection Logic
    target_col = 'ZQ_Outright' if 'ZQ' in contract_type else 'SR1_Outright'
    spread_col = 'ZQ_1M_Spread' if 'ZQ' in contract_type else 'SR1_1M_Spread'
    side_mult = 1 if 'Long' in trade_side else -1
    
    st.header("📈 Scenario Results")
    res1, res2 = st.columns(2)
    
    if dashboard_mode == 'Outright Analysis':
        outright_px = master_df.loc[target_month, target_col]
        spot_px = 100 - (effr_spot if 'ZQ' in contract_type else sofr_spot)
        pnl = (outright_px - spot_px) * 100 * lot_size * 41.67 * side_mult
        
        res1.metric(f"{target_month} Price", f"{outright_px:.4f}")
        res2.metric("Scenario P&L", f"${pnl:,.2f}", delta=f"{(outright_px - spot_px)*side_mult:.4f} Price Delta")
    else:
        m_idx = month_options.index(target_month)
        if m_idx < 23:
            sprd_val = master_df.loc[target_month, spread_col]
            pnl = (sprd_val * 100 * lot_size * 41.67) * side_mult
            res1.metric(f"{target_month} / {month_options[m1_idx+1]} Spread", f"{sprd_val*100:+.2f} bps")
            res2.metric("Spread P&L", f"${pnl:,.2f}")
        else:
            st.warning("Cannot calculate 1-month spread for the last available month.")

    # Show Master Table
    st.subheader("Master Summary Table (All Months)")
    st.dataframe(master_df.style.format("{:.4f}"), use_container_width=True)

    # --- EXCEL EXPORT (Multi-Sheet) ---
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        master_df.to_excel(writer, sheet_name='Master_Data_Summary')
        # Simple summary sheet
        pd.DataFrame({"Metric": ["Mode", "Instrument", "Direction", "Target"], 
                      "Value": [dashboard_mode, contract_type, trade_side, target_month]}).to_excel(writer, sheet_name='Scenario_Meta', index=False)
    
    st.download_button(
        label="📩 Download Multi-Sheet Excel Report",
        data=buffer.getvalue(),
        file_name=f"Fed_Report_{target_month}.xlsx",
        mime="application/vnd.ms-excel"
    )
