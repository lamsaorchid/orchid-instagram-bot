import os
import requests
import openai
from flask import Flask, jsonify, request, make_response, redirect, url_for
import threading
import time
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# الإعدادات
# ═══════════════════════════════════════════════════════════
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
PAGE_ID = str(os.environ.get('PAGE_ID', '')).strip()
OPENAI_KEY = os.environ.get('OPENAI_KEY')

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

stats = {
    'total_replies': 0,
    'total_messages': 0,
    'total_comments': 0,
    'last_activity': 'لا يوجد نشاط بعد',
    'recent_activities': [],
    'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'bot_running': True,
    'fb_page_name': 'جاري التحقق...',
    'ig_username': 'جاري التحقق...',
    'openai_status': '⏳ جاري الفحص...',
    'meta_status': '⏳ جاري الفحص...'
}

replied_ids = set()

BUSINESS_CONTEXT = """
أنت مساعد ذكي لمتجر "لمسة أوركيد" (Lamt Orchid) في عدن، اليمن.
🌸 المنتجات: باقات ورد طبيعي وصناعي، تغليف هدايا، توزيعات مناسبات.
📍 الموقع: عدن مول - الدور الأول.
📞 واتساب: 783200063.
✨ أسلوب الرد: ودود، مهني، استخدم إيموجي، اذكر الواتساب (783200063) للطلب.
"""

def get_smart_reply(message_text):
    try:
        if not OPENAI_KEY: return "أهلاً بك في لمسة أوركيد 🌸 واتساب: 783200063"
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": BUSINESS_CONTEXT}, {"role": "user", "content": message_text}],
            max_tokens=150, temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"ChatGPT Error: {e}")
        return "شكراً لتواصلك مع لمسة أوركيد ❤️ واتساب للطلب: 783200063"

# ═══════════════════════════════════════════════════════════
# وظائف الفحص والاتصال
# ═══════════════════════════════════════════════════════════

def check_connections():
    global stats
    try:
        openai.Model.list()
        stats['openai_status'] = '✅ متصل'
    except Exception as e:
        stats['openai_status'] = '❌ خطأ'
        logger.error(f"OpenAI Error: {e}")

    try:
        url = f"https://graph.facebook.com/v21.0/me"
        params = {'fields': 'name,instagram_business_account', 'access_token': PAGE_ACCESS_TOKEN}
        res = requests.get(url, params=params).json()
        if 'name' in res:
            stats['fb_page_name'] = res['name']
            stats['meta_status'] = '✅ متصل'
            if 'instagram_business_account' in res:
                ig_id = res['instagram_business_account']['id']
                ig_url = f"https://graph.facebook.com/v21.0/{ig_id}"
                ig_res = requests.get(ig_url, params={'fields': 'username', 'access_token': PAGE_ACCESS_TOKEN}).json()
                stats['ig_username'] = ig_res.get('username', 'غير مرتبط')
            else:
                stats['ig_username'] = '❌ غير مرتبط'
        else:
            stats['meta_status'] = '❌ توكن خطأ'
    except Exception as e:
        stats['meta_status'] = '❌ خطأ اتصال'
        logger.error(f"Meta Error: {e}")

# ═══════════════════════════════════════════════════════════
# وظائف البوت (Polling Mode)
# ═══════════════════════════════════════════════════════════

def check_updates():
    while True:
        if stats['bot_running'] and PAGE_ACCESS_TOKEN and PAGE_ID:
            try:
                # فحص الرسائل
                conv_url = f"https://graph.facebook.com/v21.0/{PAGE_ID}/conversations"
                res = requests.get(conv_url, params={'access_token': PAGE_ACCESS_TOKEN}).json()
                for conv in res.get('data', []):
                    conv_id = conv['id']
                    m_url = f"https://graph.facebook.com/v21.0/{conv_id}/messages"
                    m_res = requests.get(m_url, params={'fields': 'id,message,from', 'access_token': PAGE_ACCESS_TOKEN}).json()
                    if m_res.get('data'):
                        last_msg = m_res['data'][0]
                        mid = last_msg['id']
                        if mid not in replied_ids and last_msg['from']['id'] != PAGE_ID:
                            text = last_msg.get('message', '')
                            reply = get_smart_reply(text)
                            send_url = f"https://graph.facebook.com/v21.0/{conv_id}/messages"
                            requests.post(send_url, json={'message': reply, 'access_token': PAGE_ACCESS_TOKEN})
                            replied_ids.add(mid)
                            update_stats('رسالة فيسبوك', last_msg['from']['name'], text, reply)

                # فحص التعليقات (Instagram) يتم هنا أيضاً بنفس الطريقة
            except Exception as e:
                logger.error(f"Polling Loop Error: {e}")
        time.sleep(60)

def update_stats(type, user, msg, reply):
    global stats
    if 'رسالة' in type: stats['total_messages'] += 1
    else: stats['total_comments'] += 1
    stats['total_replies'] += 1
    stats['last_activity'] = datetime.now().strftime('%H:%M:%S')
    stats['recent_activities'].insert(0, {'type': type, 'user': user, 'msg': msg, 'reply': reply, 'time': stats['last_activity']})
    stats['recent_activities'] = stats['recent_activities'][:10]

# ═══════════════════════════════════════════════════════════
# Dashboard UI & Controls
# ═══════════════════════════════════════════════════════════

@app.route('/toggle_bot')
def toggle_bot():
    stats['bot_running'] = not stats['bot_running']
    return redirect(url_for('dashboard'))

@app.route('/')
def dashboard():
    check_connections()
    bot_status_class = "status-on" if stats['bot_running'] else "status-off"
    bot_status_text = "يعمل" if stats['bot_running'] else "متوقف"
    bot_btn_text = "إيقاف البوت" if stats['bot_running'] else "تشغيل البوت"

    activities_html = "".join([f"""
        <div style='border-bottom:1px solid #eee; padding:15px; margin-bottom:10px;'>
            <div style='display:flex; justify-content:space-between;'>
                <b>{a['user']}</b> <small style='color:#999;'>{a['time']}</small>
            </div>
            <div style='font-size:14px; color:#555; margin:5px 0;'>📩 {a['msg']}</div>
            <div style='font-size:14px; color:#9b59b6; font-weight:bold;'>🤖 {a['reply']}</div>
        </div>
    """ for a in stats['recent_activities']])

    return f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8"><title>لمسة أوركيد | لوحة التحكم</title>
        <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Tajawal', sans-serif; background: #f8f9fe; margin: 0; padding: 20px; }}
            .container {{ max-width: 1000px; margin: auto; display: grid; grid-template-columns: 1fr 350px; gap: 20px; }}
            .card {{ background: white; border-radius: 15px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }}
            .btn {{ display: block; width: 100%; padding: 12px; border: none; border-radius: 25px; cursor: pointer; text-align: center; text-decoration: none; font-weight: bold; color: white; }}
            .btn-toggle {{ background: linear-gradient(to right, #9b59b6, #e91e63); }}
            .btn-off {{ background: #e74c3c; }}
            .status-circle {{ width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 10px; font-size: 24px; border: 4px solid #eee; }}
            .status-on {{ border-color: #2ecc71; color: #2ecc71; }}
            .status-off {{ border-color: #e74c3c; color: #e74c3c; }}
            .badge {{ background: #e8f5e9; color: #2e7d32; padding: 4px 10px; border-radius: 10px; font-size: 12px; }}
            .err {{ background: #ffebee; color: #c62828; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div>
                <div class="card">
                    <h1 style="color:#9b59b6; margin:0;">🌸 لمسة أوركيد AI</h1>
                    <p style="color:#666;">لوحة تحكم بوت الانستغرام والفيسبوك</p>
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">
                    <div class="card"><h3>الرسائل: {stats['total_messages']}</h3></div>
                    <div class="card"><h3>التعليقات: {stats['total_comments']}</h3></div>
                </div>
                <div class="card">
                    <h3>📊 آخر النشاطات</h3>
                    {activities_html if stats['recent_activities'] else "<p style='color:#ccc; text-align:center;'>لا يوجد نشاط بعد...</p>"}
                </div>
            </div>
            <div>
                <div class="card" style="text-align:center;">
                    <div class="status-circle {bot_status_class}">{ "✔️" if stats['bot_running'] else "✖️" }</div>
                    <h2>البوت {bot_status_text}</h2>
                    <a href="/toggle_bot" class="btn btn-toggle {'btn-off' if stats['bot_running'] else ''}">{bot_btn_text}</a>
                </div>
                <div class="card">
                    <h3>📸 معلومات الربط</h3>
                    <p><b>فيسبوك:</b> {stats['fb_page_name']}</p>
                    <p><b>انستغرام:</b> @{stats['ig_username']}</p>
                    <hr>
                    <p><b>حالة OpenAI:</b> <span class="badge {'err' if '❌' in stats['openai_status'] else ''}">{stats['openai_status']}</span></p>
                    <p><b>حالة Meta:</b> <span class="badge {'err' if '❌' in stats['meta_status'] else ''}">{stats['meta_status']}</span></p>
                </div>
            </div>
        </div>
        <script>setTimeout(() => {{ location.reload(); }}, 30000);</script>
    </body>
    </html>
    """

if __name__ == '__main__':
    threading.Thread(target=check_updates, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
