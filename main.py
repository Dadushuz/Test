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
    CallbackQuery, Update
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

# --- 1. SOZLAMALAR ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
except:
    ADMIN_ID = 129932291

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://test-fzug.onrender.com").rstrip('/')
WEBAPP_URL = f"{RENDER_URL}/static/index.html"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"
DATABASE_URL = "postgresql://postgres.zvtrujwsydewfcaotwvx:rkbfVJlp96S85bnu@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
TASHKENT_TZ = pytz.timezone('Asia/Tashkent')

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- 2. YORDAMCHI FUNKSIYALAR ---
def get_time():
    """Hozirgi vaqtni qaytaradi"""
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")

def clean(text):
    """HTML xavfsizligi"""
    return re.sub(r'<.*?>', '', str(text)).replace('<', '&lt;').replace('>', '&gt;') if text else ""

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
        logger.info("✅ Baza va Jadvallar tayyor!")
    except Exception as e:
        logger.error(f"❌ Baza xatosi: {e}")

init_db()

# --- 3. MENYULAR (KEYBOARDS) ---

def main_menu_kb(is_allowed: bool):
    """Foydalanuvchi menyusi"""
    builder = InlineKeyboardBuilder()
    if is_allowed:
        builder.button(text="📝 Testni Boshlash", web_app=WebAppInfo(url=WEBAPP_URL))
    else:
        builder.button(text="🔒 Testni Boshlash", callback_data="locked_alert")
    
    builder.button(text="🚀 Do'stlarni Chaqirish", callback_data="invite_friends")
    builder.button(text="👤 Profilim", callback_data="my_profile")
    builder.adjust(1)
    return builder.as_markup()

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Asosiy Menyuga", callback_data="back_main")]])

def admin_kb():
    """Admin Asosiy Menyusi"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Testlar Ro'yxati", callback_data="adm_list"), InlineKeyboardButton(text="🗑 Test O'chirish", callback_data="adm_delete")],
        [InlineKeyboardButton(text="📤 Test Yuklash", callback_data="adm_upload"), InlineKeyboardButton(text="📢 Xabar Yuborish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats"), InlineKeyboardButton(text="🔍 User Izlash", callback_data="adm_search")],
        [InlineKeyboardButton(text="❌ Panelni Yopish", callback_data="close_menu")]
    ])

def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Admin Menyuga", callback_data="adm_menu")]])

# --- 4. SERVER (FASTAPI) ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Update xatosi: {e}")
        return {"ok": False}

@app.get("/")
async def root(): return {"status": "Active", "time": get_time()}

# API: Test olish
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

# API: Natija saqlash
@app.post("/submit_result")
async def submit(request: Request):
    try:
        d = await request.json()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (d.get('user_id'), clean(d.get('user_name')), d.get('nickname'), d.get('code'), d.get('title'), d.get('score'), d.get('total'), get_time()))
                conn.commit()
        await bot.send_message(ADMIN_ID, f"🎯 <b>YANGI NATIJA:</b>\n👤 {clean(d.get('user_name'))}\n📚 {d.get('title')}\n📊 {d.get('score')}/{d.get('total')}", parse_mode="HTML")
        return {"status": "success"}
    except: return {"status": "error"}

# --- 5. BOT LOGIKASI (USER) ---

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    uid, name = msg.from_user.id, clean(msg.from_user.full_name)
    args = msg.text.split()
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            if not user:
                inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
                cur.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (%s, %s, 0, %s)", (uid, inviter, get_time()))
                if inviter:
                    cur.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=%s", (inviter,))
                    try: await bot.send_message(inviter, "🚀 <b>Ball +1!</b> Do'stingiz qo'shildi.")
                    except: pass
                conn.commit()
                count = 0
            else: count = user[0]

    is_allowed = (uid == ADMIN_ID) or (count >= 3)
    text = (f"👋 <b>Assalomu alaykum, {name}!</b>\n\n"
            f"Botimizga xush kelibsiz. Bilimingizni sinashga tayyormisiz?\n"
            f"💎 Sizning ballaringiz: <b>{count} / 3</b>")

    await msg.answer(text, reply_markup=main_menu_kb(is_allowed), parse_mode="HTML")

@dp.callback_query(F.data == "locked_alert")
async def show_alert(call: CallbackQuery):
    await call.answer("🚫 Ruxsat yo'q! Avval 3 ta do'stingizni taklif qiling.", show_alert=True)

@dp.callback_query(F.data == "invite_friends")
async def invite_handler(call: CallbackQuery):
    await call.answer()
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={call.from_user.id}"
    
    text = f"📣 <b>Do'stlarni Taklif Qilish</b>\n\nMaxsus havolangiz:\n🔗 <code>{link}</code>\n\nUni do'stlaringizga yuboring!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ulashish ↗️", switch_inline_query=f"\nTest yechamiz! {link}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "my_profile")
async def profile_handler(call: CallbackQuery):
    await call.answer()
    uid = call.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count, joined_at FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            cur.execute("SELECT test_title, score, total FROM results WHERE user_id=%s ORDER BY id DESC LIMIT 5", (uid,))
            results = cur.fetchall()
            
    res_list = "\n".join([f"▫️ {r[0]}: <b>{r[1]}/{r[2]}</b>" for r in results]) if results else "Test yechilmagan"
    text = f"👤 <b>Mening Profilim:</b>\n\n🆔 ID: <code>{uid}</code>\n📅 Sana: {user[1]}\n👥 Takliflar: <b>{user[0]}</b> ta\n\n📚 <b>Oxirgi Natijalar:</b>\n{res_list}"
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    uid = call.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            res = cur.fetchone()
            count = res[0] if res else 0
            
    is_allowed = (uid == ADMIN_ID) or (count >= 3)
    await call.message.edit_text(f"🏠 <b>Asosiy Menyu</b>\n\n💎 Ballar: <b>{count}</b>", reply_markup=main_menu_kb(is_allowed), parse_mode="HTML")

# --- 6. ADMIN PANEL (FULL) ---

@dp.message(Command("admin"))
async def admin_start(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("👑 <b>Admin Panel</b>\nBoshqaruv turini tanlang:", reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_menu")
async def back_admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    await call.message.edit_text("👑 <b>Admin Panel</b>", reply_markup=admin_kb(), parse_mode="HTML")

# 1. Testlar Ro'yxati
@dp.callback_query(F.data == "adm_list")
async def adm_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, title, duration FROM tests")
            rows = cur.fetchall()
    
    txt = "📋 <b>Mavjud Testlar:</b>\n\n" + "\n".join([f"🔹 <code>{r[0]}</code> | {r[1]} ({r[2]} daq)" for r in rows]) if rows else "📭 Testlar yo'q."
    await call.message.edit_text(txt, reply_markup=admin_back_kb(), parse_mode="HTML")

# 2. Test Yuklash
@dp.callback_query(F.data == "adm_upload")
async def adm_upload(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    txt = (
        "📤 <b>Test Yuklash Formati:</b>\n\n"
        "1-qator: <code>KOD | MAVZU | VAQT</code>\n"
        "2-qator: <code>Savol matni | A javob, B javob | To'g'ri javob</code>\n"
        "...\n\n"
        "<i>Namuna:</i>\n"
        "<code>101 | Matematika | 15\n"
        "2+2=? | 3, 4, 5 | 4</code>\n\n"
        "Shu formatda xabar yuboring."
    )
    await call.message.edit_text(txt, reply_markup=admin_back_kb(), parse_mode="HTML")

# 3. Test O'chirish
@dp.callback_query(F.data == "adm_delete")
async def adm_delete(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    await call.message.edit_text("🗑 <b>Testni O'chirish:</b>\n\nO'chirish uchun buyruq yuboring:\n`/del [test_kodi]`\n\nMasalan: `/del 101`", reply_markup=admin_back_kb(), parse_mode="HTML")

# 4. Statistika
@dp.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM results")
            tests = cur.fetchone()[0]
    
    txt = f"📊 <b>Statistika:</b>\n\n👥 Foydalanuvchilar: <b>{users}</b>\n📝 Yechilgan testlar: <b>{tests}</b>\n⏰ Vaqt: {get_time()}"
    await call.message.edit_text(txt, reply_markup=admin_back_kb(), parse_mode="HTML")

# 5. User Qidirish
@dp.callback_query(F.data == "adm_search")
async def adm_search(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    await call.message.edit_text("🔍 <b>User Izlash:</b>\n\nID bo'yicha ma'lumot olish uchun:\n`/user [id]`\n\nMasalan: `/user 123456789`", reply_markup=admin_back_kb(), parse_mode="Markdown")

# 6. Broadcast (Reklama)
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer()
    await call.message.edit_text("📢 <b>Xabar Yuborish:</b>\n\nHamma foydalanuvchiga xabar yuborish uchun:\n`/send Xabar matni`\n\nMasalan: `/send Yangi test qo'shildi!`", reply_markup=admin_back_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "close_menu")
async def close_menu(call: CallbackQuery):
    await call.message.delete()

# --- ADMIN TEXT HANDLERS (BUYRUQLAR) ---

# Test Yuklash Logikasi
@dp.message(F.text.contains("|"))
async def upload_logic(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        lines = msg.text.split('\n')
        code, title, time = map(str.strip, lines[0].split('|'))
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO tests (code, title, duration) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET title=%s, duration=%s", (code, title, int(time), title, int(time)))
                cur.execute("DELETE FROM questions WHERE test_code=%s", (code,))
                count = 0
                for l in lines[1:]:
                    if '|' in l:
                        parts = list(map(str.strip, l.split('|')))
                        if len(parts) >= 3:
                            q = parts[0]
                            if '.' in q[:4]: q = q.split('.', 1)[-1].strip()
                            opts = [x.strip() for x in parts[1].split(',')]
                            ans = parts[2]
                            cur.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (%s, %s, %s, %s)", (code, q, json.dumps(opts), ans))
                            count += 1
                conn.commit()
        await msg.answer(f"✅ <b>{title}</b> yuklandi! ({count} savol)", parse_mode="HTML")
    except Exception as e: await msg.answer(f"❌ Xato: {e}")

# Test O'chirish
@dp.message(Command("del"))
async def delete_test(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        code = msg.text.split()[1]
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tests WHERE code=%s", (code,))
                cur.execute("DELETE FROM questions WHERE test_code=%s", (code,))
                cur.execute("DELETE FROM results WHERE test_code=%s", (code,))
                conn.commit()
        await msg.answer(f"🗑 <b>{code}</b> raqamli test o'chirildi!", parse_mode="HTML")
    except: await msg.answer("⚠️ Kod xato! Masalan: `/del 101`")

# User Tekshirish
@dp.message(Command("user"))
async def check_user(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        uid = int(msg.text.split()[1])
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT invite_count, joined_at FROM users WHERE user_id=%s", (uid,))
                res = cur.fetchone()
        if res:
            await msg.answer(f"👤 <b>User:</b> {uid}\n👥 Ball: {res[0]}\n📅 Sana: {res[1]}", parse_mode="HTML")
        else:
            await msg.answer("❌ User topilmadi.")
    except: await msg.answer("⚠️ ID xato!")

# Broadcast (Xabar tarqatish)
@dp.message(Command("send"))
async def broadcast_msg(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    text = msg.text.replace("/send", "").strip()
    if not text: return await msg.answer("Xabar bo'sh bo'lmasligi kerak.")
    
    await msg.answer("⏳ Xabar yuborish boshlandi...")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            users = cur.fetchall()
    
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 <b>E'LON:</b>\n\n{text}", parse_mode="HTML")
            count += 1
            await asyncio.sleep(0.05) # Spam bo'lmasligi uchun
        except: pass
    
    await msg.answer(f"✅ Xabar {count} kishiga yuborildi.")

# VIP
@dp.message(Command("tanishbilish"))
async def vip(msg: types.Message):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET invite_count=3 WHERE user_id=%s", (msg.from_user.id,))
            conn.commit()
    await msg.answer("✅ VIP berildi!")

# Debug
@dp.callback_query()
async def catch_all(call: CallbackQuery):
    await call.answer("Tez orada...", show_alert=True)

# --- STARTUP ---
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
                
