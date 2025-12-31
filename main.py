import logging
import asyncio
import os
import json
import re
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import uvicorn

# ======================================================
# 1. SOZLAMALAR VA KONFIGURATSIYA
# ======================================================

logging.basicConfig(level=logging.INFO)

# Bot Tokeni (Render Environment Variables dan olinadi)
TOKEN = os.getenv("BOT_TOKEN")

# Admin ID (Raqam formatida ekanligini tekshiramiz)
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
except:
    ADMIN_ID = 129932291  # Agar xato bo'lsa, standart ID

# WebApp manzili
WEBAPP_URL = "https://test-fzug.onrender.com/static/index.html"

# ✅ SUPABASE ULANISH HAVOLASI (Port 6543 - Transaction Pooler)
# Bu havola Renderda "Network unreachable" xatosini oldini oladi.
DATABASE_URL = "postgresql://postgres.zvtrujwsydewfcaotwvx:rkbfVJlp96S85bnu@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ======================================================
# 2. YORDAMCHI FUNKSIYALAR
# ======================================================

def clean_html(text):
    """
    Telegram HTML formatidagi xatoliklarni oldini olish uchun.
    < va > belgilarini xavfsiz formatga o'tkazadi va teglarni tozalaydi.
    """
    if not text: return ""
    text = str(text)
    # Barcha mavjud HTML teglarni olib tashlaymiz (xavfsizlik uchun)
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', text)
    # Belgi almashtirish
    return text.replace("<", "&lt;").replace(">", "&gt;")

def get_db_connection():
    """Supabase bazasiga ulanish funksiyasi"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """
    Baza jadvallarini yaratish (PostgreSQL formatida).
    Agar jadvallar mavjud bo'lsa, ularga tegmaydi.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Testlar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tests (
                code TEXT PRIMARY KEY, 
                title TEXT, 
                duration INTEGER
            )
        ''')
        
        # 2. Savollar jadvali (SERIAL - avtomatik ID)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY, 
                test_code TEXT, 
                question TEXT, 
                options TEXT, 
                correct_answer TEXT
            )
        ''')
        
        # 3. Natijalar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY, 
                user_id BIGINT, 
                user_name TEXT, 
                nickname TEXT, 
                test_code TEXT, 
                test_title TEXT, 
                score INTEGER, 
                total INTEGER, 
                date TEXT
            )
        ''')
        
        # 4. Foydalanuvchilar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, 
                invited_by BIGINT, 
                invite_count INTEGER DEFAULT 0, 
                joined_at TEXT
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        logging.info("✅ Baza (Supabase) jadvallari muvaffaqiyatli tekshirildi.")
    except Exception as e:
        logging.error(f"❌ Baza yaratishda xato: {e}")

# Dastur boshlanishida bazani tekshiramiz
init_db()

# ======================================================
# 3. SERVER VA API (FASTAPI)
# ======================================================

# Statik fayllar (index.html, css, js) uchun papka
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    """Server ishlayotganini tekshirish uchun"""
    return {"status": "🚀 Bot va Server Supabase bilan ishlamoqda!"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    """WebApp uchun test savollarini bazadan olib beradi"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Test ma'lumotini olish
        cursor.execute("SELECT title, duration FROM tests WHERE code=%s", (code.strip(),))
        test = cursor.fetchone()
        
        if not test:
            conn.close()
            return {"error": "Bunday kodli test topilmadi! Kodingizni tekshiring."}
        
        # Savollarni olish
        cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=%s", (code.strip(),))
        rows = cursor.fetchall()
        
        questions = []
        for q in rows:
            questions.append({
                "q": q[0], 
                "o": json.loads(q[1]), # JSON formatidan listga o'tkazish
                "a": q[2]
            })
            
        conn.close()
        return {"title": test[0], "time": test[1], "questions": questions}
    except Exception as e:
        logging.error(f"API Xatosi (/get_test): {e}")
        return {"error": "Server xatosi yuz berdi."}

@app.post("/submit_result")
async def submit_result(request: Request):
    """O'quvchi yechgan test natijasini qabul qilish"""
    try:
        data = await request.json()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Bazaga yozish
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get('user_id'), 
            clean_html(data.get('user_name')), 
            data.get('nickname'), 
            data.get('code'), 
            data.get('title'), 
            data.get('score'), 
            data.get('total'), 
            now
        ))
        conn.commit()
        conn.close()
        
        # Adminga chiroyli hisobot yuborish
        report = (
            f"🏆 <b>YANGI NATIJA</b>\n\n"
            f"👤 <b>O'quvchi:</b> {clean_html(data.get('user_name'))}\n"
            f"📝 <b>Test:</b> {clean_html(data.get('title'))}\n"
            f"🔑 <b>Kod:</b> {data.get('code')}\n"
            f"🎯 <b>Natija:</b> {data.get('score')} / {data.get('total')}\n"
            f"📅 <b>Vaqt:</b> {now}"
        )
        await bot.send_message(ADMIN_ID, report, parse_mode="HTML")
        return {"status": "success"}
    except Exception as e:
        logging.error(f"API Xatosi (/submit_result): {e}")
        return {"status": "error"}

# ======================================================
# 4. TELEGRAM BOT KOMANDALARI (AIOGRAM)
# ======================================================

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Botga start bosilganda ishlaydi"""
    user_id = message.from_user.id
    full_name = clean_html(message.from_user.full_name)
    username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    args = message.text.split()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Foydalanuvchi bazada borligini tekshirish
    cursor.execute("SELECT invite_count FROM users WHERE user_id=%s", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        # --- YANGI FOYDALANUVCHI ---
        # Taklif qilgan odamni aniqlash
        invited_by = None
        if len(args) > 1 and args[1].isdigit():
            possible_inviter = int(args[1])
            if possible_inviter != user_id:
                invited_by = possible_inviter

        # Bazaga qo'shish
        cursor.execute(
            "INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (%s, %s, 0, %s)", 
            (user_id, invited_by, now)
        )
        
        # Agar birov orqali kirgan bo'lsa, unga ball berish
        if invited_by:
            cursor.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=%s", (invited_by,))
            try: await bot.send_message(invited_by, "🎉 <b>Tabriklaymiz!</b> Do'stingiz havola orqali botga qo'shildi.", parse_mode="HTML")
            except: pass
            
        conn.commit()
        
        # Adminga yangi a'zo haqida xabar
        admin_msg = (
            f"👤 <b>YANGI FOYDALANUVCHI</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📛 <b>Ism:</b> {full_name}\n"
            f"🔗 <b>Username:</b> {username}\n"
            f"📅 <b>Vaqt:</b> {now}"
        )
        try: await bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
        except: pass
        
        invite_count = 0
    else:
        invite_count = user_data[0]
    
    conn.close()

    # --- JAVOB QAYTARISH MANTIQI ---
    
    # 1. Agar Admin bo'lsa - hamma narsa ochiq
    if user_id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Testni Boshlash (Admin) 📝", web_app=WebAppInfo(url=WEBAPP_URL))
        ]])
        return await message.answer(f"👑 <b>Xush kelibsiz, Admin!</b>\nSizga barcha testlar ochiq.", reply_markup=kb, parse_mode="HTML")

    # 2. Agar takliflar yetarli bo'lsa (3 ta)
    if invite_count >= 3:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))
        ]])
        return await message.answer(f"✅ <b>Tabriklaymiz!</b> Shart bajarildi.\nTestni boshlashingiz mumkin:", reply_markup=kb, parse_mode="HTML")
    
    # 3. Agar shart bajarilmagan bo'lsa
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = (
        f"👋 <b>Assalomu alaykum, {full_name}!</b>\n\n"
        f"Testlarni yechish uchun kamida <b>3 ta</b> do'stingizni taklif qilishingiz kerak.\n\n"
        f"📊 <b>Sizning takliflaringiz:</b> {invite_count} / 3\n\n"
        f"🔗 <b>Sizning shaxsiy havolangiz:</b>\n<code>{ref_link}</code>\n\n"
        f"<i>Havolani do'stlaringizga yuboring!</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Do'stlarga ulashish 🚀", switch_inline_query=f"\nBiologiya testini yechish uchun botga kiring! {ref_link}")
    ]])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("tests"))
async def list_tests(message: types.Message):
    """Admin uchun barcha testlar ro'yxati"""
    if message.from_user.id != ADMIN_ID: return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code, title FROM tests")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return await message.answer("📭 <b>Baza hozircha bo'sh.</b> Test yuklash uchun menga fayl yuboring.", parse_mode="HTML")
    
    res = "📋 <b>MAVJUD TESTLAR RO'YXATI:</b>\n\n"
    for r in rows:
        res += f"🔹 <code>{r[0]}</code> - {clean_html(r[1])}\n"
    
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("rating"))
async def show_rating(message: types.Message):
    """Test kodi bo'yicha reytingni ko'rsatish"""
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ <b>Xato!</b> Test kodini kiriting.\nMisol: <code>/rating 001</code>", parse_mode="HTML")
    
    t_code = args[1].strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Eng yuqori ball va eng tez ishlagan vaqt bo'yicha saralash
    cursor.execute("""
        SELECT user_name, score, total FROM results 
        WHERE test_code=%s 
        ORDER BY score DESC, date ASC 
        LIMIT 10
    """, (t_code,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return await message.answer(f"❌ <b>{t_code}</b> kodi bo'yicha hali natijalar yo'q.", parse_mode="HTML")
        
    res = f"🏆 <b>TEST {t_code} — TOP REYTING:</b>\n\n"
    rewards = ["🥇", "🥈", "🥉"]
    
    for i, r in enumerate(rows, 1):
        medal = rewards[i-1] if i <= 3 else f"{i}."
        res += f"{medal} <b>{clean_html(r[0])}</b> — {r[1]}/{r[2]}\n"
        
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("tanishbilish"))
async def vip_access(message: types.Message):
    """Admin tanishlari uchun shartni chetlab o'tish"""
    user_id = message.from_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Taklif sonini sun'iy ravishda 3 taga yetkazish
    cursor.execute("""
        INSERT INTO users (user_id, invited_by, invite_count, joined_at) 
        VALUES (%s, NULL, 3, %s) 
        ON CONFLICT (user_id) DO UPDATE SET invite_count = 3
    """, (user_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await message.answer("🤫 <b>Tanish-bilish ishga tushdi!</b>\nSizga maxsus ruxsat berildi.", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("users_count"))
async def get_stats(message: types.Message):
    """Admin uchun statistika"""
    if message.from_user.id != ADMIN_ID: return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    
    await message.answer(f"📊 <b>Botdagi jami foydalanuvchilar:</b> {count} nafar", parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_help(message: types.Message):
    """Admin menyusi"""
    if message.from_user.id != ADMIN_ID: return
    text = (
        "🛠 <b>ADMIN PANEL BUYRUQLARI:</b>\n\n"
        "📋 /tests - Testlar ro'yxatini ko'rish\n"
        "📊 /users_count - Foydalanuvchilar soni\n"
        "🏆 /rating [kod] - Reytingni ko'rish\n"
        "📥 <b>Test yuklash:</b> Shunchaki menga quyidagi formatda matn yuboring:\n\n"
        "<code>kod | mavzu | vaqt</code>\n"
        "<code>1. Savol | A, B, C | A</code>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text.contains("|"))
async def upload_test(message: types.Message):
    """Yangi test yuklash funksiyasi"""
    if message.from_user.id != ADMIN_ID: return
    
    lines = message.text.split('\n')
    header = lines[0].split('|')
    
    if len(header) != 3:
        return await message.answer("⚠️ <b>Format xato!</b>\nBirinchi qator: <code>kod | mavzu | vaqt</code> bo'lishi shart.", parse_mode="HTML")
    
    t_code = header[0].strip()
    t_title = header[1].strip()
    t_time = header[2].strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Testni saqlash (Agar avval bo'lsa yangilash)
        cursor.execute("""
            INSERT INTO tests (code, title, duration) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (code) DO UPDATE SET title = EXCLUDED.title, duration = EXCLUDED.duration
        """, (t_code, t_title, int(t_time)))
        
        # Eski savollarni o'chirish (yangilash uchun)
        cursor.execute("DELETE FROM questions WHERE test_code=%s", (t_code,))
        
        count = 0
        for line in lines[1:]:
            if '|' in line:
                parts = line.split('|')
                if len(parts) == 3:
                    q_text = parts[0].split('.', 1)[-1].strip()
                    # Variantlarni JSON formatida saqlash
                    opts = json.dumps([i.strip() for i in parts[1].split(",")])
                    correct = parts[2].strip()
                    
                    cursor.execute("""
                        INSERT INTO questions (test_code, question, options, correct_answer) 
                        VALUES (%s, %s, %s, %s)
                    """, (t_code, q_text, opts, correct))
                    count += 1
        
        conn.commit()
        await message.answer(f"✅ <b>{clean_html(t_title)}</b> muvaffaqiyatli saqlandi!\n📝 Jami savollar: {count} ta", parse_mode="HTML")
        
    except Exception as e:
        conn.rollback()
        await message.answer(f"❌ Saqlashda xatolik: {e}")
    finally:
        conn.close()

# ======================================================
# 5. ASOSIY ISHGA TUSHIRISH QISMI
# ======================================================
async def main():
    # Webhookni o'chirish (Conflict xatosini 100% oldini oladi)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Server sozlamalari
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    
    # Bot va Serverni parallel ishga tushirish
    await asyncio.gather(dp.start_polling(bot), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
    
