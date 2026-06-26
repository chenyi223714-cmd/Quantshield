print("hello")
import requests
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import io
from datetime import datetime
import os

# --- 預設的 ETF 防禦清單 ---
STUDENT_ETFS = {
    '006208.TW': '富邦台50 (市值)',
    '0050.TW': '元大台灣50 (市值)',
    '00878.TW': '國泰永續高股息 (高息)',
    '0056.TW': '元大高股息 (高息)',
    '00919.TW': '群益台灣精選高息 (高息)'
}

def calculate_rsi(data, window=14):
    """自建 RSI 相對強弱指標演算法"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def screen_multi_factor_stocks():
    """多因子模型：價值初篩 -> 技術面與動能複篩"""
    print("啟動證交所價值初篩...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    res = requests.get(url)
    df = pd.DataFrame(res.json())
    
    df['PEratio'] = pd.to_numeric(df['PEratio'], errors='coerce')
    df['DividendYield'] = pd.to_numeric(df['DividendYield'], errors='coerce')
    df['PBratio'] = pd.to_numeric(df['PBratio'], errors='coerce')
    
    # 【因子 1：價值安全防禦】
    condition = (df['PEratio'] > 0) & (df['PEratio'] < 15) & \
                (df['DividendYield'] > 5.0) & \
                (df['PBratio'] < 1.5)
    
    # 先抓出前 30 名，準備進入第二階段面試
    candidate_stocks = df[condition].sort_values(by='DividendYield', ascending=False).head(30)
    
    final_stocks = []
    print("啟動 Yahoo Finance 動能複篩...")
    
    for index, row in candidate_stocks.iterrows():
        if len(final_stocks) >= 5: # 找到 5 檔就收工
            break
            
        ticker = f"{row['Code']}.TW"
        stock = yf.Ticker(ticker)
        # 抓取 3 個月資料以計算月線和 RSI
        hist = stock.history(period="3mo").dropna(subset=['Close'])
        
        if len(hist) < 25: 
            continue
            
        current_price = hist['Close'].iloc[-1]
        
        # 【因子 2：避開地雷股 (站上 20 日均線)】
        ma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        if current_price < ma_20:
            continue # 股價在月線之下，代表正在跌，剔除！
            
        # 【因子 3：籌碼動能 (RSI 低於 50，尚未過熱)】
        rsi_series = calculate_rsi(hist['Close'])
        current_rsi = rsi_series.iloc[-1]
        
        if pd.isna(current_rsi) or current_rsi > 50:
            continue # RSI 太高代表已經被炒熱了，剔除！
            
        # 通過所有嚴格面試，加入最終名單
        row['RSI'] = round(current_rsi, 1)
        final_stocks.append(row)

    return pd.DataFrame(final_stocks)

def fetch_data_and_plot(final_stocks_df):
    """將 ETF 與多因子過濾出的好股繪製圖表"""
    # 解決 Linux 雲端伺服器沒有微軟正黑體的問題 (改用內建英文字體，避免雲端報錯)
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    
    analysis_text = "<h4>📊 第一區：ETF 核心防禦</h4><ul>"
    
    for ticker, name in STUDENT_ETFS.items():
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo").dropna(subset=['Close'])
        if not hist.empty:
            current_price = round(hist['Close'].iloc[-1], 2)
            pct_change = ((hist['Close'] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
            ax.plot(hist.index, pct_change, label=ticker, linewidth=2, linestyle='--')
            analysis_text += f"<li><b>{ticker} {name}</b>：現價 {current_price} 元</li>"
            
    analysis_text += "</ul><h4>🎯 第二區：多因子黃金陣容 (價值+趨勢+低動能)</h4><ul>"
    
    for index, row in final_stocks_df.iterrows():
        ticker = f"{row['Code']}.TW"
        name = row['Name']
        yield_val = row['DividendYield']
        rsi_val = row['RSI']
        
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo").dropna(subset=['Close'])
        if not hist.empty:
            current_price = round(hist['Close'].iloc[-1], 2)
            pct_change = ((hist['Close'] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
            ax.plot(hist.index, pct_change, label=ticker, linewidth=1.5)
            analysis_text += (f"<li><b>{row['Code']} {name}</b>：現價 {current_price} 元 | "
                              f"殖利率 <span style='color:#10b981;'><b>{yield_val}%</b></span> | "
                              f"RSI <span style='color:#60a5fa;'><b>{rsi_val}</b></span></li>")
    
    analysis_text += "</ul>"

    ax.set_title(f"QuantShield Multi-Factor Radar ({datetime.now().strftime('%Y-%m-%d')})", fontsize=14, color='#10b981')
    ax.set_ylabel("Return (%)")
    ax.axhline(0, color='white', linewidth=1)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, linestyle=':', alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=120)
    img_buf.seek(0)
    plt.close()
    
    return img_buf, analysis_text

def send_daily_email(sender_email, app_password, recipient_email):
    print("啟動多因子模型掃描...")
    final_stocks_df = screen_multi_factor_stocks()
    img_buf, analysis_text = fetch_data_and_plot(final_stocks_df)
    
    msg = MIMEMultipart('related')
    msg['Subject'] = f"📊 QuantShield 多因子量化報告 ({datetime.now().strftime('%m/%d')})"
    msg['From'] = sender_email
    msg['To'] = recipient_email

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #111827; color: #e5e7eb; padding: 20px;">
        <h2 style="color: #10b981;">QuantShield 多因子演算法過濾結果</h2>
        <p>今日個股已通過嚴格的 <b>「價值低估 + 站上月線(避開暴跌) + RSI<50(逢低進場)」</b> 三重濾網：</p>
        <div style="background-color: #1f2937; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            {analysis_text}
        </div>
        <div style="background-color: #1f2937; padding: 15px; border-radius: 8px;">
            <img src="cid:trend_chart" alt="走勢圖" style="max-width: 100%; border-radius: 4px;">
        </div>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html_content, 'html'))
    image = MIMEImage(img_buf.read())
    image.add_header('Content-ID', '<trend_chart>')
    msg.attach(image)
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print("✅ 郵件發送成功！")
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

if __name__ == "__main__":
    # 改為從 GitHub 的加密環境變數讀取，保護你的密碼不外洩！
    SENDER = os.environ.get("GMAIL_USER")
    PASSWORD = os.environ.get("GMAIL_PASS")
    RECIPIENT = os.environ.get("GMAIL_USER") 
    
    send_daily_email(SENDER, PASSWORD, RECIPIENT)