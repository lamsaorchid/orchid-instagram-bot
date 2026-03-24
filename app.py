import os
import requests
import openai
from flask import Flask, jsonify, request, make_response
import threading
import time
from datetime import datetime
import logging
from dotenv import load_dotenv

# تحميل المتغيرات
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
# القيمة الافتراضية إذا لم يتم ضبطها في Render
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'orchid_bot_verify_123')

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

# ═══════════════════════════════════════════════════════════
# إحصائيات النظام
# ═══════════════════════════════════════════════════════════
replied_comments = set()
replied_messages = set()
stats = {
    'total_comments_replied': 0,
    'total_messages_replied': 0,
    'last_activity': 'لا يوجد نشاط بعد',
    'bot_status': '✅ يعمل بنظام الويب هوك',
    'recent_activities': [],
    'bot_started': True,
    'instagram_username': 'lamst_orchid',
    'page_name': 'لمسة أوركيد'
}

# ═══════════════════════════════════════════════════════════
# الردود الذكية (ChatGPT)
# ═══════════════════════════════════════════════════════════
BUSINESS_CONTEXT = """أنت مساعد ذكي لمتجر "لمسة أوركيد" في عدن...""" # ضع السياق الكامل هنا

def get_smart_reply(message_text):
    try:
        if not OPENAI_KEY:
            return "أهلاً بك في لمسة أوركيد 🌸\nللطلب والاستفسار تواصل معنا واتساب: 783200063"
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": BUSINESS_CONTEXT}, {"role": "user", "content": message_text}],
            max_tokens=150, temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return "شكراً لتواصلك مع لمسة أوركيد ❤️\nواتساب للطلب: 783200063"

# ═══════════════════════════════════════════════════════════
# Webhook Verification & Handling
# ═══════════════════════════════════════════════════════════

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # التحقق من الويب هوك (Meta Verification)
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("✅ Webhook Verified Successfully!")
            # يجب إرجاع الـ challenge كنص خالص (Plain Text)
            return make_response(challenge, 200)
        else:
            logger.error(f"❌ Verification Failed. Token Mismatch: {token}")
            return "Verification Failed", 403

    # استقبال الأحداث (Events)
    if request.method == 'POST':
        data = request.json
        # تشغيل المعالجة في الخلفية
        threading.Thread(target=process_event, args=(data,)).start()
        return "EVENT_RECEIVED", 200

def process_event(data):
    try:
        if 'entry' in data:
            for entry in data['entry']:
                # التعامل مع الرسائل
                if 'messaging' in entry:
                    for event in entry['messaging']:
                        sender_id = event['sender']['id']
                        if sender_id != PAGE_ID and 'message' in event:
                            text = event['message'].get('text')
                            if text:
                                reply = get_smart_reply(text)
                                send_message(sender_id, reply)
                                update_stats('facebook_message', "الزبون", text, reply)

                # التعامل مع الكومنتات
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change['field'] == 'comments':
                            comment_id = change['value']['id']
                            text = change['value']['text']
                            reply = get_smart_reply(text)
                            send_comment_reply(comment_id, reply)
                            update_stats('instagram_comment', "متابع", text, reply)
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")

def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": recipient_id}, "message": {"text": text}})

def send_comment_reply(comment_id, text):
    url = f"https://graph.facebook.com/v21.0/{comment_id}/replies?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, data={"message": text})

def update_stats(type, user, msg, reply):
    global stats
    stats['total_messages_replied' if 'message' in type else 'total_comments_replied'] += 1
    stats['last_activity'] = datetime.now().strftime('%H:%M:%S')
    stats['recent_activities'].insert(0, {'type': type, 'user': user, 'message': msg[:40], 'reply': reply[:40], 'time': stats['last_activity']})
    stats['recent_activities'] = stats['recent_activities'][:10]

# ═══════════════════════════════════════════════════════════
# Dashboard Route
# ═══════════════════════════════════════════════════════════
@app.route('/')
def dashboard():
    return f"<h1>🌸 Bot Status: {stats['bot_status']}</h1><p>Last Activity: {stats['last_activity']}</p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
