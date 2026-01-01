import logging
import asyncio
import os
import json
import re
import psycopg2
import random
import pytz
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, Filter
from aiogram.types import (
    WebAppInfo, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, 
    Update
)
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

# --- 1. SOZLAMALAR VA LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Muhit o'zgaruvchilari
TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
except:
    ADMIN_ID = 129932291

# Server manzillari
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://test-fzug.onrender.com").rstrip('/')
WEBAPP_URL = f"{RENDER_URL}/static/index.html"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Supabase (5432 port - Barqaror ulanish uchun)
DATABASE_URL = "postgresql://postgres.zvtrujwsydewfcaotwvx:rkbfVJlp96S85bnu@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

# O'zbekiston vaqti
TASHKENT_TZ = pytz.timezone('Asia/Tashkent')

# --- 2. OBYEKTLAR ---
app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- 3. YORDAMCHI FUNKSIYALAR ---
def get_time():
    """Hozirgi O'zbekiston vaqtini qaytaradi"""
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")

def clean(text):
    """HTML teglarini tozalaydi"""
    if not text: return ""
    return re.sub(r'<.*?>', '', str(text)).replace('<', '&lt;').replace('>', '&gt;')

def get_db():
    """Bazaga ulanish"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Jadvallarni yaratish"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS questions (id SERIAL PRIMARY KEY, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, invited_by BIGINT, invite_count INTEGER DEFAULT 0, joined_at TEXT)''')
                conn.commit()
        logger.info("✅ Baza va jadvallar tayyor!")
    except Exception as e:
        logger.error(f"❌ Baza xatosi: {e}")

init_db()

# --- 4. TUGMALAR (KEYBOARDS) ---

# Admin Menyusi
admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Testlar"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📤 Test Yuklash"), KeyboardButton(text="🏆 Reyting Ko'rish")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Foydalanuvchi Menyusi
def get_user_kb(is_allowed: bool):
    buttons = []
    if is_allowed:
        buttons.append([KeyboardButton(text="📝 Testni Boshlash")])
    buttons.append([KeyboardButton(text="🚀 Do'stlarni Taklif Qilish"), KeyboardButton(text="👤 Profilim")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Testga kirish (Inline)
webapp_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Testni Yechish ✍️", web_app=WebAppInfo(url=WEBAPP_URL))]
])

# --- 5. FASTAPI (WEBHOOK & BACKEND) ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"status": "🚀 Bot O'zbekiston vaqtida ishlayapti!", "time": get_time()}

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False}

@app.get("/get_test/{code}")
async def get_test(code: str):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, duration FROM tests WHERE code=%s", (code.strip(),))
                test = cur.fetchone()
                if not test: return {"error": "Test topilmadi"}
                
                cur.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=%s", (code.strip(),))
                rows = cur.fetchall()
                
                questions = [{"q": r[0], "o": random.sample(json.loads(r[1]), len(json.loads(r[1]))), "a": r[2]} for r in rows]
                random.shuffle(questions)
                return {"title": test[0], "time": test[1], "questions": questions}
    except Exception as e: return {"error": str(e)}

@app.post("/submit_result")
async def submit(request: Request):
    try:
        d = await request.json()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (d.get('user_id'), clean(d.get('user_name')), d.get('nickname'), d.get('code'), d.get('title'), d.get('score'), d.get('total'), get_time()))
                conn.commit()
        
        # Adminga xabar
        await bot.send_message(ADMIN_ID, f"🏆 <b>YANGI NATIJA</b>\n\n👤 {clean(d.get('user_name'))}\n📚 {clean(d.get('title'))}\n🎯 {d.get('score')} / {d.get('total')}\n⏰ {get_time()}", parse_mode="HTML")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Save Result Error: {e}")
        return {"status": "error"}

# --- 6. BOT HANDLERLARI (ADMIN) ---

# Admin ekanligini tekshirish filtri
class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == ADMIN_ID

@dp.message(Command("admin"))
@dp.message(F.text == "/panel")
async def admin_panel(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("👑 <b>Admin Panelga Xush Kelibsiz!</b>\nQuyidagi tugmalardan foydalaning:", reply_markup=admin_kb, parse_mode="HTML")

@dp.message(IsAdmin(), F.text == "📋 Testlar")
async def admin_tests(msg: types.Message):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, title, duration FROM tests")
            rows = cur.fetchall()
    
    if rows:
        text = "📂 <b>Bazadagi Testlar:</b>\n\n" + "\n".join([f"🔹 <b>{r[0]}</b> | {r[1]} ({r[2]} daqiqa)" for r in rows])
    else:
        text = "📭 Hozircha testlar yo'q."
    await msg.answer(text, parse_mode="HTML")

@dp.message(IsAdmin(), F.text == "📊 Statistika")
async def admin_stats(msg: types.Message):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            u_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM results")
            r_count = cur.fetchone()[0]
    
    text = (
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{u_count}</b> ta\n"
        f"📝 Yechilgan testlar: <b>{r_count}</b> ta\n"
        f"⏰ Server vaqti: {get_time()}"
    )
    await msg.answer(text, parse_mode="HTML")

@dp.message(IsAdmin(), F.text == "📤 Test Yuklash")
async def admin_upload_info(msg: types.Message):
    text = (
        "📤 <b>Test Yuklash Yo'riqnomasi:</b>\n\n"
        "Testni quyidagi formatda yozib yuboring:\n\n"
        "<code>Kod | Mavzu | Vaqt(daqiqa)\n"
        "1. Savol matni | A javob, B javob, C javob | To'g'ri javob matni\n"
        "2. Keyingi savol...</code>\n\n"
        "<i>Eslatma: Kod takrorlanmasligi kerak!</i>"
    )
    await msg.answer(text, parse_mode="HTML")

@dp.message(IsAdmin(), F.text == "🏆 Reyting Ko'rish")
async def admin_rating_ask(msg: types.Message):
    await msg.answer("Reytingni ko'rish uchun test kodini yozing. Masalan: `/rating 101`")

@dp.message(IsAdmin(), Command("rating"))
async def admin_rating_show(msg: types.Message):
    try: code = msg.text.split()[1]
    except: return await msg.answer("⚠️ Iltimos, kodni kiriting: `/rating 101`")
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_name, score, total, date FROM results WHERE test_code=%s ORDER BY score DESC, date ASC LIMIT 15", (code,))
            rows = cur.fetchall()
    
    if rows:
        res = f"🏆 <b>TOP-15 Reyting ({code}):</b>\n\n" + "\n".join([f"{i+1}. {r[0]} — <b>{r[1]}/{r[2]}</b> <i>({r[3]})</i>" for i, r in enumerate(rows)])
    else:
        res = "❌ Bu kod bo'yicha natijalar topilmadi."
    await msg.answer(res, parse_mode="HTML")

@dp.message(IsAdmin(), F.text.contains("|"))
async def upload_process(msg: types.Message):
    try:
        lines = msg.text.split('\n')
        code, title, time = map(str.strip, lines[0].split('|'))
        
        with get_db() as conn:
            with conn.cursor() as cur:
                # Testni saqlash yoki yangilash
                cur.execute("INSERT INTO tests (code, title, duration) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET title=%s, duration=%s", 
                            (code, title, int(time), title, int(time)))
                # Eski savollarni o'chirish va yangilarini yozish
                cur.execute("DELETE FROM questions WHERE test_code=%s", (code,))
                
                count = 0
                for l in lines[1:]:
                    if '|' in l:
                        parts = list(map(str.strip, l.split('|')))
                        if len(parts) >= 3:
                            q = parts[0]
                            # Raqam bilan boshlansa olib tashlash (1. Savol -> Savol)
                            if '.' in q[:4]: q = q.split('.', 1)[-1].strip()
                            
                            opts = [x.strip() for x in parts[1].split(',')]
                            ans = parts[2]
                            cur.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (%s, %s, %s, %s)", 
                                        (code, q, json.dumps(opts), ans))
                            count += 1
                conn.commit()
        await msg.answer(f"✅ <b>{title}</b> muvaffaqiyatli yuklandi!\n📥 Jami savollar: {count} ta", parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"❌ Yuklashda xatolik bo'ldi:\n{e}")

# --- 7. BOT HANDLERLARI (FOYDALANUVCHI) ---

@dp.message(Command("start"))
async def user_start(msg: types.Message):
    uid = msg.from_user.id
    name = clean(msg.from_user.full_name)
    args = msg.text.split()
    
    # 1. Foydalanuvchini bazaga qo'shish yoki tekshirish
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            
            if not user:
                # Yangi foydalanuvchi
                inviter_id = None
                if len(args) > 1 and args[1].isdigit():
                    potential_inviter = int(args[1])
                    if potential_inviter != uid:
                        inviter_id = potential_inviter
                
                cur.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (%s, %s, 0, %s)", 
                            (uid, inviter_id, get_time()))
                
                # Taklif qilgan odamga ball qo'shish
                if inviter_id:
                    cur.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=%s", (inviter_id,))
                    try: await bot.send_message(inviter_id, f"🎉 <b>Tabriklaymiz!</b>\nDo'stingiz {name} botga qo'shildi. Sizda yana bitta imkoniyat oshdi!", parse_mode="HTML")
                    except: pass
                
                conn.commit()
                # Adminga xabar
                try: await bot.send_message(ADMIN_ID, f"👤 <b>Yangi a'zo:</b> <a href='tg://user?id={uid}'>{name}</a>", parse_mode="HTML")
                except: pass
                count = 0
            else:
                count = user[0]

    # 2. Ruxsatni tekshirish
    is_allowed = (uid == ADMIN_ID) or (count >= 3)
    
    msg_text = f"👋 <b>Assalomu alaykum, {name}!</b>\n\n"
    if is_allowed:
        msg_text += "✅ Sizda test yechish uchun ruxsat bor. Marhamat, boshlashingiz mumkin!"
    else:
        msg_text += (f"⚠️ Testlarni yechish uchun <b>3 ta</b> do'stingizni taklif qilishingiz kerak.\n\n"
                     f"📊 Hozirgi natijangiz: <b>{count} / 3</b> ta\n"
                     f"👇 Quyidagi tugma orqali do'stlaringizni chaqiring!")

    await msg.answer(msg_text, reply_markup=get_user_kb(is_allowed), parse_mode="HTML")

@dp.message(F.text == "📝 Testni Boshlash")
async def start_test_button(msg: types.Message):
    # Qayta tekshirish (xavfsizlik uchun)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (msg.from_user.id,))
            res = cur.fetchone()
            count = res[0] if res else 0
            
    if msg.from_user.id == ADMIN_ID or count >= 3:
        await msg.answer("🧠 <b>Ajoyib!</b> Quyidagi tugmani bosib testni boshlang:", reply_markup=webapp_kb, parse_mode="HTML")
    else:
        await msg.answer("🚫 <b>Ruxsat yo'q!</b> Iltimos, avval 3 ta do'stingizni taklif qiling.")

@dp.message(F.text == "🚀 Do'stlarni Taklif Qilish")
async def invite_friends(msg: types.Message):
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={msg.from_user.id}"
    
    text = (
        "📣 <b>Do'stlarni chaqirish uchun maxsus havolangiz:</b>\n\n"
        f"🔗 <code>{link}</code>\n\n"
        "👆 Shu havolani nusxalab, do'stlaringizga yuboring. Ular start bosishi bilan sizga ball beriladi!"
    )
    
    # Ulashish tugmasi
    share_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Do'stlarga yuborish ↗️", switch_inline_query=f"\nBu bot orqali bilimingni sinab ko'r! Kirish: {link}")]
    ])
    
    await msg.answer(text, reply_markup=share_kb, parse_mode="HTML")

@dp.message(F.text == "👤 Profilim")
async def my_profile(msg: types.Message):
    uid = msg.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count, joined_at FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            if not user: return await msg.answer("Ma'lumot topilmadi.")
            
            # Natijalarni olish
            cur.execute("SELECT test_title, score, total FROM results WHERE user_id=%s ORDER BY id DESC LIMIT 5", (uid,))
            results = cur.fetchall()
            
    res_text = "\n".join([f"▫️ {r[0]}: {r[1]}/{r[2]}" for r in results]) if results else "Hali test yechmagansiz."
    
    text = (
        f"👤 <b>Sizning Profilingiz:</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📅 Qo'shilgan vaqt: {user[1]}\n"
        f"👥 Takliflar: <b>{user[0]}</b> ta\n\n"
        f"📚 <b>Oxirgi natijalar:</b>\n{res_text}"
    )
    await msg.answer(text, parse_mode="HTML")

@dp.message(Command("tanishbilish"))
async def vip_access(msg: types.Message):
    """Faqat test uchun: O'ziga sun'iy 3 ta ball berish"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET invite_count=3 WHERE user_id=%s", (msg.from_user.id,))
            conn.commit()
    await msg.answer("🕵️‍♂️ <b>VIP status faollashtirildi!</b> Endi bemalol test yechishingiz mumkin.", parse_mode="HTML")

# Hamma narsani eshituvchi handler (Bot tirikligini bildirish uchun)
@dp.message(F.text)
async def echo_handler(msg: types.Message):
    # Agar buyruq yoki knopka bo'lmasa
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("Admin, buyruqlardan foydalaning yoki /panel ni bosing.")
    else:
        # Oddiy foydalanuvchiga hech narsa demaymiz yoki yordamchi menyuni qaytaramiz
        pass 

# --- 8. ISHGA TUSHIRISH ---
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"🚀 Webhook o'rnatildi: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("🛑 Bot to'xtatildi")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
