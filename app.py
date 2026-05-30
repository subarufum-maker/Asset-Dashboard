import streamlit as st
import matplotlib.pyplot as plt
import japanize_matplotlib
import yfinance as yf
import json
import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

# アプリの基本設定
st.set_page_config(page_title="資産管理ダッシュボード", layout="wide")

# ==========================================
# ★ ログインパスワード
# ==========================================
APP_PASSWORD = "0824"  

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔒 ログイン")
    pwd = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pwd == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが間違っています。")
    st.stop()

# ==========================================
# ★ Google ドライブ連携設定
# ==========================================
# フォルダID
GOOGLE_DRIVE_FOLDER_ID = "1qCM2XIpSV-yIe5UT2kBmHXDm0DeitE-f"

# Streamlit Cloudの「Secrets（秘密の金庫）」から直接認証情報を読み込む
try:
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    drive_service = build('drive', 'v3', credentials=creds)
except Exception as e:
    st.error(f"Googleドライブの認証に失敗しました。Streamlit CloudのSecrets設定を確認してください。\n詳細: {e}")
    st.stop()

SAVE_FILE = "save_data.json"
HISTORY_FILE = "history.json"  

# 初期データ
default_data = {
    "MY_SP500": 279771,
    "MY_ALL_COUNTRY": 395279,
    "MY_NASDAQ": 50000,
    "MY_SOX": 50000,
    "MY_RAKUTEN": 100,
    "MY_SOFTBANK": 100,
    "MY_NTT": 300,
    "MY_JOSHIN": 2
}

# ドライブからファイルをダウンロードする関数
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
    except Exception as e:
        return default_value

# ドライブへファイルをアップロード（上書き）する関数
def upload_to_drive(filename, data):
    try:
        query = f"name = '{filename}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        
        json_str = json.dumps(data, ensure_ascii=False, indent=4)
        media = MediaFileUpload(
            io.BytesIO(json_str.encode('utf-8')), 
            mimetype='application/json', 
            resumable=True
        )
        
        if items:
            file_id = items[0]['id']
            drive_service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {
                'name': filename,
                'parents': [GOOGLE_DRIVE_FOLDER_ID]
            }
            drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    except Exception as e:
        st.error(f"ドライブへの保存に失敗しました: {e}")

# データの読み込み（Googleドライブから取得）
user_data = download_from_drive(SAVE_FILE, default_data)
history_data = download_from_drive(HISTORY_FILE, {})

# アプリの画面構成
st.title("資産管理ダッシュボード")

names = []
values = []
total_amount = 0

# 1. 投資信託エリア
st.sidebar.header("■ 投資信託")
sp500_kuchi = st.sidebar.number_input("S&P500 (保有口数)", min_value=0, value=user_data.get("MY_SP500", 279771), step=10000)
if sp500_kuchi > 0:
    ticker = yf.Ticker("1655.T")
    data = ticker.history(period="1d")
    if not data.empty:
        simulated_kijun = data['Close'].iloc[-1] * 35.5 
        sp500_eval = simulated_kijun * (sp500_kuchi / 10000)
        names.append("S&P500 (投信)")
        values.append(sp500_eval)
        total_amount += sp500_eval
        st.text(f"【S&P500】 推定基準: 約{simulated_kijun:,.0f}円 / 評価額: {sp500_eval:,.0f}円")

alld_kuchi = st.sidebar.number_input("オルカン (保有口数)", min_value=0, value=user_data.get("MY_ALL_COUNTRY", 395279), step=10000)
if alld_kuchi > 0:
    ticker = yf.Ticker("2559.T")
    data = ticker.history(period="1d")
    if not data.empty:
        simulated_kijun = data['Close'].iloc[-1] * 1.2
        alld_eval = simulated_kijun * (alld_kuchi / 10000)
        names.append("オルカン (投信)")
        values.append(alld_eval)
        total_amount += alld_eval
        st.text(f"【オルカン】 推定基準: 約{simulated_kijun:,.0f}円 / 評価額: {alld_eval:,.0f}円")

nasdaq_kuchi = st.sidebar.number_input("NASDAQ-100 (保有口数)", min_value=0, value=user_data.get("MY_NASDAQ", 50000), step=10000)
if nasdaq_kuchi > 0:
    ticker = yf.Ticker("1545.T")
    data = ticker.history(period="1d")
    if not data.empty:
        simulated_kijun = data['Close'].iloc[-1] * 118
        nasdaq_eval = simulated_kijun * (nasdaq_kuchi / 10000)
        names.append("NASDAQ-100 (投信)")
        values.append(nasdaq_eval)
        total_amount += nasdaq_eval
        st.text(f"【NASDAQ-100】 推定基準: 約{simulated_kijun:,.0f}円 / 評価額: {nasdaq_eval:,.0f}円")

sox_kuchi = st.sidebar.number_input("SOX半導体 (保有口数)", min_value=0, value=user_data.get("MY_SOX", 50000), step=10000)
if sox_kuchi > 0:
    ticker = yf.Ticker("2243.T")
    data = ticker.history(period="1d")
    if not data.empty:
        simulated_kijun = data['Close'].iloc[-1] * 6.5
        sox_eval = simulated_kijun * (sox_kuchi / 10000)
        names.append("SOX半導体 (投信)")
        values.append(sox_eval)
        total_amount += sox_eval
        st.text(f"【SOX半導体】 推定基準: 約{simulated_kijun:,.0f}円 / 評価額: {sox_eval:,.0f}円")

st.sidebar.divider()

# 2. 株式・ETFエリア
st.sidebar.header("■ 株式・ETF")
rakuten_kabu = st.sidebar.number_input("楽天 (株数)", min_value=0, value=user_data.get("MY_RAKUTEN", 100))
softbank_kabu = st.sidebar.number_input("ソフトバンク (株数)", min_value=0, value=user_data.get("MY_SOFTBANK", 100))
ntt_kabu = st.sidebar.number_input("NTT (株数)", min_value=0, value=user_data.get("MY_NTT", 300))
joshin_kabu = st.sidebar.number_input("Joshin (株数)", min_value=0, value=user_data.get("MY_JOSHIN", 2))

portfolio_kabu = {
    "4755.T": {"名前": "楽天グループ", "保有数": rakuten_kabu},
    "9434.T": {"名前": "ソフトバンク", "保有数": softbank_kabu},
    "9432.T": {"名前": "NTT", "保有数": ntt_kabu},
    "8173.T": {"名前": "上新電機(Joshin)", "保有数": joshin_kabu}
}

for code, info in portfolio_kabu.items():
    if info["保有数"] > 0:
        ticker = yf.Ticker(code)
        todays_data = ticker.history(period="1d")
        if not todays_data.empty:
            latest_price = todays_data['Close'].iloc[-1]
            evaluation = info["保有数"] * latest_price
            names.append(info['名前'])
            values.append(evaluation)
            total_amount += evaluation
            st.text(f"【{info['名前']}】 現在値: {latest_price:,.1f}円 / 評価額: {evaluation:,.0f}円")

# ★ セーブボタン機能（Google ドライブへ保存）
st.sidebar.divider()
if st.sidebar.button("💾 現在の数値をセーブする"):
    new_data = {
        "MY_SP500": sp500_kuchi,
        "MY_ALL_COUNTRY": alld_kuchi,
        "MY_NASDAQ": nasdaq_kuchi,
        "MY_SOX": sox_kuchi,
        "MY_RAKUTEN": rakuten_kabu,
        "MY_SOFTBANK": softbank_kabu,
        "MY_NTT": ntt_kabu,
        "MY_JOSHIN": joshin_kabu
    }
    upload_to_drive(SAVE_FILE, new_data)
    
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    history_data[today_str] = total_amount
    upload_to_drive(HISTORY_FILE, history_data)
    
    st.sidebar.success("セーブ完了！Google ドライブに同期しました。")

# 3. グラフ表示エリア
st.divider()
st.subheader(f"資産総額: {total_amount:,.0f}円")

st.markdown("### ■ ポートフォリオ比率")
if values:
    fig1, ax1 = plt.subplots(figsize=(10, 6)) 
    wedges, texts = ax1.pie(values, startangle=90, counterclock=False)
    ax1.axis("equal")
    
    legend_labels = []
    for name, val in zip(names, values):
        percent = (val / total_amount) * 100
        legend_labels.append(f"{name} ({percent:.1f}%)")
    
    ax1.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
    st.pyplot(fig1)
else:
    st.warning("保有データがありません。")

st.divider()

st.markdown("### ■ 資産推移（履歴）")
if history_data:
    sorted_dates = sorted(history_data.keys())
    sorted_totals = [history_data[d] for d in sorted_dates]
    
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    ax2.plot(sorted_dates, sorted_totals, marker='o', linestyle='-', color='tab:blue')
    
    ax2.set_ylabel("総資産額 (円)")
    ax2.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(rotation=45)
    ax2.get_yaxis().get_major_formatter().set_scientific(False)
    plt.tight_layout()
    st.pyplot(fig2)
else:
    st.info("まだ履歴がありません。セーブするとドライブにデータが作成されます。")