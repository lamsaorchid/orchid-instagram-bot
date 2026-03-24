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
# جلب التوكن مع التأكد من إزالة أي مسافات زائدة
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'orchid_bot_verify_123').strip()

# ═══════════════════════════════════════════════════════════
# Webhook Verification
# ═══════════════════════════════════════════════════════════

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode == 'subscribe':
            logger.info(f"🔍 محاولة تحقق: التوكن المستلم ({token}) | التوكن المتوقع ({VERIFY_TOKEN})")

            if token == VERIFY_TOKEN:
                logger.info("✅ تم التطابق والتحقق بنجاح!")
                return make_response(challenge, 200)
            else:
                logger.error("❌ فشل التحقق: الكلمتان غير متطابقتين")
                return "Verification Failed", 403

    if request.method == 'POST':
        # معالجة البيانات (نفس الكود السابق)
        return "EVENT_RECEIVED", 200

@app.route('/')
def index():
    return "<h1>Bot is Online</h1>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
