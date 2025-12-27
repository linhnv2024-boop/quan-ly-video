import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
import time
import altair as alt

# --- CẤU HÌNH HỆ THỐNG ---
SHEET_NAME = "QuanLyVideo_App"
KEY_FILE = "key.json"

# --- 1. KẾT NỐI DATABASE ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Kịch bản 1: Chạy trên Streamlit Cloud (Dùng Secrets)
    # Lưu ý: Trong mục Secrets trên web phải có header là [gcp_service_account]
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # Kịch bản 2: Chạy trên máy tính cá nhân (Dùng file key.json)
    else:
        # Nếu không tìm thấy Secrets, thử tìm file key.json
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        except:
            # Nếu cả 2 đều không có thì báo lỗi rõ ràng
            st.error("⚠️ Lỗi kết nối: Không tìm thấy 'Secrets' trên Cloud hoặc file 'key.json' trên máy.")
            st.stop()
            
    client = gspread.authorize(creds)
    return client

def get_worksheet(ws_name):
    client = init_connection()
    sh = client.open(SHEET_NAME)
    return sh.worksheet(ws_name)

# --- 2. BACKEND LOGIC ---

def login_system(user_id, pin):
    try:
        ws = get_worksheet("CONFIG_USER")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df['User_ID'] = df['User_ID'].astype(str).str.strip()
        df['PIN'] = df['PIN'].astype(str).str.strip()
        user = df[(df['User_ID'] == str(user_id)) & (df['PIN'] == str(pin))]
        if not user.empty:
            return user.iloc[0].to_dict()
        return None
    except Exception as e:
        st.error(f"Lỗi kết nối Sheet CONFIG_USER: {e}")
        return None

def submit_video(user_info, product, title, link):
    """Gửi bài có thêm Tên Video"""
    ws = get_worksheet("DATA_LOGS")
    bai_id = str(uuid.uuid4())[:6]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Cấu trúc dòng mới: [ID, Time, User, SP, TEN_VIDEO, Link, Status, Note]
    row = [bai_id, timestamp, user_info['User_ID'], product, title, link, "Cho_Duyet", ""]
    ws.append_row(row)

def update_submission(bai_id, new_link):
    """Sửa link (Cập nhật lại index cột do đã thêm cột Ten_Video)"""
    ws = get_worksheet("DATA_LOGS")
    try:
        cell = ws.find(str(bai_id))
        row_idx = cell.row
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Cập nhật: Cột 2 (Time), Cột 6 (Link), Cột 7 (Status)
        ws.update_cell(row_idx, 2, timestamp)
        ws.update_cell(row_idx, 6, new_link)
        ws.update_cell(row_idx, 7, "Cho_Duyet")
        return True
    except Exception as e:
        st.error(f"Lỗi khi cập nhật: {e}")
        return False

# --- 3. FRONTEND UI ---

def ui_dashboard_stats(user_info):
    ws = get_worksheet("DATA_LOGS")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    if df.empty:
        st.warning("Chưa có dữ liệu.")
        return

    # ADMIN VIEW
    if str(user_info['Role']).lower() == 'admin':
        st.info("🛡️ Dashboard Admin")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tổng Video", len(df))
        col2.metric("🟢 Đã Duyệt", len(df[df['Trang_Thai'] == 'Da_Duyet']))
        col3.metric("🟡 Chờ Duyệt", len(df[df['Trang_Thai'] == 'Cho_Duyet']))
        col4.metric("🔴 Cần Sửa", len(df[df['Trang_Thai'] == 'Can_Sua']))
        
        st.divider()
        st.subheader("🏆 Bảng Xếp Hạng")
        if not df.empty:
            leaderboard = df['User_ID'].value_counts().reset_index()
            leaderboard.columns = ['Nhan_Vien', 'So_Luong']
            st.bar_chart(leaderboard, x='Nhan_Vien', y='So_Luong')

    # USER VIEW
    else:
        my_df = df[df['User_ID'] == user_info['User_ID']]
        if my_df.empty:
            st.info("Bạn chưa nộp video nào.")
            return

        st.subheader(f"📊 Hiệu Suất: {user_info['Ho_Ten']}")
        c1, c2 = st.columns(2)
        c1.metric("Đã nộp", len(my_df))
        c2.metric("✅ Được duyệt", len(my_df[my_df['Trang_Thai'] == 'Da_Duyet']))
        st.divider()
        st.write("📦 **Phân bổ sản phẩm**")
        prod_chart = my_df['San_Pham'].value_counts().reset_index()
        prod_chart.columns = ['San_Pham', 'So_Luong']
        st.bar_chart(prod_chart, x='San_Pham', y='So_Luong')

def ui_submission_page(user_info):
    st.header("1. Nộp Video Mới")
    product_list = [p.strip() for p in str(user_info['DS_San_Pham']).split(',')]
    
    with st.form("form_nop_bai"):
        san_pham = st.selectbox("Sản Phẩm", product_list)
        c1, c2 = st.columns(2)
        with c1:
            ten_video = st.text_input("Tiêu đề Video (Caption)")
        with c2:
            link = st.text_input("Link Video")
        
        if st.form_submit_button("Gửi Bài Ngay 🚀"):
            if link and ten_video:
                with st.spinner("Đang gửi..."):
                    submit_video(user_info, san_pham, ten_video, link)
                st.success(f"Đã nộp: {ten_video}")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("⚠️ Vui lòng điền đủ Tên video và Link!")

    st.divider()
    st.header("2. Lịch sử bài nộp")
    
    ws = get_worksheet("DATA_LOGS")
    df = pd.DataFrame(ws.get_all_records())
    
    if not df.empty:
        my_logs = df[df['User_ID'] == user_info['User_ID']].iloc[::-1]
        
        for index, row in my_logs.iterrows():
            status = str(row['Trang_Thai']).strip()
            note = str(row['Admin_Note']).strip()
            bai_id = row['ID_Bai']
            title_display = row['Ten_Video'] if row['Ten_Video'] else "Video không tên"
            
            if status == "Da_Duyet":
                with st.expander(f"🟢 {title_display} ({row['San_Pham']})"):
                    st.success("✅ ĐÃ DUYỆT (Khóa)")
                    st.write(f"🔗 Link: {row['Link_Video']}")
            
            elif status == "Can_Sua":
                with st.expander(f"🔴 {title_display} ({row['San_Pham']})", expanded=True):
                    st.error(f"Sếp nhắn: {note}")
                    new_link = st.text_input("Link mới:", key=f"txt_{bai_id}")
                    if st.button("Cập nhật lại", key=f"btn_{bai_id}"):
                        if new_link:
                            update_submission(bai_id, new_link)
                            st.rerun()
            else:
                with st.expander(f"🟡 {title_display} ({row['San_Pham']})"):
                    st.info("⏳ Chờ duyệt")
                    st.write(f"🔗 Link: {row['Link_Video']}")
                    check = st.checkbox("Sửa link", key=f"chk_{bai_id}")
                    if check:
                        lk = st.text_input("Link mới", key=f"txt_{bai_id}")
                        if st.button("Lưu", key=f"btn_{bai_id}"):
                            update_submission(bai_id, lk)
                            st.rerun()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Video Manager Pro", page_icon="🎬", layout="wide")
    if 'user_info' not in st.session_state: st.session_state['user_info'] = None

    if st.session_state['user_info'] is None:
        c1, c2, c3 = st.columns([1,1,1])
        with c2:
            st.title("🔐 Đăng Nhập")
            with st.form("login"):
                uid = st.text_input("User ID")
                pin = st.text_input("PIN", type="password")
                if st.form_submit_button("Vào Hệ Thống"):
                    user = login_system(uid, pin)
                    if user:
                        st.session_state['user_info'] = user
                        st.rerun()
                    else: st.error("Sai ID/PIN")
    else:
        user = st.session_state['user_info']
        with st.sidebar:
            st.title(f"Hi, {user['Ho_Ten']}")
            if st.button("Đăng Xuất"):
                st.session_state['user_info'] = None
                st.rerun()
        
        tab1, tab2 = st.tabs(["📝 NỘP BÀI", "📊 THỐNG KÊ"])
        with tab1: ui_submission_page(user)
        with tab2: ui_dashboard_stats(user)

if __name__ == "__main__":
    main()
