import os
import requests
import openai
from flask import Flask, jsonify
import threading
import time
from datetime import datetime
import logging
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env إذا كان موجوداً (للتطوير المحلي)
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# الإعدادات - يتم جلبها من متغيرات البيئة للأمان
# ═══════════════════════════════════════════════════════════
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
PAGE_ID = os.environ.get('PAGE_ID')
OPENAI_KEY = os.environ.get('OPENAI_KEY')

# متغيرات Instagram (سيتم جلبها تلقائياً من الصفحة)
INSTAGRAM_ACCOUNT_ID = None

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY
    logger.info("✅ OpenAI API Key تم تحميله بنجاح")
else:
    logger.warning("⚠️ OpenAI API Key غير موجود - سيتم استخدام الردود الافتراضية")

# ═══════════════════════════════════════════════════════════
# سياق العمل (ChatGPT Prompt)
# ═══════════════════════════════════════════════════════════
BUSINESS_CONTEXT = """
أنت مساعد ذكي لمتجر "لمسة أوركيد" (Lamt Orchid) في عدن، اليمن.

🌸 المنتجات والخدمات:
- باقات ورد طبيعي (جوري، بيبي روز، ورد مستورد)
- باقات ورد صناعي (جودة عالية)
- تنسيقات ورد للمناسبات (أعياد، أعراس، تخرج، خطوبة)
- تغليف هدايا فاخر
- منتجات أكريليك مخصصة
- توزيعات المناسبات
- بوكسات ورد فاخرة

📍 معلومات التواصل:
- الموقع: عدن - عدن مول - الدور الأول
- واتساب للطلب: 783200063
- ساعات العمل: 9 صباحاً - 9 مساءً يومياً
- الحساب: @lamst_orchid

📦 التوصيل:
- نوصل لجميع مناطق عدن
- التوصيل خلال 24 ساعة
- إمكانية التوصيل الفوري (حسب المنطقة)

✨ أسلوب الرد:
- كن ودوداً ومحترفاً جداً
- استخدم إيموجي مناسبة (🌸❤️🌹✨🎁)
- رد بإيجاز (2-4 أسطر فقط)
- اذكر رقم الواتساب (783200063) عند الحاجة للطلب
- إذا سأل عن منتج غير متوفر، اقترح بديلاً مشابهاً
- إذا كان الكومنت مجرد إعجاب، اشكره بلطف

مهم جداً: إذا سأل عن الأسعار بالتحديد، انصحه بالتواصل واتساب (783200063) لمعرفة السعر الدقيق لكل تنسيق.
"""

# ═══════════════════════════════════════════════════════════
# إحصائيات النظام
# ═══════════════════════════════════════════════════════════
replied_comments = set()
replied_messages = set()
stats = {
    'total_comments_replied': 0,
    'total_messages_replied': 0,
    'last_activity': 'لا يوجد نشاط بعد',
    'bot_status': '⏳ جاري بدء التشغيل...',
    'recent_activities': [],
    'bot_started': False,
    'instagram_username': 'lamst_orchid',
    'page_name': 'لمسة أوركيد'
}

# ═══════════════════════════════════════════════════════════
# دالة جلب Instagram Account من صفحة Facebook
# ═══════════════════════════════════════════════════════════
def get_instagram_account():
    """جلب حساب Instagram المربوط بصفحة Facebook"""
    global INSTAGRAM_ACCOUNT_ID
    
    if not PAGE_ID or not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ID أو PAGE_ACCESS_TOKEN غير معرف")
        return False

    try:
        logger.info("🔍 جلب حساب Instagram من صفحة Facebook...")
        
        url = f"https://graph.facebook.com/v21.0/{PAGE_ID}"
        params = {
            'fields': 'instagram_business_account,name',
            'access_token': PAGE_ACCESS_TOKEN
        }
        
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if 'error' in data:
            logger.error(f"❌ خطأ في جلب Instagram Account: {data['error']}")
            return False
        
        if 'instagram_business_account' in data:
            INSTAGRAM_ACCOUNT_ID = data['instagram_business_account']['id']
            stats['page_name'] = data.get('name', 'لمسة أوركيد')
            logger.info(f"✅ تم ربط Instagram Account: {INSTAGRAM_ACCOUNT_ID}")
            
            # جلب اسم المستخدم على Instagram
            ig_url = f"https://graph.facebook.com/v21.0/{INSTAGRAM_ACCOUNT_ID}"
            ig_params = {
                'fields': 'username,followers_count',
                'access_token': PAGE_ACCESS_TOKEN
            }
            ig_response = requests.get(ig_url, params=ig_params, timeout=15)
            ig_data = ig_response.json()
            
            if 'username' in ig_data:
                stats['instagram_username'] = ig_data['username']
                logger.info(f"✅ Instagram Username: @{ig_data['username']}")
            
            return True
        else:
            logger.error("❌ لا يوجد حساب Instagram مربوط بهذه الصفحة")
            return False
            
    except Exception as e:
        logger.error(f"❌ خطأ في جلب Instagram Account: {e}")
        return False

# ═══════════════════════════════════════════════════════════
# وظائف البوت
# ═══════════════════════════════════════════════════════════

def get_smart_reply(message_text):
    """توليد رد ذكي باستخدام ChatGPT"""
    try:
        if not OPENAI_KEY:
            return "أهلاً بك في لمسة أوركيد 🌸\nللطلب والاستفسار تواصل معنا واتساب: 783200063"
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": BUSINESS_CONTEXT},
                {"role": "user", "content": message_text}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ ChatGPT Error: {e}")
        return "شكراً لتواصلك مع لمسة أوركيد ❤️\nللطلب أو الاستفسار عن الأسعار، يسعدنا تواصلك واتساب: 783200063"

def instagram_comments_bot():
    """مراقبة كومنتات Instagram عبر Facebook Page"""
    global stats
    
    logger.info("=" * 70)
    logger.info("🚀 بوت كومنتات Instagram بدأ العمل (عبر Facebook Page)...")
    logger.info(f"📄 Facebook Page ID: {PAGE_ID}")
    logger.info(f"🔑 Token Status: {'✅ موجود' if PAGE_ACCESS_TOKEN else '❌ غير موجود'}")
    logger.info(f"🤖 OpenAI Status: {'✅ مفعّل' if OPENAI_KEY else '❌ معطّل'}")
    logger.info("=" * 70)
    
    # جلب Instagram Account أولاً
    if not get_instagram_account():
        logger.error("❌ فشل الحصول على Instagram Account - البوت متوقف")
        stats['bot_status'] = '❌ فشل ربط Instagram'
        return
    
    stats['bot_started'] = True
    stats['bot_status'] = '✅ البوت يعمل الآن'
    
    while True:
        try:
            # جلب المنشورات من Instagram عبر Facebook Graph API
            logger.info("🔍 جلب منشورات Instagram...")
            
            media_url = f"https://graph.facebook.com/v21.0/{INSTAGRAM_ACCOUNT_ID}/media"
            media_params = {
                'fields': 'id,caption,media_type,permalink',
                'limit': 10,
                'access_token': PAGE_ACCESS_TOKEN
            }
            
            media_response = requests.get(media_url, params=media_params, timeout=20)
            
            if media_response.status_code != 200:
                logger.error(f"❌ خطأ في جلب المنشورات: {media_response.status_code}")
                logger.error(f"الاستجابة: {media_response.text}")
                stats['bot_status'] = f'⚠️ خطأ في الاتصال: {media_response.status_code}'
                time.sleep(120)
                continue
            
            media_data = media_response.json()
            
            if 'error' in media_data:
                logger.error(f"❌ خطأ من API: {media_data['error']}")
                stats['bot_status'] = f"❌ {media_data['error'].get('message', 'خطأ غير معروف')[:40]}"
                time.sleep(120)
                continue
            
            posts = media_data.get('data', [])
            logger.info(f"✅ تم جلب {len(posts)} منشورات")
            
            for post in posts:
                post_id = post['id']
                caption = post.get('caption', 'بدون وصف')[:50]
                
                # جلب الكومنتات
                comments_url = f"https://graph.facebook.com/v21.0/{post_id}/comments"
                comments_params = {
                    'fields': 'id,text,username,from',
                    'access_token': PAGE_ACCESS_TOKEN
                }
                
                comments_response = requests.get(comments_url, params=comments_params, timeout=20)
                
                if comments_response.status_code != 200:
                    continue
                
                comments = comments_response.json().get('data', [])
                
                if comments:
                    logger.info(f"💬 وُجد {len(comments)} كومنت على المنشور: {caption}")
                
                for comment in comments:
                    cid = comment['id']
                    
                    if cid not in replied_comments:
                        text = comment.get('text', '')
                        user = comment.get('username', comment.get('from', {}).get('name', 'Unknown'))
                        
                        logger.info("=" * 70)
                        logger.info(f"📩 كومنت جديد من @{user}")
                        logger.info(f"💬 النص: {text}")
                        
                        # توليد الرد
                        reply = get_smart_reply(text)
                        logger.info(f"🤖 الرد المُولّد: {reply}")
                        
                        # إرسال الرد
                        reply_url = f"https://graph.facebook.com/v21.0/{cid}/replies"
                        reply_data = {
                            'message': reply,
                            'access_token': PAGE_ACCESS_TOKEN
                        }
                        
                        res = requests.post(reply_url, data=reply_data, timeout=20)
                        
                        if res.status_code == 200:
                            replied_comments.add(cid)
                            stats['total_comments_replied'] += 1
                            stats['last_activity'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            stats['recent_activities'].insert(0, {
                                'type': 'instagram_comment',
                                'user': user,
                                'message': text[:80],
                                'reply': reply[:80],
                                'time': stats['last_activity']
                            })
                            stats['recent_activities'] = stats['recent_activities'][:30]
                            logger.info("✅ تم إرسال الرد بنجاح!")
                            logger.info("=" * 70)
                        else:
                            logger.error(f"❌ فشل إرسال الرد: {res.status_code}")
                            logger.error(f"الاستجابة: {res.text}")
            
            stats['bot_status'] = f'✅ نشط - يراقب {len(posts)} منشورات'
            logger.info(f"⏳ انتظار 60 ثانية...")
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"❌ خطأ في البوت: {e}", exc_info=True)
            stats['bot_status'] = f'⚠️ خطأ: {str(e)[:40]}'
            time.sleep(120)

def facebook_messages_bot():
    """مراقبة الرسائل الخاصة على Facebook Page"""
    global stats
    
    if not PAGE_ID:
        logger.error("❌ PAGE_ID غير معرف")
        return

    logger.info("🚀 بوت الرسائل الخاصة بدأ العمل...")
    time.sleep(15)  # انتظار قليلاً قبل البدء
    
    while True:
        try:
            # جلب المحادثات
            conversations_url = f"https://graph.facebook.com/v21.0/{PAGE_ID}/conversations"
            conversations_params = {
                'fields': 'id,updated_time',
                'access_token': PAGE_ACCESS_TOKEN
            }
            
            conversations_response = requests.get(
                conversations_url,
                params=conversations_params,
                timeout=20
            )
            
            if conversations_response.status_code != 200:
                time.sleep(120)
                continue
            
            conversations = conversations_response.json().get('data', [])
            
            for conv in conversations:
                conv_id = conv['id']
                
                # جلب الرسائل
                messages_url = f"https://graph.facebook.com/v21.0/{conv_id}/messages"
                messages_params = {
                    'fields': 'id,message,from,created_time',
                    'limit': 5,
                    'access_token': PAGE_ACCESS_TOKEN
                }
                
                messages_response = requests.get(
                    messages_url,
                    params=messages_params,
                    timeout=20
                )
                
                if messages_response.status_code != 200:
                    continue
                
                messages = messages_response.json().get('data', [])
                
                for msg in messages:
                    msg_id = msg['id']
                    
                    # التأكد من أن الرسالة ليست من الصفحة نفسها
                    if msg_id not in replied_messages and msg.get('from', {}).get('id') != PAGE_ID:
                        message_text = msg.get('message', '')
                        sender_name = msg.get('from', {}).get('name', 'Unknown')
                        
                        if message_text:
                            logger.info(f"\n💬 رسالة جديدة من {sender_name}")
                            logger.info(f"   النص: {message_text[:80]}")
                            
                            # توليد الرد
                            reply = get_smart_reply(message_text)
                            logger.info(f"🤖 الرد: {reply[:50]}")
                            
                            # إرسال الرد
                            reply_url = f"https://graph.facebook.com/v21.0/{conv_id}/messages"
                            reply_data = {
                                'message': reply,
                                'access_token': PAGE_ACCESS_TOKEN
                            }
                            
                            res = requests.post(reply_url, json=reply_data, timeout=20)
                            
                            if res.status_code == 200:
                                replied_messages.add(msg_id)
                                stats['total_messages_replied'] += 1
                                stats['last_activity'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                stats['recent_activities'].insert(0, {
                                    'type': 'facebook_message',
                                    'user': sender_name,
                                    'message': message_text[:80],
                                    'reply': reply[:80],
                                    'time': stats['last_activity']
                                })
                                stats['recent_activities'] = stats['recent_activities'][:30]
                                logger.info("✅ تم الرد بنجاح!")
                            else:
                                logger.error(f"❌ فشل الرد: {res.status_code}")
            
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"❌ خطأ في بوت الرسائل: {e}")
            time.sleep(120)

# دالة لتشغيل البوت مع إعادة المحاولة في حال الخطأ
def run_bot_with_retry(target_function, bot_name):
    while True:
        try:
            target_function()
        except Exception as e:
            logger.error(f"❌ تعطل {bot_name}: {e}")
            logger.info(f"🔄 إعادة تشغيل {bot_name} خلال 30 ثانية...")
            time.sleep(30)

# ═══════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    html = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🌸 لمسة أوركيد</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   padding: 20px; min-height: 100vh; margin: 0; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .card {{ background: white; border-radius: 15px; padding: 25px; 
                     box-shadow: 0 8px 25px rgba(0,0,0,0.2); margin-bottom: 25px; }}
            .header {{ text-align: center; border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 20px; }}
            .header h1 {{ color: #667eea; margin: 0 0 10px 0; font-size: 28px; }}
            .status-bar {{ background: {'#e8f5e9' if stats['bot_started'] else '#ffebee'}; 
                          color: {'#2e7d32' if stats['bot_started'] else '#c62828'}; 
                          padding: 15px; border-radius: 10px; text-align: center; 
                          font-weight: bold; margin: 15px 0; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); 
                          gap: 15px; margin: 20px 0; }}
            .stat-box {{ background: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; }}
            .stat-num {{ font-size: 36px; font-weight: bold; color: #667eea; margin: 10px 0; }}
            .stat-label {{ color: #666; font-size: 14px; }}
            .activity-item {{ border-bottom: 1px solid #eee; padding: 12px 0; }}
            .activity-item:last-child {{ border-bottom: none; }}
            .type-badge {{ background: #667eea; color: white; padding: 3px 10px; 
                          border-radius: 5px; font-size: 12px; font-weight: bold; }}
            .type-badge.msg {{ background: #9c27b0; }}
            .user-name {{ font-weight: bold; color: #667eea; margin: 0 5px; }}
            .time-stamp {{ float: left; color: #999; font-size: 12px; }}
            .message-box {{ background: #f5f5f5; padding: 8px; border-radius: 8px; margin: 5px 0; color: #555; }}
            .reply-box {{ background: #e8eaf6; padding: 8px; border-radius: 8px; margin: 5px 0; 
                         color: #667eea; font-weight: bold; }}
            .empty-state {{ text-align: center; color: #999; padding: 40px; font-size: 16px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <h1>🌸 لوحة تحكم لمسة أوركيد الذكية</h1>
                <p style="color: #666; margin: 5px 0;">
                    📘 صفحة Facebook: {stats['page_name']} • 
                    📸 Instagram: @{stats['instagram_username']}
                </p>
                <div class="status-bar">{stats['bot_status']}</div>
            </div>

            <div class="stats-grid">
                <div class="card stat-box">
                    <div class="stat-label">💬 ردود Instagram</div>
                    <div class="stat-num">{stats['total_comments_replied']}</div>
                </div>
                <div class="card stat-box">
                    <div class="stat-label">📨 ردود Facebook</div>
                    <div class="stat-num">{stats['total_messages_replied']}</div>
                </div>
                <div class="card stat-box">
                    <div class="stat-label">⏰ آخر نشاط</div>
                    <div class="stat-num" style="font-size: 18px;">{stats['last_activity']}</div>
                </div>
            </div>

            <div class="card">
                <h2 style="color: #667eea; margin-bottom: 15px;">📋 آخر النشاطات</h2>
                {''.join([f'''
                <div class="activity-item">
                    <span class="type-badge {'msg' if a['type'] == 'facebook_message' else ''}">{
                        '💬 Instagram' if a['type'] == 'instagram_comment' else '📨 Facebook'
                    }</span>
                    <span class="user-name">{a['user']}</span>
                    <span class="time-stamp">{a['time']}</span>
                    <div class="message-box">📩 {a['message']}</div>
                    <div class="reply-box">🤖 {a['reply']}</div>
                </div>
                ''' for a in stats['recent_activities']]) if stats['recent_activities'] else 
                '<div class="empty-state">⏳ لا توجد نشاطات حالياً...<br>البوت ينتظر الكومنتات والرسائل الجديدة 🤖</div>'}
            </div>
            
            <div style="text-align: center; color: white; margin-top: 20px; opacity: 0.9; font-size: 14px;">
                التحديث التلقائي كل 30 ثانية • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'bot_running': stats['bot_started'],
        'instagram_account_id': INSTAGRAM_ACCOUNT_ID,
        'total_instagram_replies': stats['total_comments_replied'],
        'total_facebook_replies': stats['total_messages_replied']
    })

# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    logger.info("🚀 بدء تشغيل نظام لمسة أوركيد الذكي (Facebook Page Mode)")
    
    # تشغيل البوتات في الخلفية مع ميزة إعادة المحاولة
    threading.Thread(target=run_bot_with_retry, args=(instagram_comments_bot, "بوت كومنتات انستغرام"), daemon=True).start()
    threading.Thread(target=run_bot_with_retry, args=(facebook_messages_bot, "بوت رسائل فيسبوك"), daemon=True).start()
    
    # تشغيل السيرفر
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
