import streamlit as st
import matplotlib.pyplot as plt
import japanize_matplotlib
import yfinance as yf
import json
import os
import datetime
import time
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io

# アプリの基本設定
st.set_page_config(page_title="資産管理ダッシュボード", layout="wide")

# ==========================================
# ★ Google ドライブ連携設定
# ==========================================
GOOGLE_DRIVE_FOLDER_ID = "1qCM2XIpSV-yIe5UT2kBmHXDm0DeitE-f"
SAVE_FILE = "save_data.json"
HISTORY_FILE = "history.json"  

@st.cache_resource
def get_drive_service():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Googleドライブの認証に失敗しました。詳細: {e}")
        st.stop()

drive_service = get_drive_service()

def download_from_drive(filename, default_value):
    try:
        query = f"name = '{filename}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        if not items:
            return default_value
        file_id = items[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return json.loads(fh.read().decode('utf-8'))
    except Exception:
        return default_value

def upload_to_drive(filename, data):
    try:
        query = f"name = '{filename}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        
        json_str = json.dumps(data, ensure_ascii=False, indent=4)
        fh = io.BytesIO(json_str.encode('utf-8'))
        media = MediaIoBaseUpload(fh, mimetype='application/json', resumable=True)
        
        if items:
            file_id = items[0]['id']
            drive_service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {'name': filename, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}
            drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            
    except Exception as e:
        st.error(f"ドライブへの保存に失敗しました: {e}")

# ==========================================
# ★ データの読み込み
# ==========================================
if "data_loaded" not in st.session_state:
    raw_data = download_from_drive(SAVE_FILE, {})
    
    if "stocks" not in raw_data and "funds" not in raw_data:
        st.session_state.portfolio = {
            "funds": {
                "S&P500 (投信)": {"ticker": "1655.T", "multiplier": 35.5, "amount": raw_data.get("MY_SP500", 279771)},
                "オルカン (投信)": {"ticker": "2559.T", "multiplier": 1.2, "amount": raw_data.get("MY_ALL_COUNTRY", 395279)},
                "NASDAQ-100 (投信)": {"ticker": "1545.T", "multiplier": 118.0, "amount": raw_data.get("MY_NASDAQ", 50000)},
                "SOX半導体 (投信)": {"ticker": "2243.T", "multiplier": 6.5, "amount": raw_data.get("MY_SOX", 50000)}
            },
            "stocks": {
                "4755.T": {"name": "楽天グループ", "amount": raw_data.get("MY_RAKUTEN", 100)},
                "9434.T": {"name": "ソフトバンク", "amount": raw_data.get("MY_SOFTBANK", 100)},
                "9432.T": {"name": "NTT", "amount": raw_data.get("MY_NTT", 300)},
                "8173.T": {"name": "上新電機(Joshin)", "amount": raw_data.get("MY_JOSHIN", 2)}
            },
            "settings": {"password": "0824"}
        }
    else:
        st.session_state.portfolio = raw_data
        if "settings" not in st.session_state.portfolio:
            st.session_state.portfolio["settings"] = {"password": "0824"}
            
    st.session_state.history = download_from_drive(HISTORY_FILE, {})
    st.session_state.data_loaded = True

# ==========================================
# ★ ログイン処理
# ==========================================
if not st.session_state.get("authenticated", False):
    st.title("🔒 ログイン")
    pwd = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pwd == st.session_state.portfolio["settings"]["password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが間違っています。")
    st.stop()

# ==========================================
# ★ Yahooファイナンス アクセス制限突破（偽装セッション）
# ==========================================
session = requests.Session()
# 一般的なパソコンのブラウザであるように見せかける
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

@st.cache_data(ttl=3600)
def get_latest_price(ticker_symbol):
    try:
        time.sleep(1) # 1秒待ってからアクセスし、スパム判定を防ぐ
        ticker = yf.Ticker(ticker_symbol, session=session)
        data = ticker.history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
    except Exception:
        return 0.0
    return 0.0

# 画面のタブ構成
tab1, tab2 = st.tabs(["📊 ダッシュボード", "⚙️ 銘柄・設定管理"])

# ==========================================
# 📊 ダッシュボード タブ
# ==========================================
with tab1:
    st.title("資産管理ダッシュボード")
    names, values, fund_details, stock_details = [], [], [], []
    total_amount = 0
    api_limit_hit = False
    
    with st.expander("📝 保有数量の入力・修正", expanded=True):
        st.markdown("### ■ 投資信託")
        for fund_name, fund_info in list(st.session_state.portfolio["funds"].items()):
            new_amount = st.number_input(f"{fund_name} (口数)", min_value=0, value=fund_info["amount"], step=10000, key=f"input_fund_{fund_name}")
            st.session_state.portfolio["funds"][fund_name]["amount"] = new_amount
            
            if new_amount > 0:
                latest_price = get_latest_price(fund_info["ticker"])
                if latest_price == 0.0:
                    api_limit_hit = True
                    
                sim_price = latest_price * fund_info["multiplier"] if latest_price > 0 else 0.0
                eval_val = sim_price * (new_amount / 10000)
                
                names.append(fund_name)
                values.append(eval_val)
                total_amount += eval_val
                
                if latest_price > 0:
                    fund_details.append(f"【{fund_name}】 推定基準: 約{sim_price:,.0f}円 / 評価額: {eval_val:,.0f}円")
                else:
                    fund_details.append(f"【{fund_name}】 ⚠️取得エラー (0円計算)")

        st.markdown("### ■ 株式・ETF")
        for stock_code, stock_info in list(st.session_state.portfolio["stocks"].items()):
            new_amount = st.number_input(f"{stock_info['name']} (株数)", min_value=0, value=stock_info["amount"], key=f"input_stock_{stock_code}")
            st.session_state.portfolio["stocks"][stock_code]["amount"] = new_amount
            
            if new_amount > 0:
                latest_price = get_latest_price(stock_code)
                if latest_price == 0.0:
                    api_limit_hit = True
                    
                eval_val = latest_price * new_amount if latest_price > 0 else 0.0
                
                names.append(stock_info["name"])
                values.append(eval_val)
                total_amount += eval_val
                
                if latest_price > 0:
                    stock_details.append(f"【{stock_info['name']}】 現在値: {latest_price:,.1f}円 / 評価額: {eval_val:,.0f}円")
                else:
                    stock_details.append(f"【{stock_info['name']}】 ⚠️取得エラー (0円計算)")

    st.divider()
    st.subheader(f"資産総額: {total_amount:,.0f}円")
    
    if api_limit_hit:
        st.warning("⚠️ Yahooのアクセス制限中ですが、アプリは正常に稼働しています（取得できない銘柄は0円計算）。保存や設定は通常通り行えます。")
    
    if st.button("💾 現在の数値をセーブする", key="main_save_btn"):
        with st.spinner("Google ドライブにセーブ中..."):
            upload_to_drive(SAVE_FILE, st.session_state.portfolio)
            if not api_limit_hit:
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                st.session_state.history[today_str] = total_amount
                upload_to_drive(HISTORY_FILE, st.session_state.history)
        st.success("セーブ完了！Google ドライブに同期しました。")
        time.sleep(1.5)
        st.rerun()
        
    if fund_details or stock_details:
        with st.expander("🔍 各銘柄の評価額の内訳詳細", expanded=False):
            for detail in fund_details: st.text(detail)
            for detail in stock_details: st.text(detail)

    st.markdown("### ■ ポートフォリオ比率")
    if values and sum(values) > 0:
        fig1, ax1 = plt.subplots(figsize=(10, 6)) 
        wedges, texts = ax1.pie(values, startangle=90, counterclock=False)
        ax1.axis("equal")
        legend_labels = [f"{name} ({(val / total_amount) * 100:.1f}%)" for name, val in zip(names, values)]
        ax1.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        st.pyplot(fig1)
    else:
        st.info("株価情報が取得できていないか、保有数量が0のためグラフを非表示にしています。")

    st.divider()
    st.markdown("### ■ 資産推移（履歴）")
    if st.session_state.history:
        sorted_dates = sorted(st.session_state.history.keys())
        sorted_totals = [st.session_state.history[d] for d in sorted_dates]
        fig2, ax2 = plt.subplots(figsize=(10, 6))
        ax2.plot(sorted_dates, sorted_totals, marker='o', linestyle='-', color='tab:blue')
        ax2.set_ylabel("総資産額 (円)")
        ax2.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(rotation=45)
        ax2.get_yaxis().get_major_formatter().set_scientific(False)
        plt.tight_layout()
        st.pyplot(fig2)
    else:
        st.info("まだ履歴がありません。セーブするとデータが作成されます。")

# ==========================================
# ⚙️ 銘柄・設定管理 タブ
# ==========================================
with tab2:
    st.title("⚙️ 銘柄・設定管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("➕ 株式・ETFを追加")
        new_stock_code = st.text_input("銘柄コード (例: 7203.T)")
        new_stock_name = st.text_input("銘柄名 (例: トヨタ自動車)")
        if st.button("株式・ETFを追加する"):
            if new_stock_code and new_stock_name:
                st.session_state.portfolio["stocks"][new_stock_code] = {"name": new_stock_name, "amount": 0}
                with st.spinner("追加中..."):
                    upload_to_drive(SAVE_FILE, st.session_state.portfolio)
                st.cache_data.clear()
                st.success(f"「{new_stock_name}」を追加しました！")
                time.sleep(1)
                st.rerun()
                
        st.divider()
        st.subheader("🗑️ 株式・ETFを削除")
        stock_options = ["選択してください"] + list(st.session_state.portfolio["stocks"].keys())
        stock_to_delete = st.selectbox("削除する株式を選択", options=stock_options, format_func=lambda x: f"{x} ({st.session_state.portfolio['stocks'][x]['name']})" if x != "選択してください" else x)
        if st.button("株式・ETFを削除する") and stock_to_delete != "選択してください":
            del st.session_state.portfolio["stocks"][stock_to_delete]
            with st.spinner("削除中..."):
                upload_to_drive(SAVE_FILE, st.session_state.portfolio)
            st.success("削除しました！")
            time.sleep(1)
            st.rerun()

    with col2:
        st.subheader("➕ 投資信託を追加")
        new_fund_name = st.text_input("投資信託名 (例: SBI・V·S&P500)")
        new_fund_ticker = st.text_input("連動ETFのコード (例: 1655.T)")
        new_fund_multiplier = st.number_input("基準価額の倍率 (例: 35.5)", min_value=0.0, value=1.0, step=0.1)
        if st.button("投資信託を追加する"):
            if new_fund_name and new_fund_ticker:
                st.session_state.portfolio["funds"][new_fund_name] = {"ticker": new_fund_ticker, "multiplier": new_fund_multiplier, "amount": 0}
                with st.spinner("追加中..."):
                    upload_to_drive(SAVE_FILE, st.session_state.portfolio)
                st.cache_data.clear()
                st.success(f"「{new_fund_name}」を追加しました！")
                time.sleep(1)
                st.rerun()
                
        st.divider()
        st.subheader("🗑️ 投資信託を削除")
        fund_options = ["選択してください"] + list(st.session_state.portfolio["funds"].keys())
        fund_to_delete = st.selectbox("削除する投資信託を選択", options=fund_options)
        if st.button("投資信託を削除する") and fund_to_delete != "選択してください":
            del st.session_state.portfolio["funds"][fund_to_delete]
            with st.spinner("削除中..."):
                upload_to_drive(SAVE_FILE, st.session_state.portfolio)
            st.success("削除しました！")
            time.sleep(1)
            st.rerun()

    st.divider()
    st.subheader("🔑 パスワードの変更")
    current_pwd = st.text_input("現在のパスワード", type="password")
    new_pwd = st.text_input("新しいパスワード", type="password")
    if st.button("パスワードを変更する"):
        if current_pwd == st.session_state.portfolio["settings"]["password"]:
            if new_pwd:
                st.session_state.portfolio["settings"]["password"] = new_pwd
                with st.spinner("パスワードを更新中..."):
                    upload_to_drive(SAVE_FILE, st.session_state.portfolio)
                st.success("変更しました！次回から新しいパスワードが必要です。")
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("新しいパスワードを入力してください。")
        else:
            if current_pwd:
                st.error("現在のパスワードが間違っています。")