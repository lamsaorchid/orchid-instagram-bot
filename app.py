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
                        # التحقق من وجود المرسل والرسالة معاً
                        if 'sender' in event and 'message' in event:
                            sender_id = str(event['sender']['id'])
                            if sender_id == PAGE_ID: continue

                            if 'text' in event['message']:
                                mid = event['message']['id']
                                if mid not in replied_ids:
                                    msg_text = event['message']['text']
                                    logger.info(f"📩 Message from {sender_id}: {msg_text}")

                                    # توليد وإرسال الرد
                                    reply = get_smart_reply(msg_text)
                                    send_reply(sender_id, reply, data.get('object'))

                                    replied_ids.add(mid)
                                    stats['total_replies'] += 1
                                    update_history('رسالة', sender_id, msg_text, reply)

                # تعليقات انستغرام
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change.get('field') in ['comments', 'comment']:
                            val = change.get('value', {})
                            cid = val.get('id')
                            if cid and cid not in replied_ids:
                                text = val.get('text', '')
                                reply = get_smart_reply(text)
                                send_comment_reply(cid, reply)
                                replied_ids.add(cid)
                                stats['total_replies'] += 1
                                update_history('تعليق', "متابع", text, reply)
    except Exception as e:
        logger.error(f"Error in process_payload: {e}")

def send_reply(recipient_id, text, platform):
    # إرسال الرد حسب المنصة (فيسبوك أو انستغرام)
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    res = requests.post(url, json=payload)
    logger.info(f"📤 Reply sent. Status: {res.status_code}")

def send_comment_reply(comment_id, text):
    url = f"https://graph.facebook.com/v21.0/{comment_id}/replies?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, data={"message": text})

def update_history(type, user, msg, reply):
    global stats
    stats['last_activity'] = datetime.now().strftime('%H:%M:%S')
    stats['recent_activities'].insert(0, {
        'type': type, 'user': user, 'msg': msg, 'reply': reply, 'time': stats['last_activity']
    })
    stats['recent_activities'] = stats['recent_activities'][:10]

# ═══════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    activities_html = "".join([f"""
        <div style="border-bottom: 1px solid #eee; padding: 10px;">
            <b>{a['user']}</b>: {a['msg']} <br>
            <span style="color:blue;">🤖 {a['reply']}</span>
        </div>
    """ for a in stats['recent_activities']])

    return f"""
    <html dir="rtl" lang="ar"><body style="font-family:tahoma; padding:20px;">
        <h1>🌸 لوحة تحكم لمسة أوركيد AI</h1>
        <p>إجمالي الردود: {stats['total_replies']}</p>
        <p>آخر نشاط: {stats['last_activity']}</p>
        <hr>
        <h3>آخر العمليات:</h3>
        {activities_html if stats['recent_activities'] else "في انتظار الرسائل..."}
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
