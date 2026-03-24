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
    'bot_running': True
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
# وظائف البوت (Polling Mode)
# ═══════════════════════════════════════════════════════════

def get_instagram_account():
    try:
        url = f"https://graph.facebook.com/v21.0/{PAGE_ID}"
        params = {'fields': 'instagram_business_account', 'access_token': PAGE_ACCESS_TOKEN}
        res = requests.get(url, params=params).json()
        if 'instagram_business_account' in res:
            return res['instagram_business_account']['id']
    except Exception as e:
        logger.error(f"Error getting IG account: {e}")
    return None

def check_updates():
    ig_acc_id = get_instagram_account()
    while True:
        try:
            # 1. فحص رسائل فيسبوك
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

            # 2. فحص تعليقات انستغرام
            if ig_acc_id:
                media_url = f"https://graph.facebook.com/v21.0/{ig_acc_id}/media"
                res = requests.get(media_url, params={'access_token': PAGE_ACCESS_TOKEN}).json()
                for post in res.get('data', []):
                    c_url = f"https://graph.facebook.com/v21.0/{post['id']}/comments"
                    c_res = requests.get(c_url, params={'fields': 'id,text,from', 'access_token': PAGE_ACCESS_TOKEN}).json()
                    for comment in c_res.get('data', []):
                        if comment['id'] not in replied_ids:
                            text = comment.get('text', '')
                            reply = get_smart_reply(text)
                            r_url = f"https://graph.facebook.com/v21.0/{comment['id']}/replies"
                            requests.post(r_url, data={'message': reply, 'access_token': PAGE_ACCESS_TOKEN})
                            replied_ids.add(comment['id'])
                            update_stats('تعليق انستغرام', comment.get('from',{}).get('username','متابع'), text, reply)

            time.sleep(60)
        except Exception as e:
            logger.error(f"Polling Error: {e}")
            time.sleep(30)

def update_stats(type, user, msg, reply):
    global stats
    if 'رسالة' in type: stats['total_messages'] += 1
    else: stats['total_comments'] += 1
    stats['total_replies'] += 1
    stats['last_activity'] = datetime.now().strftime('%H:%M:%S')
    stats['recent_activities'].insert(0, {'type': type, 'user': user, 'msg': msg, 'reply': reply, 'time': stats['last_activity']})
    stats['recent_activities'] = stats['recent_activities'][:15]

# ═══════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    activities_html = "".join([f"<div style='border-bottom:1px solid #eee; padding:10px;'><b>{a['user']}</b> ({a['type']}): {a['msg']}<br><span style='color:purple;'>🤖 {a['reply']}</span></div>" for a in stats['recent_activities']])
    return f"""
    <html dir="rtl" lang="ar"><body style="font-family:tahoma; padding:20px; background:#f8f9fe;">
        <h1 style="color:#9b59b6;">🌸 لوحة تحكم لمسة أوركيد AI</h1>
        <div style="display:flex; gap:20px;">
            <div style="background:white; padding:20px; border-radius:10px; flex:1;"><h3>الرسائل: {stats['total_messages']}</h3></div>
            <div style="background:white; padding:20px; border-radius:10px; flex:1;"><h3>التعليقات: {stats['total_comments']}</h3></div>
        </div>
        <div style="background:white; padding:20px; border-radius:10px; margin-top:20px;">
            <h3>📋 السجل المباشر:</h3>
            {activities_html if stats['recent_activities'] else "في انتظار النشاط..."}
        </div>
    </body></html>
    """

if __name__ == '__main__':
    threading.Thread(target=check_updates, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
