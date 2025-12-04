import streamlit as st
import pandas as pd
from supabase import create_client, Client
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
# 2. Helper Functions
# -----------------------------------------------------------------------------
def get_or_create_domain_id(domain_name):
    """
    Checks the 'Domains' table for the domain name. 
    Returns the ID if found, or creates a new entry and returns the new ID.
    """
    try:
        # 1. Check if exists
        response = supabase.table('Domains').select("id").eq("domain_name", domain_name).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]['id']
        else:
            # 2. Create new if not exists
            st.toast(f"New domain detected: {domain_name}. Creating ID...", icon="🆕")
            insert_response = supabase.table('Domains').insert({"domain_name": domain_name}).execute()
            if insert_response.data:
                return insert_response.data[0]['id']
            else:
                raise Exception(f"Failed to create domain: {domain_name}")
                
    except Exception as e:
        st.error(f"Database Error resolving domain '{domain_name}'. Ensure your 'Domains' table has 'id' and 'domain_name' columns. Error: {e}")
        return None

def batch_insert(table_name, df, chunk_size=1000):
    """Inserts a pandas DataFrame into Supabase in chunks."""
    records = df.to_dict(orient='records')
    total_records = len(records)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_records, chunk_size):
        chunk = records[i:i + chunk_size]
        try:
            supabase.table(table_name).insert(chunk).execute()
            progress = min((i + chunk_size) / total_records, 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Uploading... {min(i + chunk_size, total_records)} / {total_records} rows")
        except Exception as e:
            st.error(f"❌ Error inserting chunk {i}-{i+chunk_size}: {e}")
            return False
            
    status_text.success(f"✅ Successfully uploaded {total_records} rows to '{table_name}'!")
    return True

# -----------------------------------------------------------------------------
# 3. Main Upload Interface
# -----------------------------------------------------------------------------
st.set_page_config(page_title="SEO Data Uploader", page_icon="📤")

st.title("📤 SEO Data Uploader")
st.markdown("This tool resolves Domain Names to IDs and inserts bulk CSV data.")
st.divider()

# --- Step 1: Configuration ---
st.subheader("1. Configuration")
table_option = st.selectbox("Select Target Table", ["GSC", "Top_Queries"])

st.divider()

# --- Step 2: Upload CSV ---
st.subheader("2. Upload CSV")
st.info("Your CSV must contain the columns: **Phase_id** (int) and a **Domain Name** column (e.g., 'Domain').")
uploaded_file = st.file_uploader(f"Choose a CSV file for {table_option}", type=['csv'])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        st.write("### Data Preview")
        st.dataframe(df.head(3))

        # --- VALIDATION & PROCESSING ---
        
        # 1. Identify Domain Name Column
        domain_col_name = None
        possible_domain_headers = ['Domain', 'domain', 'Domain Name', 'domain_name']
        
        for col in df.columns:
            if col in possible_domain_headers:
                domain_col_name = col
                break
        
        if not domain_col_name:
            st.error("❌ CSV must contain a column for Domain Name (e.g., 'Domain', 'domain_name').")
            st.stop()
            
        if 'Phase_id' not in df.columns:
            st.error("❌ CSV must contain a column named 'Phase_id'.")
            st.stop()
        
        # 2. Domain Name Resolution (Map string names to Integer IDs)
        st.write("---")
        st.write("🔄 **Resolving Domain Names to IDs...**")
        
        unique_domains = df[domain_col_name].astype(str).str.strip().unique()
        domain_map = {}
        
        for dom in unique_domains:
            if dom in ('', 'nan'): continue
            resolved_id = get_or_create_domain_id(dom)
            if resolved_id:
                domain_map[dom] = resolved_id
            else:
                st.stop() 
        
        # Apply the map to create the actual 'Domain_id' column
        df['Domain_id'] = df[domain_col_name].astype(str).str.strip().map(domain_map)
        
        if df['Domain_id'].isnull().any():
            st.error("Error mapping some domain names to IDs. Check for empty domain cells.")
            st.stop()
            
        st.success("✅ All domains resolved to IDs successfully!")

        # 3. Column Cleanup and Formatting
        if table_option == "GSC":
            target_cols = ['Clicks', 'Impressions', 'Position', 'Date', 'Phase_id', 'Domain_id']
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            else:
                st.error("❌ GSC data requires a 'Date' column.")
                st.stop()
        else:
            target_cols = ['Top_Queries', 'Clicks', 'Impressions', 'Position', 'Phase_id', 'Domain_id']

        missing = [c for c in target_cols if c not in df.columns]
        if missing:
            st.error(f"❌ Missing columns for database insert: {missing}")
            st.stop()

        df_final = df[target_cols]

        # --- Step 4: Confirm & Upload ---
        st.write("---")
        st.warning(f"Ready to upload {len(df_final)} rows to **{table_option}**.")
        
        if st.button("🚀 Confirm and Upload Data"):
            with st.spinner("Processing upload..."):
                batch_insert(table_option, df_final)

    except Exception as e:
        st.error(f"An unexpected error occurred. Check data types in CSV. Error: {e}")