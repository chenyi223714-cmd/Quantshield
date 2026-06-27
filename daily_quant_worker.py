import os
import requests
import pandas as pd
import yfinance as yf
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ==========================================
# ⚙️ 第一區：核心防禦 (長線存股，只買不賣)
# ==========================================
STUDENT_ETFS = {
    '006208.TW': '富邦台50 (台股大盤，穩健底層)',
    '00878.TW': '國泰永續高股息 (ESG高息，抗跌防禦)',
    '00713.TW': '元大台灣高息低波 (聰明選股，高息且低波動)',
    '00919.TW': '群益精選高息 (積極型高息，高殖利率攻擊)',
    '00757.TW': '統一FANG+ (美股10大科技巨頭，極致爆發力)',
    '00662.TW': '富邦NASDAQ (美股科技大盤，長線趨勢)'
}

# ==========================================
# ⚙️ 第二區：個人持股健檢 (移動停利雷達)
# ==========================================
MY_PORTFOLIO = {
    # 未來如果有買進股票，就把前面的 # 拿掉並改成你的股票
    # '2330.TW': {'name': '台積電', 'buy_date': '2026-06-01', 'trailing_stop': 0.10}
}

# ==========================================
# 以下為系統核心運算區，未來不需更動
# ==========================================

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_portfolio_health():
    """檢查個人持股，計算是否觸發移動停利"""
    results_html = ""
    if not MY_PORTFOLIO:
        return "<p style='color:#9ca3af;'>目前無個股持倉，維持空手紀律。</p>"
        
    results_html += "<ul>"
    for ticker, info in MY_PORTFOLIO.items():
        stock = yf.Ticker(ticker)
        hist = stock.history(start=info['buy_date']).dropna(subset=['Close'])
        
        if hist.empty:
            results_html += f"<li>{info['name']}：查無資料</li>"
            continue
            
        current_price = round(hist['Close'].iloc[-1], 2)
        max_price = round(hist['Close'].max(), 2)
        drawdown = (max_price - current_price) / max_price
        
        if drawdown >= info['trailing_stop']:
            status_text = f"<span style='color:#ef4444; font-weight:bold;'>🔴 觸發賣出 (回檔 {(drawdown*100):.1f}%)</span>"
        else:
            status_text = f"<span style='color:#10b981;'>🟢 安全續抱 (回檔 {(drawdown*100):.1f}%)</span>"
            
        results_html += (f"<li><b>{ticker} {info['name']}</b>："
                         f"買後最高 <b>{max_price}</b> 元 | "
                         f"現價 <b>{current_price}</b> 元 | {status_text}</li>")
    results_html += "</ul>"
    return results_html

def screen_multi_factor_stocks():
    """多因子模型 + 防彈機制"""
    print("啟動證交所價值初篩...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    
    # 戴上最完整的瀏覽器面具
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 🛡️ 終極防彈衣：如果被證交所擋住，優雅退場不當機
    try:
        res = requests.get(url, headers=headers, timeout=10)
        df = pd.DataFrame(res.json())
    except Exception as e:
        print(f"🚨 證交所資料解析失敗 (被擋 IP 或假日無資料)：{e}")
        # 回傳空表，讓系統繼續寄送 ETF 和健檢報表
        return pd.DataFrame(columns=['Code', 'Name', 'DividendYield', 'RSI'])
        
    df['PEratio'] = pd.to_numeric(df['PEratio'], errors='coerce')
    df['DividendYield'] = pd.to_numeric(df['DividendYield'], errors='coerce')
    df['PBratio'] = pd.to_numeric(df['PBratio'], errors='coerce')
    
    condition = (df['PEratio'] > 0) & (df['PEratio'] < 15) & \
                (df['DividendYield'] > 5.0) & \
                (df['PBratio'] < 1.5)
    
    candidate_stocks = df[condition].sort_values(by='DividendYield', ascending=False).head(30)
    final_stocks = []
    
    for index, row in candidate_stocks.iterrows():
        if len(final_stocks) >= 5: 
            break
        ticker = f"{row['Code']}.TW"
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo").dropna(subset=['Close'])
        
        if len(hist) < 25: continue
        current_price = hist['Close'].iloc[-1]
        ma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        
        if current_price < ma_20: continue
            
        rsi_series = calculate_rsi(hist['Close'])
        current_rsi = rsi_series.iloc[-1]
        
        if pd.isna(current_rsi) or current_rsi > 50: continue
            
        row['RSI'] = round(current_rsi, 1)
        final_stocks.append(row)

    return pd.DataFrame(final_stocks)

def send_daily_email(sender_email, app_password, recipient_email):
    print("啟動全能量化系統...")
    portfolio_html = check_portfolio_health()
    final_stocks_df = screen_multi_factor_stocks()
    
    analysis_text = "<h4>📊 第一區：核心 ETF (長線存股，只買不賣)</h4><ul>"
    for ticker, name in STUDENT_ETFS.items():
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo").dropna(subset=['Close'])
        if not hist.empty:
            current_price = round(hist['Close'].iloc[-1], 2)
            analysis_text += f"<li><b>{ticker} {name}</b>：現價 {current_price} 元</li>"
            
    analysis_text += "</ul><h4>🎯 第三區：盤後尋寶 (適合建倉新標的)</h4><ul>"
    if final_stocks_df.empty:
        analysis_text += "<p style='color:#9ca3af;'>今日大盤無符合嚴格價值與動能之標的 (或證交所連線異常)。</p>"
    else:
        for index, row in final_stocks_df.iterrows():
            ticker = f"{row['Code']}.TW"
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d").dropna(subset=['Close'])
            current_price = round(hist['Close'].iloc[-1], 2) if not hist.empty else "N/A"
            analysis_text += (f"<li><b>{row['Code']} {row['Name']}</b>：現價 {current_price} 元 | "
                              f"殖利率 <span style='color:#10b981;'><b>{row['DividendYield']}%</b></span> | "
                              f"RSI <span style='color:#60a5fa;'><b>{row['RSI']}</b></span></li>")
    analysis_text += "</ul>"

    msg = MIMEMultipart('related')
    msg['Subject'] = f"📊 QuantShield 全能雷達：存股+健檢+尋寶 ({datetime.now().strftime('%m/%d')})"
    msg['From'] = sender_email
    msg['To'] = recipient_email

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #111827; color: #e5e7eb; padding: 20px;">
        <h2 style="color: #10b981;">QuantShield 個人量化交易中心</h2>
        
        <div style="background-color: #374151; padding: 15px; border-radius: 8px; border-left: 5px solid #f59e0b; margin-bottom: 20px;">
            <h4 style="margin-top:0; color:#fcd34d;">🚨 第二區：個人持股移動停利雷達 (策略C)</h4>
            {portfolio_html}
        </div>

        <div style="background-color: #1f2937; padding: 15px; border-radius: 8px;">
            {analysis_text}
        </div>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html_content, 'html'))
    
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
    SENDER = os.environ.get("GMAIL_USER")
    PASSWORD = os.environ.get("GMAIL_PASS")
    RECIPIENT = os.environ.get("GMAIL_USER") 
    
    send_daily_email(SENDER, PASSWORD, RECIPIENT)
