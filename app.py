import os
import requests
import openai
from flask import Flask, jsonify, request, make_response
import threading
import time
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# الإعدادات
# ═══════════════════════════════════════════════════════════
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
PAGE_ID = os.environ.get('PAGE_ID')
OPENAI_KEY = os.environ.get('OPENAI_KEY')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'orchid_bot_verify_123').strip()

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

# ═══════════════════════════════════════════════════════════
# إحصائيات النظام (تخزين مؤقت في الذاكرة)
# ═══════════════════════════════════════════════════════════
stats = {
    'total_comments_replied': 0,
    'total_messages_replied': 0,
    'last_activity': 'لا يوجد نشاط بعد',
    'recent_activities': [],
    'bot_status': '✅ متصل ويعمل بنظام الويب هوك',
    'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}

replied_ids = set() # لمنع تكرار الردود

# ═══════════════════════════════════════════════════════════
# سياق العمل (ChatGPT Prompt)
# ═══════════════════════════════════════════════════════════
BUSINESS_CONTEXT = """
أنت مساعد ذكي لمتجر "لمسة أوركيد" (Lamt Orchid) في عدن، اليمن.
🌸 المنتجات: باقات ورد طبيعي وصناعي، تغليف هدايا، توزيعات مناسبات.
📍 الموقع: عدن مول - الدور الأول.
📞 واتساب: 783200063.
✨ أسلوب الرد: ودود، مهني، استخدم إيموجي، اذكر الواتساب للطلب.
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
# Webhook Handling
# ═══════════════════════════════════════════════════════════

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return make_response(challenge, 200)
        return "Forbidden", 403

    if request.method == 'POST':
        data = request.json
        threading.Thread(target=process_payload, args=(data,)).start()
        return "EVENT_RECEIVED", 200

def process_payload(data):
    global stats
    try:
        if 'entry' in data:
            for entry in data['entry']:
                # رسائل فيسبوك/انستغرام
                if 'messaging' in entry:
                    for event in entry['messaging']:
                        sender_id = event['sender']['id']
                        if sender_id == PAGE_ID: continue
                        if 'message' in event and 'text' in event['message']:
                            mid = event['message']['id']
                            if mid not in replied_ids:
                                text = event['message']['text']
                                reply = get_smart_reply(text)
                                send_fb_message(sender_id, reply)
                                replied_ids.add(mid)
                                update_stats('رسالة', sender_id, text, reply)

                # تعليقات انستغرام
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change['field'] == 'comments':
                            cid = change['value']['id']
                            if cid not in replied_ids:
                                text = change['value']['text']
                                reply = get_smart_reply(text)
                                send_ig_reply(cid, reply)
                                replied_ids.add(cid)
                                update_stats('تعليق انستغرام', "متابع", text, reply)
    except Exception as e:
        logger.error(f"Payload Error: {e}")

def send_fb_message(rid, text):
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": rid}, "message": {"text": text}})

def send_ig_reply(cid, text):
    url = f"https://graph.facebook.com/v21.0/{cid}/replies?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, data={"message": text})

def update_stats(type, user, msg, reply):
    global stats
    if 'رسالة' in type: stats['total_messages_replied'] += 1
    else: stats['total_comments_replied'] += 1
    stats['last_activity'] = datetime.now().strftime('%H:%M:%S')
    stats['recent_activities'].insert(0, {
        'type': type, 'user': user, 'msg': msg[:50], 'reply': reply[:50], 'time': stats['last_activity']
    })
    stats['recent_activities'] = stats['recent_activities'][:15]

# ═══════════════════════════════════════════════════════════
# Dashboard UI
# ═══════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    activities_html = "".join([f"""
        <div style="border-bottom: 1px solid #eee; padding: 10px; margin-bottom: 5px;">
            <span style="background: #667eea; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{a['type']}</span>
            <strong style="color: #444;"> {a['user']}</strong> <small style="float: left; color: #999;">{a['time']}</small>
            <div style="color: #666; margin-top: 5px;">📩 {a['msg']}</div>
            <div style="color: #667eea; font-weight: bold; margin-top: 3px;">🤖 {a['reply']}</div>
        </div>
    """ for a in stats['recent_activities']])

    html = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>لوحة تحكم لمسة أوركيد</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma; background: #f0f2f5; margin: 0; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            .header {{ text-align: center; color: #667eea; border-bottom: 2px solid #f0f2f5; padding-bottom: 15px; }}
            .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
            .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 10px; text-align: center; border: 1px solid #eee; }}
            .stat-val {{ font-size: 28px; font-weight: bold; color: #667eea; }}
            .status {{ background: #e8f5e9; color: #2e7d32; padding: 10px; border-radius: 8px; text-align: center; font-weight: bold; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <h1>🌸 لمسة أوركيد - بوت الذكاء الاصطناعي</h1>
                <p>تاريخ بدء التشغيل: {stats['start_time']}</p>
            </div>
            <div class="status">{stats['bot_status']}</div>
            <div class="stats-grid">
                <div class="card stat-box">
                    <div style="color: #666;">إجمالي ردود الرسائل</div>
                    <div class="stat-val">{stats['total_messages_replied']}</div>
                </div>
                <div class="card stat-box">
                    <div style="color: #666;">إجمالي ردود التعليقات</div>
                    <div class="stat-val">{stats['total_comments_replied']}</div>
                </div>
            </div>
            <div class="card">
                <h3>📋 آخر النشاطات (تحديث تلقائي)</h3>
                {activities_html if stats['recent_activities'] else '<p style="text-align:center; color:#999;">في انتظار أول تفاعل من الزبائن... 🤖</p>'}
            </div>
            <p style="text-align: center; font-size: 12px; color: #999;">آخر تحديث: {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
    </body>
    </html>
    """
    return html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
