import os
import requests
import pandas as pd
import yfinance as yf
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import urllib.parse
import xml.etree.ElementTree as ET
import time

# ==========================================
# ⚙️ 第一區：核心防禦 (長線存股，只買不賣)
# ==========================================
STUDENT_ETFS = {
    '006208.TW': '富邦台50',
    '00878.TW': '國泰永續高股息',
    '00713.TW': '元大台灣高息低波',
    '00919.TW': '群益精選高息',
    '00757.TW': '統一FANG+',
    '00662.TW': '富邦NASDAQ'
}

# ==========================================
# ⚙️ 第二區：個人持股健檢 (移動停利雷達)
# ==========================================
MY_PORTFOLIO = {
    # '2330.TW': {'name': '台積電', 'buy_date': '2026-06-01', 'trailing_stop': 0.10}
}

# ==========================================
# 系統核心運算區
# ==========================================

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_portfolio_health():
    results_html = ""
    if not MY_PORTFOLIO:
        return "<p style='color:#9ca3af;'>目前無個股持倉，維持空手紀律。</p>"
        
    results_html += "<ul>"
    for ticker, info in MY_PORTFOLIO.items():
        stock = yf.Ticker(ticker)
        hist = stock.history(start=info['buy_date']).dropna(subset=['Close'])
        if hist.empty:
            continue
        current_price = round(hist['Close'].iloc[-1], 2)
        max_price = round(hist['Close'].max(), 2)
        drawdown = (max_price - current_price) / max_price
        trigger_price = round(max_price * (1 - info['trailing_stop']), 2)
        
        if drawdown >= info['trailing_stop']:
            status_text = f"<span style='color:#ef4444; font-weight:bold;'>🔴 觸發賣出 (請用限價 {trigger_price} 元賣出)</span>"
        else:
            status_text = f"<span style='color:#10b981;'>🟢 安全續抱 (跌破 {trigger_price} 元時將觸發賣出)</span>"
            
        results_html += (f"<li><b>{ticker} {info['name']}</b>：現價 <b>{current_price}</b> 元 | {status_text}</li>")
    results_html += "</ul>"
    return results_html

def screen_multi_factor_stocks():
    print("啟動證交所價值初篩...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    # 💡 企業級重試機制：最多挑戰 3 次
    max_retries = 3
    df = pd.DataFrame() # 先建立空表格
    
    for attempt in range(max_retries):
        try:
            res = requests.get(url, headers=headers, timeout=10)
            # 檢查對方是不是給我們正常的網頁 (200 代表成功)
            if res.status_code == 200:
                df = pd.DataFrame(res.json())
                print(f"✅ 第 {attempt + 1} 次嘗試：成功取得證交所資料！")
                break # 成功就跳出迴圈，不繼續重試了
            else:
                print(f"⚠️ 第 {attempt + 1} 次嘗試：證交所伺服器異常 (狀態碼: {res.status_code})")
        
        except Exception as e:
            print(f"⚠️ 第 {attempt + 1} 次嘗試失敗：{e}")
            
        # 如果還沒到最後一次，就等 5 秒再試
        if attempt < max_retries - 1:
            print("⏳ 休息 5 秒後重新敲門...")
            time.sleep(5)
            
    # 如果試了 3 次還是失敗，就真的放棄
    if df.empty:
        print("🚨 連續 3 次遭證交所拒絕，今日放棄抓取尋寶名單。")
        return pd.DataFrame(columns=['Code', 'Name', 'DividendYield', 'RSI'])
        
    df['PEratio'] = pd.to_numeric(df['PEratio'], errors='coerce')
    df['DividendYield'] = pd.to_numeric(df['DividendYield'], errors='coerce')
    df['PBratio'] = pd.to_numeric(df['PBratio'], errors='coerce')
    
    condition = (df['PEratio'] > 0) & (df['PEratio'] < 15) & (df['DividendYield'] > 5.0) & (df['PBratio'] < 1.5)
    candidate_stocks = df[condition].sort_values(by='DividendYield', ascending=False).head(30)
    final_stocks = []
    
    for index, row in candidate_stocks.iterrows():
        if len(final_stocks) >= 5: break
        ticker = f"{row['Code']}.TW"
        hist = yf.Ticker(ticker).history(period="3mo").dropna(subset=['Close'])
        if len(hist) < 25: continue
        current_price = hist['Close'].iloc[-1]
        ma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        if current_price < ma_20: continue
        current_rsi = calculate_rsi(hist['Close']).iloc[-1]
        if pd.isna(current_rsi) or current_rsi > 50: continue
            
        row['RSI'] = round(current_rsi, 1)
        final_stocks.append(row)
    return pd.DataFrame(final_stocks)

# ==========================================
# 🆕 新增：Google 新聞爬蟲引擎
# ==========================================
def fetch_google_news(keyword):
    """透過 Google News RSS 抓取繁體中文新聞"""
    encoded_kw = urllib.parse.quote(f"{keyword} 股票 OR 營收")
    url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    news_html = ""
    try:
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        items = root.findall('./channel/item')[:3] # 只取前 3 則最新新聞
        for item in items:
            title = item.find('title').text
            link = item.find('link').text
            news_html += f"<li style='margin-bottom: 8px;'><a href='{link}' style='color:#60a5fa; text-decoration:none;'>{title}</a></li>"
        if not news_html:
            return "<li style='color:#9ca3af;'>今日無重大新聞</li>"
        return news_html
    except Exception:
        return "<li style='color:#ef4444;'>新聞抓取失敗</li>"

# ==========================================
# 郵件發送模組 (拆分為量化報表與新聞報表)
# ==========================================
def send_email(sender_email, app_password, recipient_emails, subject, html_content):
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = sender_email
    
    # 判斷收件人是一個(字串)還是多個(清單)，並用逗號串接起來
    if isinstance(recipient_emails, list):
        msg['To'] = ", ".join(recipient_emails)
    else:
        msg['To'] = recipient_emails
    msg.attach(MIMEText(html_content, 'html'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ 郵件發送成功：{subject}")
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

if __name__ == "__main__":
    SENDER = os.environ.get("GMAIL_USER")
    PASSWORD = os.environ.get("GMAIL_PASS")
    
    # 📝 你的訂閱者名單 (用中括號包起來，每個信箱用引號，並用逗號隔開)
    SUBSCRIBERS = [
        SENDER                       
    ]
    
    print("啟動全能量化系統...")
    # 1. 先執行一次最耗時的運算與抓資料
    portfolio_html = check_portfolio_health()
    final_stocks_df = screen_multi_factor_stocks()
    
    # ---------------------------------------------------------
    # 📧 發送第一封信：量化交易報表 (與之前相同)
    # ---------------------------------------------------------
    analysis_text = "<h4>📊 第一區：核心 ETF</h4><ul>"
    for ticker, name in STUDENT_ETFS.items():
        analysis_text += f"<li><b>{ticker} {name}</b></li>"
    analysis_text += "</ul><h4>🎯 第三區：盤後尋寶</h4><ul>"
    
    if final_stocks_df.empty:
        analysis_text += "<p style='color:#9ca3af;'>今日大盤無符合嚴格條件之標的。</p>"
    else:
        for index, row in final_stocks_df.iterrows():
            analysis_text += f"<li><b>{row['Code']} {row['Name']}</b>：限價 {row['Close'] if 'Close' in row else '現價'} 元買進</li>"
    analysis_text += "</ul>"

    quant_html = f"""
    <html><body style="font-family: Arial; background-color: #111827; color: #e5e7eb; padding: 20px;">
        <h2 style="color: #10b981;">QuantShield 量化交易中心</h2>
        <div style="background-color: #374151; padding: 15px; border-radius: 8px; border-left: 5px solid #f59e0b; margin-bottom: 20px;">
            <h4 style="margin-top:0; color:#fcd34d;">🚨 第二區：移動停利雷達</h4>{portfolio_html}
        </div>
        <div style="background-color: #1f2937; padding: 15px; border-radius: 8px;">{analysis_text}</div>
    </body></html>
    """
    send_email(SENDER, PASSWORD, SUBSCRIBERS, f"📊 QuantShield 全能雷達 ({datetime.now().strftime('%m/%d')})", quant_html)
    
    # ---------------------------------------------------------
    # 📰 發送第二封信：情資新聞報表 (為三區股票抓取新聞)
    # ---------------------------------------------------------
    print("啟動 Google 新聞爬蟲...")
    news_content = "<h4>📊 第一區：ETF 相關新聞</h4>"
    for ticker, name in STUDENT_ETFS.items():
        news_content += f"<p><b>{name}</b></p><ul>{fetch_google_news(name)}</ul>"
        
    news_content += "<h4>🚨 第二區：持股重大訊息</h4>"
    if not MY_PORTFOLIO:
        news_content += "<p style='color:#9ca3af;'>目前無個股持倉。</p>"
    else:
        for ticker, info in MY_PORTFOLIO.items():
            news_content += f"<p><b>{info['name']}</b></p><ul>{fetch_google_news(info['name'])}</ul>"
            
    news_content += "<h4>🎯 第三區：尋寶名單情資</h4>"
    if final_stocks_df.empty:
        news_content += "<p style='color:#9ca3af;'>今日無尋寶標的，暫無新聞。</p>"
    else:
        for index, row in final_stocks_df.iterrows():
            news_content += f"<p><b>{row['Name']}</b></p><ul>{fetch_google_news(row['Name'])}</ul>"

    news_html = f"""
    <html><body style="font-family: Arial; background-color: #1e1b4b; color: #e5e7eb; padding: 20px;">
        <h2 style="color: #818cf8;">📰 QuantShield 每日情資簡報</h2>
        <div style="background-color: #312e81; padding: 15px; border-radius: 8px;">
            <p>以下為系統針對您雷達中的標的，自動彙整的最新 Google 財經新聞：</p>
            {news_content}
        </div>
    </body></html>
    """
    send_email(SENDER, PASSWORD, SUBSCRIBERS, f"📰 QuantShield 每日情資簡報 ({datetime.now().strftime('%m/%d')})", news_html)
