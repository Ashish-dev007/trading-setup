import streamlit as st
import pandas as pd
import numpy as np
import io
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

# Page Config
st.set_page_config(page_title="Institutional ZQ/SR1 Terminal", layout="wide")

# --- ENGINE ---
holidays = USFederalHolidayCalendar()
usb = CustomBusinessDay(calendar=holidays)
all_days = pd.date_range(start="2026-01-01", end="2027-12-31", freq='D')
biz_days_set = set(pd.date_range(start="2026-01-01", end="2027-12-31", freq=usb))

fomc_dates = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16", "2027-07-28", "2027-09-22", "2027-11-03", "2027-12-15"
]
month_options = pd.date_range("2026-01-01", periods=24, freq='MS').strftime('%b-%y').tolist()

# --- SIDEBAR: SETTINGS ---
st.sidebar.header("📊 Market Baseline")
effr_spot = st.sidebar.number_input('Spot EFFR %', value=3.7500, format="%.4f")
sofr_spot = st.sidebar.number_input('Spot SOFR %', value=3.7300, format="%.4f")
lot_size = st.sidebar.number_input('Position (Lots)', value=100)

st.sidebar.header("⏳ Turn Premiums (bps)")
y_prem = st.sidebar.number_input('Year-End', value=15.0)
q_prem = st.sidebar.number_input('Quarter-End', value=5.0)
m_prem = st.sidebar.number_input('Month-End', value=2.0)

# --- MAIN UI ---
st.title("🏛️ Institutional ZQ & SR1 Trading Terminal")
col1, col2, col3 = st.columns(3)
with col1:
    mode = st.selectbox("Dashboard Mode", ['Outright Analysis', 'Spread Analysis'])
with col2:
    side = st.selectbox("Direction", ['Long (Buy)', 'Short (Sell)'])
with col3:
    contract = st.selectbox("Instrument", ['ZQ (Fed Funds)', 'SR1 (SOFR)'])

target_month = st.selectbox("Target Month", month_options)

st.header("📅 FOMC Meeting Expectations")
st.info("Enter manual Bps and Probability for each meeting.")

fomc_data = {}
cols = st.columns(4)
for i, date in enumerate(fomc_dates):
    with cols[i % 4]:
        st.write(f"**{date}**")
        b = st.number_input("Bps", value=0.0, key=f"bps_{date}")
        p = st.number_input("Prob %", value=0.0, key=f"p_{date}")
        fomc_data[date] = (b, p)

# --- CALCULATION ---
if st.button("RUN SCENARIO & GENERATE REPORT"):
    def get_path(base):
        s = pd.Series(base, index=all_days)
        curr = base
        for d in sorted(fomc_dates):
            nxt = pd.Timestamp(d) + usb
            move = (fomc_data[d][0] / 100) * (fomc_data[d][1] / 100)
            curr += move
            s.loc[nxt:] = curr
        for (yr, mt), grp in s.groupby([s.index.year, s.index.month]):
            bz = [d for d in grp.index if d in biz_days_set]
            if bz:
                lwd = max(bz)
                prem = y_prem if lwd.month == 12 else (q_prem if lwd.month in [3,6,9] else m_prem)
                s.loc[lwd] += (prem/100)
        return s

    effr_path = get_path(effr_spot)
    sofr_path = get_path(sofr_spot)

    master_df = pd.DataFrame(index=month_options)
    master_df['EFFR_Avg'] = effr_path.groupby([effr_path.index.year, effr_path.index.month]).mean().values
    master_df['SOFR_Avg'] = sofr_path.groupby([sofr_path.index.year, sofr_path.index.month]).mean().values
    master_df['ZQ_Outright'] = (100 - master_df['EFFR_Avg']).round(4)
    master_df['SR1_Outright'] = (100 - master_df['SOFR_Avg']).round(4)
    master_df['ZQ_1M_Spread'] = (master_df['ZQ_Outright'] - master_df['ZQ_Outright'].shift(-1)).round(4)
    master_df['SR1_1M_Spread'] = (master_df['SR1_Outright'] - master_df['SR1_Outright'].shift(-1)).round(4)

    # Execution Report
    t_col = 'ZQ_Outright' if 'ZQ' in contract else 'SR1_Outright'
    s_col = 'ZQ_1M_Spread' if 'ZQ' in contract else 'SR1_1M_Spread'
    mult = 1 if 'Long' in side else -1

    st.divider()
    if mode == 'Outright Analysis':
        px = master_df.loc[target_month, t_col]
        st.metric(f"{target_month} Outright Price", f"{px:.4f}")
    else:
        m_idx = month_options.index(target_month)
        m2 = month_options[m_idx+1] if m_idx < 23 else "N/A"
        sprd = master_df.loc[target_month, s_col]
        st.metric(f"{target_month}/{m2} Spread (bps)", f"{sprd*100:+.2f} bps")

    st.dataframe(master_df.style.format("{:.4f}"))

    # Excel Download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        master_df.to_excel(writer, sheet_name='Master_Summary')
    st.download_button("📩 Download Excel Report", output.getvalue(), "Trader_Report.xlsx")
