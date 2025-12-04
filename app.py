import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

def check_password():
    """
    检查密码是否正确。
    如果正确，返回 True；如果不正确，显示输入框并停止运行后续代码。
    """
    # 1. 如果已经验证成功，直接返回 True
    if st.session_state.get("password_correct", False):
        return True

    # 2. 定义密码验证的回调函数
    def password_entered():
        # 检查输入密码是否匹配 Secrets 中的配置
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            # 为了安全，验证后删除 session 中的明文密码
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    # 3. 显示密码输入框
    st.title("🔒 请输入密码访问")
    st.text_input(
        "Password", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    # 4. 如果密码错误，提示错误
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 密码错误，请重试。")

    # 5. 返回 False，表示未通过验证
    return False

# --- 执行检查 ---
if not check_password():
    st.stop()  # 🛑 核心步骤：如果没通过，直接停止运行下面的所有代码

# -----------------------------------------------------------------------------
# 1. Supabase Connection Setup
# -----------------------------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# -----------------------------------------------------------------------------
# 2. Data Fetching Functions
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600) 
def fetch_data(table_name): 
    """Fetches all data from a Supabase table."""
    response = supabase.table(table_name).select("*").execute()
    data = response.data
    if data:
        return pd.DataFrame(data)
    return pd.DataFrame()


# -----------------------------------------------------------------------------
# HELPER FUNCTION: Calculate Aggregated Metrics for a Single Phase
# -----------------------------------------------------------------------------
def calculate_phase_metrics(phase_id, df):
    """Calculates aggregated GSC metrics (Clicks, Imp, CTR, Pos) for a single phase."""
    df_phase = df[df['Phase_id'] == phase_id]
    total_clicks = df_phase['Clicks'].sum()
    total_impressions = df_phase['Impressions'].sum()
    avg_position = df_phase['Position'].mean()
    avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    
    return {
        'Phase_id': phase_id,
        'Clicks': total_clicks,
        'Impressions': total_impressions,
        'Position': avg_position,
        'CTR': avg_ctr
    }

# -----------------------------------------------------------------------------
# 3. Streamlit App Layout
# -----------------------------------------------------------------------------
st.set_page_config(page_title="SEO Phase Comparison Dashboard", layout="wide")

st.title("SEO Performance Dashboard")
st.markdown("Analysis is based on **Phase** segmentation.")

# Load Data
with st.spinner('Fetching data from Supabase...'):
    df_gsc = fetch_data("GSC")
    df_queries = fetch_data("Top_Queries")
    df_domains = fetch_data("Domains") 

# Initial Data Check
if df_gsc.empty:
    st.error("❌ No GSC data found. Please use the Uploader script to add data.")
    st.stop()
if df_queries.empty:
    st.error("❌ No Query data found. Please use the Uploader script to add data.")
    st.stop()


# -----------------------------------------------------------------------------
# SIDEBAR CONFIGURATION (Domain ID to Name Mapping)
# -----------------------------------------------------------------------------
st.sidebar.header("Configuration")

# 1. Create mapping: {id: name}
if not df_domains.empty and 'id' in df_domains.columns and 'domain_name' in df_domains.columns:
    domain_map = dict(zip(df_domains['id'], df_domains['domain_name']))
else:
    domain_map = {}

# 2. Get unique Domain IDs that actually have GSC data
available_domain_ids = sorted(df_gsc['Domain_id'].unique())
if not available_domain_ids:
    st.error("No domain data available in GSC table.")
    st.stop()

# 3. Create friendly labels for the dropdown
domain_options = {
    did: domain_map.get(did, f"ID: {did}") 
    for did in available_domain_ids
}

# 4. Selectbox shows Names, but the returned value is the ID (key)
selected_domain_id = st.sidebar.selectbox(
    "Select Domain", 
    options=available_domain_ids, 
    format_func=lambda x: domain_options[x] 
)

# Filter Data using the selected ID
domain_gsc = df_gsc[df_gsc['Domain_id'] == selected_domain_id]
df_queries_all = df_queries[df_queries['Domain_id'] == selected_domain_id]

unique_phases = sorted(domain_gsc['Phase_id'].unique())
if not unique_phases:
    st.error("No phases found for the selected domain.")
    st.stop()


# -----------------------------------------------------------------------------
# 5. Tab Layout (All Performance and Comparison)
# -----------------------------------------------------------------------------
tab_all, tab_comparison, tab_tiers, tab_strategy = st.tabs([
    "📈 All Performance", 
    "⚔️ Phase Comparison",
    "🏆 Position Tier Analysis",
    "🕵️ Strategy Validation" # <--- NEW TAB
])

# =============================================================================
# TAB 1: ALL PERFORMANCE
# =============================================================================
with tab_all:
    st.header(f"📈 All Phase Performance Overview for {domain_options.get(selected_domain_id, 'Selected Domain')}")

    # Calculate metrics for ALL phases
    all_phases_metrics = [calculate_phase_metrics(pid, domain_gsc) for pid in unique_phases]
    df_all_phases = pd.DataFrame(all_phases_metrics)
    
    if df_all_phases.empty:
        st.warning("No performance data found to plot.")
    else:
        df_all_phases['Phase_id'] = df_all_phases['Phase_id'].astype(str)
        
        # 1. Clicks and Impressions Subplots
        fig_volume = make_subplots(rows=1, cols=2, subplot_titles=("Total Clicks Across Phases", "Total Impressions Across Phases"))
        
        fig_volume.add_trace(go.Bar(x=df_all_phases['Phase_id'], y=df_all_phases['Clicks'], name='Clicks', marker_color='skyblue'), row=1, col=1)
        fig_volume.add_trace(go.Bar(x=df_all_phases['Phase_id'], y=df_all_phases['Impressions'], name='Impressions', marker_color='orange'), row=1, col=2)
        
        fig_volume.update_layout(height=450, showlegend=False, title_text="Volume Trends: Clicks and Impressions")
        st.plotly_chart(fig_volume, use_container_width=True)
        
        # 2. CTR and Position Subplots
        fig_quality = make_subplots(rows=1, cols=2, subplot_titles=("Average CTR Across Phases", "Average Position Across Phases"))
        
        fig_quality.add_trace(go.Scatter(x=df_all_phases['Phase_id'], y=df_all_phases['CTR'], name='CTR', mode='lines+markers', line=dict(color='green', width=3)), row=1, col=1)
        fig_quality.add_trace(go.Scatter(x=df_all_phases['Phase_id'], y=df_all_phases['Position'], name='Position', mode='lines+markers', line=dict(color='red', width=3)), row=1, col=2)
        
        fig_quality.update_yaxes(autorange="reversed", title_text="Average Position (Lower is Better)", row=1, col=2)
        fig_quality.update_layout(height=450, showlegend=False, title_text="Quality Trends: CTR and Position")
        st.plotly_chart(fig_quality, use_container_width=True)
        
        st.subheader("Data Summary (All Phases)")
        st.dataframe(df_all_phases.style.format({
            "Clicks": "{:,.0f}", "Impressions": "{:,.0f}",
            "Position": "{:.1f}", "CTR": "{:.2f}%"
        }), use_container_width=True)


# =============================================================================
# TAB 2: PHASE COMPARISON
# =============================================================================
with tab_comparison:
    st.header("⚔️ Phase-over-Phase Comparison")
    st.markdown("Compare key metrics between two distinct optimization phases.")

    col_a, col_b = st.columns(2)

    with col_a:
        phase_a = st.selectbox("Select Phase A (Baseline)", unique_phases, index=0, key='phase_a_select')
    with col_b:
        default_index_b = len(unique_phases) - 1 if len(unique_phases) > 1 else 0
        phase_b = st.selectbox("Select Phase B (Comparison)", unique_phases, index=default_index_b, key='phase_b_select')

    # Calculate metrics for both phases
    metrics_a = calculate_phase_metrics(phase_a, domain_gsc)
    metrics_b = calculate_phase_metrics(phase_b, domain_gsc)

    # Convert to DataFrames for easy merging/display
    df_metrics = pd.DataFrame([metrics_a, metrics_b]).set_index('Phase_id')

    # --- Metric Comparison ---
    st.subheader("GSC Core Metric Change: Phase B vs. Phase A")
    
    comp_cols = st.columns(4)
    metrics = ['Clicks', 'Impressions', 'CTR', 'Position']
    titles = ['Total Clicks', 'Total Impressions', 'Avg CTR', 'Avg Position']
    formats = ['{:.0f}', '{:.0f}', '{:.2f}%', '{:.1f}']
    
    for i, metric in enumerate(metrics):
        value_a = df_metrics.loc[phase_a, metric]
        value_b = df_metrics.loc[phase_b, metric]
        
        # Calculate Delta
        delta = value_b - value_a
        
        if metric == 'Position':
            if value_a == 0:
                delta_indicator = "N/A"
            else:
                delta_indicator = f"{delta:.1f}"
                if delta < 0:
                    delta_indicator += " (Better)"
                elif delta > 0:
                    delta_indicator += " (Worse)"
                else:
                    delta_indicator = "No Change"
        elif value_a != 0:
             delta_pct = (delta / value_a * 100)
             delta_indicator = f"{delta_pct:+.2f}%"
        else:
            delta_indicator = f"{delta:+,}"

        with comp_cols[i]:
            st.metric(label=titles[i], value=formats[i].format(value_b), delta=delta_indicator)

    st.divider()
    
    # --- Queries Control ---
    st.subheader("Query Mover Analysis")
    max_rows = st.slider(
        "Max Number of Top/Bottom Queries to Display", 
        min_value=5, 
        max_value=30, 
        value=10, 
        step=5
    )
    st.divider()
    
    # Helper to Aggregate
    def aggregate_queries(phase_id, df_q):
        df_phase = df_q[df_q['Phase_id'] == phase_id]
        return df_phase.groupby('Top_Queries').agg({
            'Clicks': 'sum',
            'Impressions': 'sum',
            'Position': 'mean'
        }).reset_index().rename(columns={
            'Clicks': f'Clicks_{phase_id}',
            'Impressions': f'Impressions_{phase_id}',
            'Position': f'Position_{phase_id}',
        })

    # Define MAX_RANK for calculation consistency (Treat 0 position as 100 for delta calculation)
    MAX_RANK = 100 
    
    # Merge Phase A and Phase B Query Data
    df_q_a = aggregate_queries(phase_a, df_queries_all)
    df_q_b = aggregate_queries(phase_b, df_queries_all)
    
    df_merged = pd.merge(
        df_q_a, 
        df_q_b, 
        on='Top_Queries', 
        how='outer'
    ).fillna(0)
    
    # Calculate all necessary deltas
    df_merged['Click_Delta'] = df_merged[f'Clicks_{phase_b}'] - df_merged[f'Clicks_{phase_a}']
    df_merged['Imp_Delta'] = df_merged[f'Impressions_{phase_b}'] - df_merged[f'Impressions_{phase_a}']
    
    df_merged[f'CTR_{phase_a}'] = (df_merged[f'Clicks_{phase_a}'] / df_merged[f'Impressions_{phase_a}'] * 100).fillna(0)
    df_merged[f'CTR_{phase_b}'] = (df_merged[f'Clicks_{phase_b}'] / df_merged[f'Impressions_{phase_b}'] * 100).fillna(0)
    df_merged['CTR_Delta'] = df_merged[f'CTR_{phase_b}'] - df_merged[f'CTR_{phase_a}']

    # --- REVISED POSITION DELTA LOGIC ---
    # 1. Create temporary calculation columns where 0 is replaced by MAX_RANK (100)
    pos_a_calc = df_merged[f'Position_{phase_a}'].replace(0, MAX_RANK)
    pos_b_calc = df_merged[f'Position_{phase_b}'].replace(0, MAX_RANK)
    
    # 2. Calculate Pos_Delta: Pos_B - Pos_A. Negative delta means improvement.
    df_merged['Pos_Delta'] = pos_b_calc - pos_a_calc

    # -------------------------------------------------------------
    # Analysis 1: Clicks & Impressions Movers (Uses st.table and max_rows)
    # -------------------------------------------------------------
    st.subheader("Query Volume Movers: Clicks & Impressions")

    col_click_movers, col_imp_movers = st.columns(2)

    top_gainers_click = df_merged.sort_values(by='Click_Delta', ascending=False).head(max_rows)
    top_losers_click = df_merged.sort_values(by='Click_Delta', ascending=True).head(max_rows)

    with col_click_movers:
        st.success(f"Top {max_rows} Click Gainers (Phase {phase_b} vs Phase {phase_a})")
        st.table(top_gainers_click[['Top_Queries', f'Clicks_{phase_a}', f'Clicks_{phase_b}', 'Click_Delta']].style.format({
            f'Clicks_{phase_a}': "{:,.0f}", f'Clicks_{phase_b}': "{:,.0f}", 'Click_Delta': "{:+,}"
        }))
        st.error(f"Top {max_rows} Click Losers (Phase {phase_b} vs Phase {phase_a})")
        st.table(top_losers_click[['Top_Queries', f'Clicks_{phase_a}', f'Clicks_{phase_b}', 'Click_Delta']].style.format({
            f'Clicks_{phase_a}': "{:,.0f}", f'Clicks_{phase_b}': "{:,.0f}", 'Click_Delta': "{:+,}"
        }))

    top_gainers_imp = df_merged.sort_values(by='Imp_Delta', ascending=False).head(max_rows)
    top_losers_imp = df_merged.sort_values(by='Imp_Delta', ascending=True).head(max_rows)

    with col_imp_movers:
        st.info(f"Top {max_rows} Impression Gainers (Phase {phase_b} vs Phase {phase_a})")
        st.table(top_gainers_imp[['Top_Queries', f'Impressions_{phase_a}', f'Impressions_{phase_b}', 'Imp_Delta']].style.format({
            f'Impressions_{phase_a}': "{:,.0f}", f'Impressions_{phase_b}': "{:,.0f}", 'Imp_Delta': "{:+,}"
        }))
        st.warning(f"Top {max_rows} Impression Losers (Phase {phase_b} vs Phase {phase_a})")
        st.table(top_losers_imp[['Top_Queries', f'Impressions_{phase_a}', f'Impressions_{phase_b}', 'Imp_Delta']].style.format({
            f'Impressions_{phase_a}': "{:,.0f}", f'Impressions_{phase_b}': "{:,.0f}", 'Imp_Delta': "{:+,}"
        }))

    st.divider()

# =============================================================================
# TAB 3: POSITION TIER ANALYSIS (ENHANCED + CLEAN EXPANDER REVISION)
# =============================================================================
with tab_tiers:
    # Tooltip Definitions for use inside the component
    TOOLTIP_S_IMPROVERS_EXP = "✅ **Tier S** 包含：**新排名**、**进入 Top 3 (S++)**，以及**大幅度提升 10+ 位 (S+)**。这是最高价值的进步。"
    TOOLTIP_A_IMPROVERS_EXP = "🔥 **Tier A (Top 10 Solid)**：最终排名前 10 (Pos ≤ 10) 且有 3+ 位实质性进步的查询。"
    TOOLTIP_B_IMPROVERS_EXP = "✨ **Tier B (General Jump)**：所有其他有排名进步 (Delta < 0) 但未达到更高 Tier 标准的查询。"
    TOOLTIP_S_DECLINERS_EXP = "🚨 **Decliner S (Crash/Lost)**：排名**大幅度下降 10+ 位 (Delta ≥ 10)** 或**排名完全丢失 (Pos_B = 0)**。请优先处理此项。"
    TOOLTIP_A_DECLINERS_EXP = "📉 **Decliner A (Top 10 Drop)**：从关键 Top 10 区域 (Pos_A ≤ 10) 掉出 3+ 位以上的查询。"
    TOOLTIP_B_DECLINERS_EXP = "⚠️ **Decliner B (Minor Drop)**：所有其他有排名后退 (Delta > 0) 但未达到更高 Decliner Tier 标准的查询。"


    st.header("🏆 Position Improvement & Drop Analysis (Enhanced Tiers)")
    st.markdown("Detailed breakdown of ranking changes, focusing on high-impact Top 3 and Top 10 movements.")
    
    # Define a constant for rank calculation (e.g., treating a lost rank as position 100)
    MAX_RANK = 100 

    col_t_a, col_t_b = st.columns(2)
    with col_t_a:
        tier_phase_a = st.selectbox("Select Phase A (Baseline)", unique_phases, index=0, key='tier_a')
    with col_t_b:
        default_index_b_tier = len(unique_phases) - 1 if len(unique_phases) > 1 else 0
        tier_phase_b = st.selectbox("Select Phase B (Comparison)", unique_phases, index=default_index_b_tier, key='tier_b')

    # Reuse aggregation logic (The function 'aggregate_queries' is defined in TAB 2)
    tier_df_a = aggregate_queries(tier_phase_a, df_queries_all)
    tier_df_b = aggregate_queries(tier_phase_b, df_queries_all)
    
    tier_merged = pd.merge(tier_df_a, tier_df_b, on='Top_Queries', how='outer').fillna(0)
    
    # -----------------------------------------------------------
    # DATA PREP & TIER CLASSIFICATION
    # -----------------------------------------------------------
    pos_a_calc = tier_merged[f'Position_{tier_phase_a}'].replace(0, MAX_RANK)
    pos_b_calc = tier_merged[f'Position_{tier_phase_b}'].replace(0, MAX_RANK)
    tier_merged['Pos_Delta'] = pos_b_calc - pos_a_calc
    
    tier_analysis_df = tier_merged[
        (tier_merged[f'Position_{tier_phase_a}'] > 0) | 
        (tier_merged[f'Position_{tier_phase_b}'] > 0)
    ].copy()
    
    pos_a_filtered_calc = tier_analysis_df[f'Position_{tier_phase_a}'].replace(0, MAX_RANK)
    pos_b_filtered_calc = tier_analysis_df[f'Position_{tier_phase_b}'].replace(0, MAX_RANK)
    tier_analysis_df['Pos_Delta'] = pos_b_filtered_calc - pos_a_filtered_calc


    def categorize_tier_enhanced(row):
        pos_a = row[f'Position_{tier_phase_a}']
        pos_b = row[f'Position_{tier_phase_b}']
        delta = row['Pos_Delta'] 
        
        if pos_a == 0 and pos_b > 0: 
            return 'Tier S (New Rank)'
            
        if pos_b > 0 and pos_b <= 3 and pos_a > 3:
            return 'Tier S++ (Top 3 Win)'
            
        if delta <= -10: 
            return 'Tier S+ (Jump 10+)'
            
        if pos_b > 0 and pos_b <= 10 and delta <= -3:
            return 'Tier A (Top 10 Solid)'
            
        if delta < 0:
            return 'Tier B (General Jump)'
            
        if delta >= 10: 
            return 'Decliner S (Crash/Lost)'
            
        if pos_a <= 10 and delta >= 3:
            return 'Decliner A (Top 10 Drop)'
            
        if delta > 0:
            return 'Decliner B (General Drop)'
        
        return 'No Change'

    tier_analysis_df['Tier_Class'] = tier_analysis_df.apply(categorize_tier_enhanced, axis=1)

# -----------------------------------------------------------
    # SUMMARY METRICS (UI ENHANCED)
    # -----------------------------------------------------------
    st.markdown("### 📊 Tier Summary (Enhanced Analysis)")
    
    # 1. Calculate Totals & Aggregates
    total_keywords = len(tier_analysis_df)
    tier_counts = tier_analysis_df['Tier_Class'].value_counts()
    
    # Counts for Improvers
    count_tier_s_all = int(
        tier_counts.get('Tier S (New Rank)', 0) + 
        tier_counts.get('Tier S++ (Top 3 Win)', 0) + 
        tier_counts.get('Tier S+ (Jump 10+)', 0)
    )
    count_tier_a = int(tier_counts.get('Tier A (Top 10 Solid)', 0))
    count_tier_b = int(tier_counts.get('Tier B (General Jump)', 0))
    total_improvers = count_tier_s_all + count_tier_a + count_tier_b
    
    # Counts for Decliners
    count_crash = int(tier_counts.get('Decliner S (Crash/Lost)', 0))
    count_major_drop = int(tier_counts.get('Decliner A (Top 10 Drop)', 0))
    count_minor_drop = int(tier_counts.get('Decliner B (General Drop)', 0))
    total_decliners = count_crash + count_major_drop + count_minor_drop
    
    count_no_change = int(tier_counts.get('No Change', 0))

    # 2. Top Level Stats (Hero Section)
    hero_c1, hero_c2, hero_c3, hero_c4 = st.columns(4)
    
    with hero_c1:
        st.metric("📦 Total Keywords", f"{total_keywords}", help="Total unique queries analyzed between these two phases.")
    with hero_c2:
        win_rate = (total_improvers / total_keywords * 100) if total_keywords > 0 else 0
        st.metric("📈 Total Improvers", f"{total_improvers}", f"{win_rate:.1f}% Ratio")
    with hero_c3:
        loss_rate = (total_decliners / total_keywords * 100) if total_keywords > 0 else 0
        st.metric("📉 Total Decliners", f"{total_decliners}", f"-{loss_rate:.1f}% Ratio", delta_color="inverse")
    with hero_c4:
        st.metric("➖ No Change", f"{count_no_change}", help="Queries with rank delta = 0")

    st.divider()

    # 3. Visual Breakdown (Chart + Detailed Metrics)
    viz_col, metric_col = st.columns([1, 2])

    with viz_col:
        # Prepare Data for Pie Chart
        pie_labels = ['Elite/Major Wins (Tier S)', 'Solid Wins (Tier A)', 'General Wins (Tier B)', 'No Change', 'Minor Drops', 'Major Drops', 'Crashes']
        pie_values = [count_tier_s_all, count_tier_a, count_tier_b, count_no_change, count_minor_drop, count_major_drop, count_crash]
        pie_colors = ['#1f77b4', '#2ca02c', '#98df8a', '#d3d3d3', '#ff9896', '#d62728', '#8c000f'] # Blue, Green, LightGreen, Gray, LightRed, Red, DarkRed
        
        # Filter out zeros to clean up chart
        chart_data = {'Label': [], 'Value': [], 'Color': []}
        for l, v, c in zip(pie_labels, pie_values, pie_colors):
            if v > 0:
                chart_data['Label'].append(l)
                chart_data['Value'].append(v)
                chart_data['Color'].append(c)

        if chart_data['Value']:
            fig_tier = go.Figure(data=[go.Pie(
                labels=chart_data['Label'], 
                values=chart_data['Value'], 
                hole=.4,
                marker=dict(colors=chart_data['Color']),
                textinfo='label+percent',
                showlegend=False
            )])
            fig_tier.update_layout(
                title_text="Tier Distribution",
                margin=dict(t=30, b=0, l=0, r=0),
                height=300
            )
            st.plotly_chart(fig_tier, use_container_width=True)
        else:
            st.info("No data to visualize.")

    with metric_col:
        st.subheader("Detailed Breakdown")
        
        # Organize into two rows: Gains vs Losses
        m_row1_c1, m_row1_c2, m_row1_c3 = st.columns(3)
        with m_row1_c1:
            st.markdown("##### 🚀 Tier S (Elite)")
            st.markdown(f"<h2 style='margin:0; color:#1f77b4'>{count_tier_s_all}</h2>", unsafe_allow_html=True)
            st.caption("New / Top 3 / Jump 10+")
        with m_row1_c2:
            st.markdown("##### 🔥 Tier A (Solid)")
            st.markdown(f"<h2 style='margin:0; color:#2ca02c'>{count_tier_a}</h2>", unsafe_allow_html=True)
            st.caption("Top 10 Growth")
        with m_row1_c3:
            st.markdown("##### ✨ Tier B (General)")
            st.markdown(f"<h2 style='margin:0; color:#98df8a'>{count_tier_b}</h2>", unsafe_allow_html=True)
            st.caption("Minor Improvements")

        st.markdown("---") # Small separator

        m_row2_c1, m_row2_c2, m_row2_c3 = st.columns(3)
        with m_row2_c1:
            st.markdown("##### 🚨 Crash (Tier S)")
            st.markdown(f"<h2 style='margin:0; color:#8c000f'>{count_crash}</h2>", unsafe_allow_html=True)
            st.caption("Lost / Drop 10+")
        with m_row2_c2:
            st.markdown("##### 📉 Major Drop (Tier A)")
            st.markdown(f"<h2 style='margin:0; color:#d62728'>{count_major_drop}</h2>", unsafe_allow_html=True)
            st.caption("Top 10 Fall")
        with m_row2_c3:
            st.markdown("##### ⚠️ Minor Drop (Tier B)")
            st.markdown(f"<h2 style='margin:0; color:#ff9896'>{count_minor_drop}</h2>", unsafe_allow_html=True)
            st.caption("General Decline")
    
    st.divider()

    # -----------------------------------------------------------
    # EXPANDABLE TABLES (FIXED HTML RENDERING - Using internal description)
    # -----------------------------------------------------------
    common_cols_display = ['Top_Queries', f'Position_{tier_phase_a}', f'Position_{tier_phase_b}', 'Pos_Delta']
    col_format = {
        f'Position_{tier_phase_a}': "{:.1f}", 
        f'Position_{tier_phase_b}': "{:.1f}", 
        'Pos_Delta': "{:+.1f}",
    }
    
    # --- IMPROVERS ---
    st.subheader("✅ Improvers")
    
    # Tier S (Combine Elite, Major Jump, and New)
    s_tiers = ['Tier S (New Rank)', 'Tier S++ (Top 3 Win)', 'Tier S+ (Jump 10+)']
    df_s_combined = tier_analysis_df[tier_analysis_df['Tier_Class'].isin(s_tiers)].sort_values('Pos_Delta', ascending=True)
    
    # Expander with explicit title and internal description
    with st.expander(f"🚀 Tier S: Elite Movers (Count: {len(df_s_combined)})", expanded=False):
        st.markdown(TOOLTIP_S_IMPROVERS_EXP)
        if not df_s_combined.empty:
            st.table(df_s_combined[common_cols_display + ['Tier_Class']].head(50).style.format(col_format))
        else:
            st.info("No elite improvers found.")

    # Tier A
    df_a = tier_analysis_df[tier_analysis_df['Tier_Class'] == 'Tier A (Top 10 Solid)'].sort_values('Pos_Delta', ascending=True)
    with st.expander(f"🔥 Tier A: Top 10 Solid Improvers (Count: {len(df_a)})", expanded=False):
        st.markdown(TOOLTIP_A_IMPROVERS_EXP)
        if not df_a.empty:
            st.table(df_a[common_cols_display].head(50).style.format(col_format))
        else:
            st.info("No solid Top 10 improvers found.")

    # Tier B
    df_b = tier_analysis_df[tier_analysis_df['Tier_Class'] == 'Tier B (General Jump)'].sort_values('Pos_Delta', ascending=True)
    with st.expander(f"✨ Tier B: General Improvers (Count: {len(df_b)})", expanded=False):
        st.markdown(TOOLTIP_B_IMPROVERS_EXP)
        if not df_b.empty:
            st.table(df_b[common_cols_display].head(50).style.format(col_format))
        else:
            st.info("No general improvers found.")

    # --- DECLINERS ---
    st.subheader("🔻 Decliners")

    # Decliner S (Crash/Lost)
    df_d_s = tier_analysis_df[tier_analysis_df['Tier_Class'] == 'Decliner S (Crash/Lost)'].sort_values('Pos_Delta', ascending=False)
    with st.expander(f"🚨 Crash: Dropped 10+ Ranks or Lost (Count: {len(df_d_s)})", expanded=True): 
        st.markdown(TOOLTIP_S_DECLINERS_EXP)
        if not df_d_s.empty:
            st.table(df_d_s[common_cols_display].head(50).style.format(col_format))
        else:
            st.info("No crash decliners found.")

    # Decliner A (Top 10 Drop)
    df_d_a = tier_analysis_df[tier_analysis_df['Tier_Class'] == 'Decliner A (Top 10 Drop)'].sort_values('Pos_Delta', ascending=False)
    with st.expander(f"📉 Major Drop: Drop from Top 10 (Count: {len(df_d_a)})", expanded=False):
        st.markdown(TOOLTIP_A_DECLINERS_EXP)
        if not df_d_a.empty:
            st.table(df_d_a[common_cols_display].head(50).style.format(col_format))
        else:
            st.info("No major Top 10 drops found.")

    # Decliner B (General Drop)
    df_d_b = tier_analysis_df[tier_analysis_df['Tier_Class'] == 'Decliner B (General Drop)'].sort_values('Pos_Delta', ascending=False)
    with st.expander(f"⚠️ Minor Drop: General Decliners (Count: {len(df_d_b)})", expanded=False):
        st.markdown(TOOLTIP_B_DECLINERS_EXP)
        if not df_d_b.empty:
            st.table(df_d_b[common_cols_display].head(50).style.format(col_format))
        else:
            st.info("No general decliners found.")

# =============================================================================
# TAB 4: STRATEGY VALIDATION (ROI & RISK SCORECARD)
# =============================================================================
with tab_strategy:
    st.header("🕵️ Strategy Health Scorecard")
    st.markdown("通过 **成功率 (Percentage)** 宏观判断点击策略是否有效，而非纠结于单个关键词。")

    # 1. Select Phases
    col_s_a, col_s_b = st.columns(2)
    with col_s_a:
        st_phase_a = st.selectbox("Baseline Phase (Before/Start)", unique_phases, index=0, key='st_a')
    with col_s_b:
        default_index_st = len(unique_phases) - 1 if len(unique_phases) > 1 else 0
        st_phase_b = st.selectbox("Comparison Phase (Current/End)", unique_phases, index=default_index_st, key='st_b')

    # 2. Data Preparation
    MAX_RANK = 100
    
    # Aggregate Data (Independent to ensure clean calculation)
    st_df_a = df_queries_all[df_queries_all['Phase_id'] == st_phase_a].groupby('Top_Queries').agg({
        'Clicks': 'sum', 'Impressions': 'sum', 'Position': 'mean'
    }).reset_index()
    
    st_df_b = df_queries_all[df_queries_all['Phase_id'] == st_phase_b].groupby('Top_Queries').agg({
        'Clicks': 'sum', 'Impressions': 'sum', 'Position': 'mean'
    }).reset_index()

    st_merged = pd.merge(st_df_a, st_df_b, on='Top_Queries', how='outer', suffixes=('_A', '_B')).fillna(0)

    # Metrics Calculation
    st_merged['Pos_A_Calc'] = st_merged['Position_A'].replace(0, MAX_RANK)
    st_merged['Pos_B_Calc'] = st_merged['Position_B'].replace(0, MAX_RANK)
    st_merged['Pos_Delta'] = st_merged['Pos_B_Calc'] - st_merged['Pos_A_Calc'] # Negative is Good
    st_merged['Imp_Delta'] = st_merged['Impressions_B'] - st_merged['Impressions_A']
    
    st_merged['CTR_A'] = (st_merged['Clicks_A'] / st_merged['Impressions_A'] * 100).fillna(0)
    st_merged['CTR_B'] = (st_merged['Clicks_B'] / st_merged['Impressions_B'] * 100).fillna(0)
    st_merged['CTR_Delta'] = st_merged['CTR_B'] - st_merged['CTR_A']

    # Total Queries analyzed (exclude noise with 0 impressions in both phases if needed, but let's keep all for now)
    st_analysis_df = st_merged[(st_merged['Impressions_A'] > 0) | (st_merged['Impressions_B'] > 0)].copy()
    total_queries = len(st_analysis_df)

    if total_queries == 0:
        st.warning("No data available for analysis.")
        st.stop()

    # -----------------------------------------------------------
    # CALCULATE PERCENTAGES (The "Scorecard" Logic)
    # -----------------------------------------------------------
    
    # Criteria 1: True ROI (Rank Improved AND Impressions Grew)
    # Pos_Delta < 0 (Improved) AND Imp_Delta > 0 (Growth)
    true_wins_df = st_analysis_df[
        (st_analysis_df['Pos_Delta'] < 0) & 
        (st_analysis_df['Imp_Delta'] > 0)
    ]
    count_wins = len(true_wins_df)
    pct_wins = (count_wins / total_queries) * 100

    # Criteria 2: Risk (CTR Boosted > 3% BUT Rank Dropped)
    # CTR_Delta > 3 (High Boost) AND Pos_Delta > 0 (Dropped)
    risky_df = st_analysis_df[
        (st_analysis_df['CTR_Delta'] > 3) & 
        (st_analysis_df['Pos_Delta'] > 0)
    ]
    count_risk = len(risky_df)
    pct_risk = (count_risk / total_queries) * 100

    # Criteria 3: Ineffective (CTR Boosted > 3% BUT Rank No Change or Minimal Drop)
    # CTR_Delta > 3 AND Pos_Delta == 0 (Stagnant)
    ineffective_df = st_analysis_df[
        (st_analysis_df['CTR_Delta'] > 3) & 
        (st_analysis_df['Pos_Delta'] == 0)
    ]
    count_ineffective = len(ineffective_df)
    pct_ineffective = (count_ineffective / total_queries) * 100

    # -----------------------------------------------------------
    # DISPLAY SCORECARD
    # -----------------------------------------------------------
    st.subheader("📊 策略健康度 (Strategy Health)")
    
    sc1, sc2, sc3 = st.columns(3)
    
    with sc1:
        st.metric(
            label="✅ 真实有效率 (True Win Rate)",
            value=f"{pct_wins:.1f}%",
            delta=f"{count_wins}/{total_queries} 词",
            help="排名提升 (Pos Up) 且 真实曝光增长 (Imp Up) 的关键词占比。越高越好，说明点击带来了真实流量。"
        )
    
    with sc2:
        st.metric(
            label="⚠️ 风险/翻车率 (Risk Rate)",
            value=f"{pct_risk:.1f}%",
            delta=f"{count_risk}/{total_queries} 词",
            delta_color="inverse", # Red if positive (bad)
            help="CTR 提升超过 3% 但排名反而下跌的关键词占比。如果此值过高 (>10%)，请立即暂停策略。"
        )
        
    with sc3:
        st.metric(
            label="💨 无效消耗率 (Wasted Rate)",
            value=f"{pct_ineffective:.1f}%",
            delta=f"{count_ineffective}/{total_queries} 词",
            delta_color="off",
            help="CTR 提升超过 3% 但排名纹丝不动的关键词。说明由于竞争或算法过滤，投入未产生效果。"
        )

    st.progress(pct_wins / 100)
    st.caption(f"当前策略有效性进度条: {pct_wins:.1f}% 的词产生了正向收益")

    # =========================================================================
    # NEW: 深度与强度分析 (解决 "赢小输大" 的担忧)
    # =========================================================================
    st.markdown("#### ⚖️ 强度与深度分析 (Magnitude Check)")
    st.info("此区域用于验证：**上涨是否只是微涨，下跌是否是暴跌？**")

    # 1. 计算平均幅度
    # 赢家：取绝对值计算平均提升了多少位
    avg_win_depth = abs(true_wins_df['Pos_Delta'].mean()) if not true_wins_df.empty else 0
    # 输家(风险词)：计算平均下降了多少位
    avg_loss_depth = risky_df['Pos_Delta'].mean() if not risky_df.empty else 0

    # 2. 计算总排名盈亏 (Total Rank P&L)
    # 总共提升了多少个名次 vs 总共丢失了多少个名次
    total_ranks_gained = abs(true_wins_df['Pos_Delta'].sum()) if not true_wins_df.empty else 0
    total_ranks_lost = risky_df['Pos_Delta'].sum() if not risky_df.empty else 0
    net_rank_change = total_ranks_gained - total_ranks_lost # 因为lost是正数(rank变大)，所以这里相减代表盈亏

    # 3. 展示 Metrics
    mag_col1, mag_col2, mag_col3 = st.columns(3)

    with mag_col1:
        st.metric(
            label="平均提升幅度 (Avg Up)",
            value=f"{avg_win_depth:.1f} 位",
            help="平均每个“真实增长词”提升了多少个名次。"
        )

    with mag_col2:
        is_crash = avg_loss_depth > (avg_win_depth * 1.5) # 如果跌幅是涨幅的1.5倍，标红
        st.metric(
            label="平均下跌幅度 (Avg Down)",
            value=f"{avg_loss_depth:.1f} 位",
            delta="⚠️ 跌幅过深" if is_crash else "幅度可控",
            delta_color="inverse" if is_crash else "normal",
            help="平均每个“风险词”下降了多少个名次。"
        )

    with mag_col3:
        # 净排名盈亏
        rank_delta_label = "🟢 净赚名次" if total_ranks_gained > total_ranks_lost else "🔴 净亏名次"
        st.metric(
            label="全盘名次盈亏 (Net Rank P&L)",
            value=f"{int(total_ranks_gained - total_ranks_lost)} 位",
            delta=f"赚 {int(total_ranks_gained)} vs 亏 {int(total_ranks_lost)}",
            help="赢家提升的总名次减去输家跌掉的总名次。如果为负，说明虽然赢的词多，但跌掉的名次更多。"
        )

    # 4. 智能预警 (Severity Warning)
    if is_crash:
        st.error(
            f"⛔ **严重警告**: 虽然有 {pct_wins:.1f}% 的胜率，但平均跌幅 ({avg_loss_depth:.1f}) 远大于平均涨幅 ({avg_win_depth:.1f})。"
            "这意味着你在通过牺牲少数词的**剧烈**排名来换取多数词的**微弱**上涨。请检查是否有点错了关键大词。"
        )
    elif avg_loss_depth > avg_win_depth:
        st.warning("⚠️ **注意**: 平均跌幅略大于平均涨幅，策略收益可能被下跌抵消。")
    else:
        st.success("✅ **健康**: 平均涨幅大于跌幅，且净名次为正，策略在稳步推进。")    

    st.divider()

    # -----------------------------------------------------------
    # DETAILED DRILL-DOWN (Expanders)
    # -----------------------------------------------------------
    col_d1, col_d2 = st.columns(2)

    with col_d1:
        st.subheader("💎 真实增长词 (True Wins)")
        with st.expander(f"查看 {count_wins} 个有效关键词明细", expanded=True):
            if not true_wins_df.empty:
                st.dataframe(
                    true_wins_df[['Top_Queries', 'Pos_Delta', 'Imp_Delta', 'CTR_Delta']].sort_values('Imp_Delta', ascending=False).style.format({
                        'Pos_Delta': "{:.1f}", 'Imp_Delta': "{:+,.0f}", 'CTR_Delta': "{:+.1f}%"
                    }),
                    use_container_width=True
                )
            else:
                st.info("暂无符合条件的关键词。")

    with col_d2:
        st.subheader("🚨 风险预警词 (Risks)")
        with st.expander(f"查看 {count_risk} 个风险关键词明细", expanded=True):
            if not risky_df.empty:
                st.dataframe(
                    risky_df[['Top_Queries', 'Pos_Delta', 'CTR_Delta', 'Position_B']].sort_values('Pos_Delta', ascending=False).style.format({
                        'Pos_Delta': "{:+.1f}", 'CTR_Delta': "{:+.1f}%", 'Position_B': "{:.1f}"
                    }),
                    use_container_width=True
                )
            else:
                st.success("暂无高风险关键词，策略目前安全。")

    # -----------------------------------------------------------
    # SCATTER PLOT (Visual Correlation)
    # -----------------------------------------------------------
    st.divider()
    st.subheader("📈 投入产出分布图 (Impact Distribution)")
    
    def categorize_outcome(row):
        if row['Pos_Delta'] < 0 and row['Imp_Delta'] > 0: return 'True Win'
        if row['CTR_Delta'] > 3 and row['Pos_Delta'] > 0: return 'Risk (Drop)'
        if row['CTR_Delta'] > 3 and row['Pos_Delta'] == 0: return 'Wasted'
        return 'Others'

    st_analysis_df['Category'] = st_analysis_df.apply(categorize_outcome, axis=1)

    fig_scatter = px.scatter(
        st_analysis_df,
        x='CTR_Delta',
        y='Pos_Delta',
        color='Category',
        hover_data=['Top_Queries', 'Impressions_B'],
        color_discrete_map={
            'True Win': 'green',
            'Risk (Drop)': 'red',
            'Wasted': 'gray',
            'Others': 'blue'
        },
        title="CTR 投入 (X轴) vs 排名变化 (Y轴)"
    )
    fig_scatter.update_layout(
        yaxis_title="排名变化 (负数=变好)", 
        xaxis_title="CTR 提升量 (%)",
        yaxis=dict(autorange="reversed") # Optional: make visual "up" mean rank up
    )
    st.plotly_chart(fig_scatter, use_container_width=True)