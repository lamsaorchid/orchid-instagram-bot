import os
import requests
import openai
from flask import Flask, jsonify, request, make_response
import threading
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
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'orchid_bot_verify_123').strip()

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

stats = {
    'total_replies': 0,
    'last_activity': 'لا يوجد نشاط بعد',
    'recent_activities': [],
    'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}

replied_ids = set()

# ═══════════════════════════════════════════════════════════
# دالة فحص التوكن (للإصلاح)
# ═══════════════════════════════════════════════════════════
def check_token_health():
    if not PAGE_ACCESS_TOKEN:
        return {"status": "❌ مفقود", "msg": "لم يتم ضبط PAGE_ACCESS_TOKEN في Render"}

    url = f"https://graph.facebook.com/v21.0/me?fields=id,name&access_token={PAGE_ACCESS_TOKEN}"
    try:
        res = requests.get(url)
        data = res.json()
        if 'error' in data:
            return {"status": "❌ غير صالح", "msg": data['error'].get('message')}

        # فحص الأذونات
        debug_url = f"https://graph.facebook.com/debug_token?input_token={PAGE_ACCESS_TOKEN}&access_token={PAGE_ACCESS_TOKEN}"
        # ملاحظة: فحص التوكن يحتاج App Token عادة، لكن سنكتفي بمعلومات الحساب الأساسية

        return {
            "status": "✅ صالح",
            "name": data.get('name'),
            "id": data.get('id'),
            "msg": "التوكن يعمل بشكل سليم ويرتبط بـ " + data.get('name')
        }
    except Exception as e:
        return {"status": "⚠️ خطأ اتصال", "msg": str(e)}

# ═══════════════════════════════════════════════════════════
# Webhook Handling
# ═══════════════════════════════════════════════════════════

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return make_response(str(challenge), 200)
        return "Forbidden", 403

    if request.method == 'POST':
        data = request.json
        logger.info(f"📥 Payload Received: {data}")
        threading.Thread(target=process_payload, args=(data,)).start()
        return "EVENT_RECEIVED", 200

def process_payload(data):
    global stats
    try:
        if 'entry' in data:
            for entry in data['entry']:
                # رسائل مسنجر وانستغرام
                if 'messaging' in entry:
                    for event in entry['messaging']:
                        sid = str(event['sender']['id'])
                        if sid == PAGE_ID: continue

                        if 'message' in event and 'text' in event['message']:
                            mid = event['message']['id']
                            if mid not in replied_ids:
                                msg_text = event['message']['text']
                                logger.info(f"💬 Message from {sid}: {msg_text}")
                                # (هنا يتم استدعاء OpenAI وإرسال الرد)
                                # للتبسيط سنزيد العداد فقط في هذا الفحص
                                stats['total_replies'] += 1
                                update_history('رسالة', sid, msg_text)

                # تعليقات انستغرام
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change.get('field') in ['comments', 'comment']:
                            val = change.get('value', {})
                            cid = val.get('id')
                            if cid and cid not in replied_ids:
                                update_history('تعليق', "متابع", val.get('text', ''))
    except Exception as e:
        logger.error(f"Error: {e}")

def update_history(type, user, msg):
    global stats
    stats['last_activity'] = datetime.now().strftime('%H:%M:%S')
    stats['recent_activities'].insert(0, {'type': type, 'user': user, 'msg': msg, 'time': stats['last_activity']})
    stats['recent_activities'] = stats['recent_activities'][:10]

# ═══════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    health = check_token_health()
    id_match = "✅ متطابق" if health.get('id') == PAGE_ID else f"❌ غير متطابق (المتوقع: {health.get('id')})"

    return f"""
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><style>
        body{{font-family:tahoma; padding:20px; background:#f4f4f4;}}
        .status-card {{background:white; padding:15px; border-radius:8px; box-shadow:0 2px 5px rgba(0,0,0,0.1); margin-bottom:10px;}}
        .ok {{color:green; font-weight:bold;}}
        .err {{color:red; font-weight:bold;}}
    </style></head>
    <body>
        <h1>🌸 فحص نظام لمسة أوركيد</h1>
        <div class="status-card">
            <h3>🔍 فحص الإعدادات السرية:</h3>
            <p>حالة التوكن: <span class="{'ok' if '✅' in health['status'] else 'err'}">{health['status']}</span></p>
            <p>التوكن يرتبط بـ: <b>{health.get('name', 'N/A')}</b></p>
            <p>رسالة النظام: {health['msg']}</p>
            <hr>
            <p>مطابقة الـ PAGE_ID: {id_match}</p>
            <p>الـ ID الحالي في Render: <code>{PAGE_ID}</code></p>
        </div>

        <div class="status-card">
            <h3>📊 النشاط الحالي:</h3>
            <p>إجمالي الردود: {stats['total_replies']}</p>
            <p>آخر نشاط: {stats['last_activity']}</p>
        </div>

        <div class="status-card">
            <h3>🛠️ خطوات الإصلاح إذا لم يعمل:</h3>
            <ol>
                <li>تأكد أن الـ ID في Render هو: <b>{health.get('id', PAGE_ID)}</b></li>
                <li>تأكد من الضغط على <b>Subscribe</b> في Meta Developers لكل من (messages, comments).</li>
                <li>تأكد أن التطبيق في وضع <b>Live Mode</b>.</li>
            </ol>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
