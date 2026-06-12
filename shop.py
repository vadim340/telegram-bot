import asyncio
import random
import json
import os

from supabase import create_client
from datetime import datetime, timedelta
from aiogram.enums import ChatType
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
from aiogram.types import WebAppInfo
from aiogram import Router, types
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime, timedelta
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from aiogram.enums import ChatType


API_TOKEN = os.getenv("BOT_TOKEN") or "8055752975:AAH2Im8lxCd0DbBvnONgs1gEU2ZqhGnN9zQ"
BOT_USERNAME = "eihagerigh_bot"   # без @
WEBAPP_URL = "https://vadim340.github.io/site/" # HTTPS

DATA_FILE = "bot_data.json"
owner_id = 6841810426

SUPABASE_URL = "https://castdkgctnnsygnifics.supabase.co/rest/v1/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNhc3Rka2djdG5uc3lnbmlmaWNzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEyNzM5NTYsImV4cCI6MjA5Njg0OTk1Nn0.rCpGgwGeMeGY3RB7HBtjMhBY-5BVde-6aCOx3pXHa20"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)
try:
    result = supabase.table("users").select("*").limit(1).execute()
    print("✅ Supabase OK")
except Exception as e:
    print("❌ Supabase ERROR:", e)

default_data = {
    "last_ton_collect": {},
    "user_dik_sizes": {},      # {user_id_str: float}
    "user_droch_counter": {},  # {user_id_str: int}
    "balances": {},            # {user_id_str: float}
    "ton_balances": {},        # {user_id_str: float}
    "user_inventory": {},
    "debts": {},               # {debtor_id_str: {creditor_id_str: float}}
    "marriages": {},           # {user_id_str: {"partner": partner_id_str, "date": iso_str}}
    "relationships": {},       # {user_id_str: [partner_id_str, ...]}
    "user_nicknames": {},      # {user_id_str: nickname}
    "users": {}                # {user_id_str: last_first_name}
}

TON_TO_UAH = 100  # 1 TON = 100 грн
TON_COOLDOWN = timedelta(hours=6)

router = Router()

# Глобальна змінна для збереження даних
data = {}


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print("⚠ Помилка при читанні data file:", e)
            data = default_data.copy()
    else:
        data = default_data.copy()
        save_data()
    # Гарантуємо наявність ключів
    for k, v in default_data.items():
        if k not in data:
            data[k] = v
    return data

def save_data():
    global data
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        print("⚠ Помилка при збереженні даних:", e)



data = load_data()

def _s(uid):
    return str(uid)


def save_user_info(user: types.User):
    """Записує останнє ім'я користувача у data['users']"""
    try:
        data["users"][_s(user.id)] = user.first_name or user.username or str(user.id)
        save_data()
    except Exception:
        pass


def get_balance(user_id):
    return int(data["balances"].get(_s(user_id), 0))


def add_balance(user_id, amount):
    uid = _s(user_id)
    data["balances"][uid] = int(data["balances"].get(uid, 0)) + int(amount)
    save_data()


def set_balance(user_id, amount):
    data["balances"][_s(user_id)] = int(amount)
    save_data()


def get_ton(user_id):
    return int(data["ton_balances"].get(_s(user_id), 0))


def add_ton(user_id, amount):
    uid = _s(user_id)
    data["ton_balances"][uid] = int(data["ton_balances"].get(uid, 0)) + int(amount)
    save_data()


# === ІНІЦІАЛІЗАЦІЯ ДАНИХ ===
load_data()


# debts: debtor -> creditor -> amount
def add_debt(debtor_id, creditor_id, amount):
    d = _s(debtor_id); c = _s(creditor_id)
    data["debts"].setdefault(d, {})
    data["debts"][d][c] = float(data["debts"][d].get(c, 0)) + float(amount)
    save_data()

def repay_debt(debtor_id, creditor_id, amount):
    d = _s(debtor_id); c = _s(creditor_id)
    if d not in data["debts"] or c not in data["debts"][d]:
        return 0.0
    owed = float(data["debts"][d][c])
    paid = min(owed, float(amount))
    remaining = owed - paid
    if remaining <= 0:
        del data["debts"][d][c]
        if not data["debts"][d]:
            del data["debts"][d]
    else:
        data["debts"][d][c] = remaining
    save_data()
    return paid

def get_debts_for_creditor(creditor_id):
    """Повертає список (debtor_id_str, amount) для заданого кредитора"""
    res = []
    for debtor, inner in data["debts"].items():
        amount = inner.get(_s(creditor_id))
        if amount:
            res.append((debtor, amount))
    return res

def get_debts_for_debtor(debtor_id):
    inner = data["debts"].get(_s(debtor_id), {})
    return list(inner.items())  # [(creditor_str, amount), ...]

# dick / droch
def get_dick_size(user_id):
    return float(data["user_dik_sizes"].get(_s(user_id), 0))

def set_dick_size(user_id, size):
    data["user_dik_sizes"][_s(user_id)] = float(size)
    save_data()

def inc_droch(user_id):
    uid = _s(user_id)
    data["user_droch_counter"][uid] = int(data["user_droch_counter"].get(uid, 0)) + 1
    save_data()
    return data["user_droch_counter"][uid]

# marriages / relationships
def are_in_relationships(a_id, b_id):
    lst = data["relationships"].get(_s(a_id), [])
    return _s(b_id) in lst

def add_relationship(a_id, b_id):
    a = _s(a_id); b = _s(b_id)
    data["relationships"].setdefault(a, [])
    data["relationships"].setdefault(b, [])
    if b not in data["relationships"][a]:
        data["relationships"][a].append(b)
    if a not in data["relationships"][b]:
        data["relationships"][b].append(a)
    save_data()

def remove_relationship(a_id, b_id):
    a = _s(a_id); b = _s(b_id)
    if a in data["relationships"]:
        if b in data["relationships"][a]:
            data["relationships"][a].remove(b)
            if not data["relationships"][a]:
                del data["relationships"][a]
    if b in data["relationships"]:
        if a in data["relationships"][b]:
            data["relationships"][b].remove(a)
            if not data["relationships"][b]:
                del data["relationships"][b]
    save_data()

def set_marriage(a_id, b_id):
    now_iso = datetime.now().isoformat()
    data["marriages"][_s(a_id)] = {"partner": _s(b_id), "date": now_iso}
    data["marriages"][_s(b_id)] = {"partner": _s(a_id), "date": now_iso}
    save_data()

def remove_marriage(a_id):
    a = _s(a_id)
    if a not in data["marriages"]:
        return None
    partner = data["marriages"][a]["partner"]
    data["marriages"].pop(a, None)
    data["marriages"].pop(partner, None)
    save_data()
    try:
        return int(partner)
    except Exception:
        return None

# nick helpers
def set_user_nick(user_id, nick):
    data["user_nicknames"][_s(user_id)] = nick
    save_data()

def get_nick(user):
    """
    Може приймати types.User або types.Chat або число/рядок.
    Повертає nickname якщо є, інакше first_name/full_name або str(id).
    """
    # якщо передали об'єкт з id і first_name
    uid = None
    if hasattr(user, "id"):
        uid = _s(user.id)
        nick = data["user_nicknames"].get(uid)
        if nick:
            return nick
        # fallback to object's name
        return getattr(user, "first_name", getattr(user, "full_name", str(user.id)))
    else:
        # user - може бути id або рядок
        uid = _s(user)
        nick = data["user_nicknames"].get(uid)
        if nick:
            return nick
        # якщо знаємо last saved name
        return data["users"].get(uid, uid)

def mention(user_id, name):
    return f'<a href="tg://user?id={user_id}">{name}</a>'

# === Ініціалізація бота ===
load_data()
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# =========================
# FASTAPI
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== ПРОФІЛЬ =====
@app.get("/profile/{user_id}")
def api_profile(user_id: int):

    uid = str(user_id)

    # створюємо користувача якщо його нема
    if uid not in data["balances"]:
        data["balances"][uid] = 1000000

    if uid not in data["ton_balances"]:
        data["ton_balances"][uid] = 0

    if uid not in data["user_inventory"]:
        data["user_inventory"][uid] = []

    save_data()

    return {

        "balance": data["balances"][uid],

        "ton": data["ton_balances"][uid],

        "inventory": data["user_inventory"][uid]

    }


# ===== КУПІВЛЯ =====
@app.post("/buy/{user_id}")
def api_buy(user_id: int, item: str, price: int):

    uid = str(user_id)

    # створюємо користувача
    if uid not in data["balances"]:
        data["balances"][uid] = 1000000

    if uid not in data["user_inventory"]:
        data["user_inventory"][uid] = []

    balance = data["balances"][uid]

    if balance < price:

        return {
            "ok": False,
            "error": "Недостатньо коштів"
        }

    # мінус баланс
    data["balances"][uid] -= price

    # додаємо предмет
    data["user_inventory"][uid].append(item)

    # ЗБЕРІГАЄМО
    save_data()

    return {

        "ok": True,

        "balance": data["balances"][uid],

        "ton": data["ton_balances"].get(uid, 0),

        "inventory": data["user_inventory"][uid]

    }


# ===== ЗАПУСК API =====
def start_api():

    render_port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=render_port
    )

# === Тимчасові структури, які не зберігаємо в JSON ===
pending_relationships = {}   # target_id -> proposer_id
pending_marriages = {}
active_battles = {}         # target_id -> (challenger_id, amount, message_id, chat_id)

# === Кулдауни (тимчасові, в пам'яті) ===
cooldowns = {
    "дроч": 1,
    "дік": 1,
    "зп": 1
}
last_used = {
    "дроч": {},
    "дік": {},
    "зп": {}
}

def is_on_cooldown(command: str, user_id: int) -> bool:
    now = datetime.now()
    last = last_used[command].get(user_id)
    cooldown_minutes = cooldowns.get(command, 0)
    if last is None or now - last >= timedelta(minutes=cooldown_minutes):
        last_used[command][user_id] = now
        return False
    return True

async def require_reply(message: Message) -> types.User | None:
    if not message.reply_to_message:
        await message.reply("❗ Ця команда працює лише у відповіді на повідомлення користувача.")
        return None
    return message.reply_to_message.from_user

def kb(proposal_id: int, proposal_type: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Прийняти", callback_data=f"accept:{proposal_type}:{proposal_id}"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data=f"decline:{proposal_type}:{proposal_id}")
        ]
    ])










@dp.message(F.text.in_(["!магазин", "!shop"]))
async def shop_in_group(message: Message):

    # Якщо ПП — одразу відкриваємо магазин
    if message.chat.type == ChatType.PRIVATE:
        await open_shop(message)
        return

        # КНОПКА ЯК У BLOODNEXUS (URL ↗)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎁 Магазин",
                url=f"https://t.me/{BOT_USERNAME}?startapp=shop"
            )
        ]
    ])


    await message.answer(
        "🛍 Щоб перейти до магазину, натисніть на кнопку.",
        reply_markup=kb
    )
async def open_shop(message: Message):

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🛍 Відкрити магазин",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "🛍 Магазин\nНатисни кнопку нижче 👇",
        reply_markup=kb
    )


@dp.message(F.web_app_data)
async def handle_webapp(message: Message):
    user_id = message.from_user.id
    payload = json.loads(message.web_app_data.data)
    action = payload.get("action")

    if action == "profile":
        balance = get_balance(user_id)
        await message.answer(f"👤 Профіль\n💵 Баланс: {balance}")

    elif action == "inventory":
        inv = data["user_inventory"].get(str(user_id), [])
        if not inv:
            await message.answer("🎒 Інвентар порожній.")
        else:
            await message.answer(
                "🎒 Інвентар:\n" +
                "\n".join(f"• {i}" for i in inv)
            )

    elif action == "buy":
        item = payload["item"]
        price = int(payload["price"])

        balance = get_balance(user_id)
        if balance < price:
            await message.answer("❌ Недостатньо коштів.")
            return

        add_balance(user_id, -price)

        inv = data["user_inventory"].setdefault(str(user_id), [])
        inv.append(item)
        save_data()

        await message.answer(
            f"✅ Куплено: {item}\n💵 -{price}"
        )













@dp.message(F.text.lower() == "!зібрати тон")
async def collect_ton(message: Message):
    uid = _s(message.from_user.id)
    now = datetime.now()

    last_time_str = data["last_ton_collect"].get(uid)
    if last_time_str:
        last_time = datetime.fromisoformat(last_time_str)
        if now - last_time < TON_COOLDOWN:
            remaining = TON_COOLDOWN - (now - last_time)
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes = remainder // 60
            await message.reply(f"⏳ Ти вже збирав TON! Спробуй знову через {hours} год {minutes} хв.")
            return

    ton_amount = random.randint(1, 10)
    data["ton_balances"][uid] = data["ton_balances"].get(uid, 0) + ton_amount
    data["last_ton_collect"][uid] = now.isoformat()
    save_data()

    await message.reply(f"💰 Ти зібрав {ton_amount} TON! Тепер у тебе {data['ton_balances'][uid]} TON.")

@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!розміняти'))
async def cmd_exchange_ton(message: types.Message):
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Вкажи кількість тон для розмінювання. Приклад: !розміняти 5")
        return

    try:
        amount = int(parts[1])
        if amount <= 0:
            await message.reply("Вкажи додатнє число тон для розмінювання.")
            return
    except ValueError:
        await message.reply("Неправильний формат кількості тон. Використовуй: !розміняти <кількість>")
        return

    user_id = message.from_user.id
    user_ton = get_ton(user_id)

    if user_ton < amount:
        await message.reply(f"У тебе недостатньо тонів для розмінювання. У тебе {user_ton} тонів.")
        return

    # Віднімаємо тон
    uid = _s(user_id)
    data["ton_balances"][uid] = user_ton - amount

    # Додаємо гривні (тон * 100)
    add_balance(user_id, amount * TON_TO_UAH)

    save_data()

    await message.reply(f"Ти розмінив {amount} тон на {amount * TON_TO_UAH} гривень. Баланс оновлено.")


ALLOWED_GIVERS = [6841810426]
@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!компенсація'))
async def cmd_give_ton(message: types.Message):
    if message.from_user.id not in ALLOWED_GIVERS:
        await message.reply("Вибач, ця команда доступна лише обраним користувачам.")
        return

    if not message.reply_to_message:
        await message.reply("Цю команду потрібно використовувати у відповіді на повідомлення користувача, якому хочеш дати тон.")
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Вкажи кількість тон. Приклад: !дати 5")
        return

    try:
        amount = int(parts[1])
        if amount <= 0:
            await message.reply("Вкажи додатнє число тон.")
            return
    except ValueError:
        await message.reply("Неправильний формат кількості тон. Використовуй: !дати <кількість>")
        return

    target_user = message.reply_to_message.from_user
    if not target_user:
        await message.reply("Не можу визначити користувача, якому треба дати тон.")
        return

    add_ton(target_user.id, amount)
    save_data()

    await message.reply(f"Додано {amount} тон користувачу {target_user.first_name or target_user.username}.")



@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!скинути'))
async def cmd_transfer_ton(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Цю команду потрібно використовувати у відповіді на повідомлення користувача, якому хочеш переказати тон.")
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Вкажи кількість тон. Приклад: !переказати 5")
        return

    try:
        amount = int(parts[1])
        if amount <= 0:
            await message.reply("Вкажи додатнє число тон для переказу.")
            return
    except ValueError:
        await message.reply("Неправильний формат кількості тон. Використовуй: !переказати <кількість>")
        return

    sender_id = message.from_user.id
    receiver = message.reply_to_message.from_user

    sender_ton = get_ton(sender_id)
    if sender_ton < amount:
        await message.reply(f"У тебе недостатньо тон для переказу. У тебе {sender_ton} тонів.")
        return

    uid_sender = _s(sender_id)
    data["ton_balances"][uid_sender] = sender_ton - amount

    uid_receiver = _s(receiver.id)
    receiver_ton = get_ton(receiver.id)
    data["ton_balances"][uid_receiver] = receiver_ton + amount

    save_data()

    await message.reply(f"Успішно переказано {amount} тон користувачу {receiver.full_name}.")

# БАТЛ
from aiogram.enums import ParseMode

@dp.message(lambda m: m.text and m.text.lower().startswith("!батл"))
async def start_battle(message: Message):
    save_user_info(message.from_user)
    if not message.reply_to_message:
        return await message.answer("❗ Ця команда працює лише у відповіді на повідомлення іншого користувача.")

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("❗ Формат: !батл <сума>")

    amount = int(parts[1])
    if amount < 10:
        return await message.answer("❗ Мінімальна ставка для батлу — 10💵.")

    challenger_id = message.from_user.id
    target_user = message.reply_to_message.from_user
    target_id = target_user.id

    if challenger_id == target_id:
        return await message.answer("❗ Не можна кинути виклик самому собі.")

    if get_balance(challenger_id) < amount:
        return await message.answer("💸 У тебе недостатньо коштів для батлу.")
    if get_balance(target_id) < amount:
        return await message.answer(f"💸 У {target_user.first_name} недостатньо коштів для батлу.")

    active_battles[_s(target_id)] = (challenger_id, amount, message.message_id, message.chat.id)

    kb_battle = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"battle_accept:{challenger_id}:{amount}"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data=f"battle_decline:{challenger_id}")
        ]
    ])

    await message.answer(
        f"⚔️ {mention(challenger_id, get_nick(challenger_id))} хоче зіграти з "
        f"{mention(target_id, get_nick(target_id))} у батл на {amount}💵!",
        reply_markup=kb_battle,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(lambda c: c.data and (c.data.startswith("battle_accept:") or c.data.startswith("battle_decline:")))
async def handle_battle_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[0].split("_")[1]  # accept або decline
    challenger_id = int(parts[1])

    if action == "accept":
        amount = int(parts[2])
        target_id = callback.from_user.id

        key = _s(target_id)
        if key not in active_battles or active_battles[key][0] != challenger_id:
            return await callback.answer("❗ Цей батл вже неактивний.", show_alert=True)

        del active_battles[key]

        if get_balance(challenger_id) < amount or get_balance(target_id) < amount:
            return await callback.message.edit_text("💸 Один з гравців не має достатньо коштів для батлу.")

        winner_id, loser_id = (challenger_id, target_id) if random.choice([True, False]) else (target_id, challenger_id)

        commission = int(amount * 0.1)
        prize = amount - commission
        add_balance(owner_id, commission)

        add_balance(winner_id, prize)
        add_balance(loser_id, -amount)

        winner_name = get_nick(winner_id)
        loser_name = get_nick(loser_id)

        await callback.message.edit_text(
            f"🏆 {mention(winner_id, winner_name)} виграв {prize}💵 у батлі проти {mention(loser_id, loser_name)}!",
            parse_mode=ParseMode.HTML
        )

    elif action == "decline":
        target_id = callback.from_user.id
        key = _s(target_id)
        if key in active_battles and active_battles[key][0] == challenger_id:
            del active_battles[key]
        await callback.message.edit_text("❌ Виклик на батл відхилено.")

    await callback.answer()



# ПОЦІЛУВАТИ
@dp.message(lambda m: m.text and m.text.lower().startswith("поцілувати"))
async def handle_kiss(message: Message):
    save_user_info(message.from_user)
    if not message.reply_to_message:
        await message.answer("❗ Ця команда працює тільки у відповіді на повідомлення користувача.")
        return
    save_user_info(message.reply_to_message.from_user)

    sender_mention = mention(message.from_user.id, get_nick(message.from_user))
    target_user = message.reply_to_message.from_user
    target_mention = mention(target_user.id, get_nick(target_user))
    await message.answer(f"😘 {sender_mention} поцілував(ла) {target_mention} 💋", parse_mode=ParseMode.HTML)

# ПОЗИЧИТИ
@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!позичити'))
async def handle_borrow(msg: types.Message):
    save_user_info(msg.from_user)
    parts = msg.text.split()

    if msg.reply_to_message:
        # позичаєш у відповіді на повідомлення (кредитор -> позичальник?)
        if len(parts) != 2:
            return await msg.reply("❗ Формат у відповіді: !позичити сума")
        try:
            amount = float(parts[1])
        except ValueError:
            return await msg.reply("❗ Неправильна сума.")
        debtor = msg.reply_to_message.from_user
    else:
        # позичаєш через @username
        if len(parts) != 3:
            return await msg.reply("❗ Формат: !позичити @username сума")
        username = parts[1].lstrip('@')
        try:
            amount = float(parts[2])
        except ValueError:
            return await msg.reply("❗ Неправильна сума.")

        # Знаходимо user_id за username у чаті
        try:
            user_chat = await bot.get_chat_member(msg.chat.id, username)
            debtor = user_chat.user
        except Exception:
            return await msg.reply("❗ Користувача не знайдено.")
    
    creditor = msg.from_user

    if debtor.id == creditor.id:
        return await msg.reply("❗ Ти не можеш позичити сам собі.")

    # Зберігаємо імена
    save_user_info(creditor)
    save_user_info(debtor)

    # Запис боргу
    add_debt(debtor.id, creditor.id, amount)

    # 🔹 Додаємо позичену суму до балансу боржника
    add_balance(debtor.id, amount)

    # 🔻 Віднімаємо суму в кредитора
    add_balance(creditor.id, -amount)

    await msg.reply(f"✅ {mention(creditor.id, creditor.first_name)} позичив {mention(debtor.id, debtor.first_name)} {amount} грн.")

# ВІДДАТИ
@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!віддати'))
async def handle_repay(msg: types.Message):
    save_user_info(msg.from_user)
    parts = msg.text.split()

    if msg.reply_to_message:
        if len(parts) != 2:
            return await msg.reply("❗ Формат у відповіді: !віддати сума")
        try:
            amount = float(parts[1])
        except ValueError:
            return await msg.reply("❗ Неправильна сума.")
        creditor = msg.reply_to_message.from_user
    else:
        if len(parts) != 3:
            return await msg.reply("❗ Формат: !віддати @username сума")
        username = parts[1].lstrip('@')
        try:
            amount = float(parts[2])
        except ValueError:
            return await msg.reply("❗ Неправильна сума.")

        # Знаходимо user_id за username у чаті
        try:
            user_chat = await bot.get_chat_member(msg.chat.id, username)
            creditor = user_chat.user
        except Exception:
            return await msg.reply("❗ Користувача не знайдено.")

    debtor = msg.from_user

    save_user_info(debtor)
    save_user_info(creditor)

    key = (_s(debtor.id), _s(creditor.id))
    # Перевіряємо наявність боргу
    if _s(debtor.id) not in data["debts"] or _s(creditor.id) not in data["debts"][_s(debtor.id)]:
        return await msg.reply("❗ У тебе немає боргу перед цим користувачем.")

    # Забезпечуємо, що не можна віддати більше, ніж винен
    paid_amount = repay_debt(debtor.id, creditor.id, amount)

    # 🔻 Віднімаємо з балансу боржника
    add_balance(debtor.id, -paid_amount)

    # 🔺 Додаємо до балансу кредитора
    add_balance(creditor.id, paid_amount)

    await msg.reply(f"✅ {mention(debtor.id, debtor.first_name)} віддав(ла) {mention(creditor.id, creditor.first_name)} {paid_amount} грн.")

# СПИСОК ВСІХ БОРГІВ
@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!боржники'))
async def handle_all_debts(msg: types.Message):
    if not data["debts"]:
        return await msg.reply("💤 Боргів поки немає.")

    lines = []
    for debtor_id, inner in data["debts"].items():
        for creditor_id, amount in inner.items():
            debtor_name = data["users"].get(debtor_id, "Невідомий")
            creditor_name = data["users"].get(creditor_id, "Невідомий")
            lines.append(f"🔸 <a href=\"tg://user?id={debtor_id}\">{debtor_name}</a> позичив у <a href=\"tg://user?id={creditor_id}\">{creditor_name}</a> {amount} грн")

    await msg.reply("\n".join(lines), parse_mode=ParseMode.HTML)

# БОРГИ ТИМ, ХТО ТОБІ ВИНЕН
@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!борги'))
async def handle_debts(msg: types.Message):
    user_id = msg.from_user.id
    result = []
    for debtor, inner in data["debts"].items():
        if _s(user_id) in inner:
            name = data["users"].get(debtor, "Невідомий")
            mention_text = f'<a href="tg://user?id={debtor}">{name}</a>'
            amount = inner[_s(user_id)]
            result.append(f"🔸 {mention_text} винен(на) тобі {amount} грн")
    if result:
        await msg.reply("\n".join(result), parse_mode=ParseMode.HTML)
    else:
        await msg.reply("💤 Ніхто нічого тобі не винен.")

# МОЇ БОРГИ
@dp.message(lambda msg: msg.text and msg.text.lower().startswith('!мої борги'))
async def handle_my_debts(msg: types.Message):
    user_id = msg.from_user.id
    result = []
    for debtor, inner in data["debts"].items():
        if debtor == _s(user_id):
            for creditor, amount in inner.items():
                name = data["users"].get(creditor, "Невідомий")
                mention_text = f'<a href="tg://user?id={creditor}">{name}</a>'
                result.append(f"🔸 Ти винен(на) {mention_text} {amount} грн")
    if result:
        await msg.reply("\n".join(result), parse_mode=ParseMode.HTML)
    else:
        await msg.reply("🎉 У тебе немає боргів.")

# КАЗИНО
@dp.message(F.text.startswith('!казино'))
async def play_casino(message: Message):
    save_user_info(message.from_user)
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) != 2 or not args[1].isdigit():
        await message.reply("⚠️ Використання: !казино (сума)")
        return

    bet = int(args[1])
    balance = get_balance(user_id)

    if bet < 50:
        await message.reply("🔒 Мінімальна ставка — 50 гривень.")
        return

    if balance < bet:
        await message.reply("💸 Недостатньо коштів на балансі.")
        return

    win = random.choice([True, False])

    if win:
        add_balance(user_id, bet)
        await message.answer(f"🎉 Вітаю! Ти виграв {bet}💵\n💰 Баланс: {get_balance(user_id)} гривень")
    else:
        add_balance(user_id, -bet)
        add_balance(owner_id, bet)
        await message.answer(f"😢 Ти програв {bet}💵\n💰 Баланс: {get_balance(user_id)} гривень")

# ЗП
@dp.message(F.text == "зп")
async def give_salary(message: Message):
    user_id = message.from_user.id
    save_user_info(message.from_user)
    if is_on_cooldown("зп", user_id):
        await message.answer("⏳ Чекати ще рано на зп.")
        return
    amount = random.randint(1, 30)
    add_balance(user_id, amount)
    await message.answer(f"👨‍💼 {message.from_user.first_name} забрав зарплату {amount}💵")

# БАЛАНС
@dp.message(F.text == "баланс")
async def show_balance(message: Message):
    save_user_info(message.from_user)
    user_id = message.from_user.id
    uah = get_balance(user_id)
    ton = get_ton(user_id)
    await message.answer(
        "<b>🏦 На рахунку:</b>\n"
        "<pre>"
        f"Гривні: {uah} 💵\n"
        f"Ton: {ton} 💠"
        "</pre>",
        parse_mode="HTML"
    )

# ПРОПОЗИЦІЇ СТОСУНКІВ
@dp.message(lambda m: m.text and m.text.lower().startswith("запропонувати стосунки"))
async def cmd_relationship(message: types.Message):
    save_user_info(message.from_user)
    if not message.reply_to_message:
        return await message.answer("❗ Ця команда працює тільки у відповіді на повідомлення користувача.")
    target = message.reply_to_message.from_user
    save_user_info(target)

    if target.id == message.from_user.id:
        await message.answer("❗ Не можна пропонувати стосунки самому собі.")
        return

    if are_in_relationships(target.id, message.from_user.id):
        await message.answer("💞 Ви вже в стосунках.")
        return

    pending_relationships[target.id] = message.from_user.id

    await message.answer(
        f"💌 {mention(message.from_user.id, message.from_user.first_name)} пропонує "
        f"{mention(target.id, target.first_name)} стосунки!",
        reply_markup=kb(message.from_user.id, "relationship")
    )

@dp.message(lambda m: m.text and m.text.lower().startswith("запропонувати шлюб"))
async def cmd_marriage(message: types.Message):
    save_user_info(message.from_user)
    if not message.reply_to_message:
        return await message.answer("❗ Ця команда працює тільки у відповіді на повідомлення користувача.")
    target = message.reply_to_message.from_user
    save_user_info(target)

    if target.id == message.from_user.id:
        await message.answer("❗ Не можна запропонувати шлюб самому собі.")
        return

    if _s(message.from_user.id) in data["marriages"]:
        await message.answer("💍 Ти вже в шлюбі.")
        return
    if _s(target.id) in data["marriages"]:
        await message.answer("💍 Ця людина вже в шлюбі.")
        return

    pending_marriages[target.id] = message.from_user.id

    await message.answer(
        f"💌 {mention(message.from_user.id, message.from_user.first_name)} пропонує "
        f"{mention(target.id, target.first_name)} шлюб!",
        reply_markup=kb(message.from_user.id, "marriage")
    )

@dp.callback_query(lambda c: c.data and (c.data.startswith("accept:") or c.data.startswith("decline:")))
async def handle_proposal(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[0]
    proposal_type = parts[1]
    proposer_id = int(parts[2])
    accepter = callback.from_user

    if proposal_type == "relationship":
        if accepter.id not in pending_relationships or pending_relationships[accepter.id] != proposer_id:
            await callback.answer("❗ Немає такої пропозиції.", show_alert=True)
            return

        if action == "accept":
            add_relationship(accepter.id, proposer_id)
            try:
                proposer_chat = await bot.get_chat(proposer_id)
                proposer_name = proposer_chat.first_name
            except Exception:
                proposer_name = get_nick(proposer_id)
            await callback.message.edit_text(
                f"💞 {mention(proposer_id, proposer_name)} і "
                f"{mention(accepter.id, accepter.first_name)} тепер у стосунках!",
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.message.edit_text("❌ Пропозицію стосунків відхилено.")

        del pending_relationships[accepter.id]

    elif proposal_type == "marriage":
        if accepter.id not in pending_marriages or pending_marriages[accepter.id] != proposer_id:
            await callback.answer("❗ Немає такої пропозиції.", show_alert=True)
            return

        if action == "accept":
            set_marriage(accepter.id, proposer_id)
            try:
                proposer_chat = await bot.get_chat(proposer_id)
                proposer_name = proposer_chat.first_name
            except Exception:
                proposer_name = get_nick(proposer_id)
            await callback.message.edit_text(
                f"💍 {mention(proposer_id, proposer_name)} і "
                f"{mention(accepter.id, accepter.first_name)} тепер одружені!",
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.message.edit_text("❌ Пропозицію шлюбу відхилено.")

        del pending_marriages[accepter.id]

    await callback.answer()

@dp.message(lambda m: m.text and m.text.lower() == "мій шлюб")
async def cmd_my_marriage(message: types.Message):
    save_user_info(message.from_user)
    user_id = _s(message.from_user.id)
    if user_id not in data["marriages"]:
        await message.answer("❗ У тебе немає зареєстрованого шлюбу.")
        return

    marriage_info = data["marriages"][user_id]
    partner_id = int(marriage_info["partner"])
    date_start = datetime.fromisoformat(marriage_info["date"])
    duration = datetime.now() - date_start

    try:
        partner = await bot.get_chat(partner_id)
        partner_name = partner.full_name
    except Exception:
        partner_name = get_nick(partner_id)

    await message.answer(
        f"💍 Ти в шлюбі з {mention(partner_id, partner_name)}\n"
        f"📅 Дата реєстрації: {date_start.strftime('%d.%m.%Y %H:%M')}\n"
        f"⏳ Тривалість шлюбу: {duration.days} днів"
    )

@dp.message(lambda m: m.text and m.text.lower() == "мої стосунки")
async def cmd_my_relationships(message: types.Message):
    save_user_info(message.from_user)
    user_id = _s(message.from_user.id)
    partners = data["relationships"].get(user_id, [])
    if not partners:
        await message.answer("❗ У тебе немає стосунків.")
        return

    lines = []
    for pid_str in partners:
        try:
            pid = int(pid_str)
            partner = await bot.get_chat(pid)
            partner_name = partner.full_name
        except Exception:
            partner_name = data["users"].get(pid_str, pid_str)
        lines.append(mention(pid_str, partner_name))
    await message.answer("💞 Твої стосунки:\n" + "\n".join(lines), parse_mode=ParseMode.HTML)

@dp.message(lambda m: m.text and m.text.lower() == "розлучитись")
async def cmd_divorce_confirm(message: types.Message):
    save_user_info(message.from_user)
    user_id = _s(message.from_user.id)
    if user_id not in data["marriages"]:
        await message.answer("❗ Ти не в шлюбі.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💔 Розлучитись", callback_data="confirm_divorce")]
    ])
    await message.answer("Ви дійсно бажаєте розлучитись?", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "confirm_divorce")
async def process_divorce(callback: CallbackQuery):
    user_id = callback.from_user.id
    if _s(user_id) not in data["marriages"]:
        await callback.answer("❗ Ти не в шлюбі.", show_alert=True)
        return

    partner_id = remove_marriage(user_id)
    if partner_id is None:
        await callback.answer("❗ Помилка при розлученні.", show_alert=True)
        return

    try:
        partner_chat = await bot.get_chat(partner_id)
        partner_name = partner_chat.first_name
    except Exception:
        partner_name = get_nick(partner_id)

    await callback.message.edit_text(
        f"💔 Ви з {mention(partner_id, partner_name)} розлучилися.",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(lambda m: m.text and m.text.lower() == "розірвати стосунки")
async def cmd_break_relationship(message: types.Message):
    save_user_info(message.from_user)
    if not message.reply_to_message:
        return await message.answer("❗ Щоб розірвати стосунки, потрібно відповісти на повідомлення партнера.")

    user_id = message.from_user.id
    partner = message.reply_to_message.from_user
    partner_id = partner.id

    if not are_in_relationships(user_id, partner_id):
        await message.answer("❗ Ви не перебуваєте в стосунках з цією людиною.")
        return

    remove_relationship(user_id, partner_id)
    partner_mention = mention(partner.id, get_nick(partner))
    await message.answer(f"💔 Ви розірвали стосунки з {partner_mention}.", parse_mode=ParseMode.HTML)

# КОМАНДИ "дроч" і "дік" (збереження)
@dp.message(lambda m: m.text and m.text.lower().startswith("дроч"))
async def handle_droch(message: Message):
    save_user_info(message.from_user)
    user_id = message.from_user.id
    name = mention(user_id, get_nick(message.from_user))

    if is_on_cooldown("дроч", user_id):
        await message.answer("⏳ Почекай, ще не час дрочити 💦")
        return

    count = inc_droch(user_id)

    if not message.reply_to_message:
        await message.answer(f"✋ {name} подрочив 💦\nВсього дрочок: <b>{count}</b>", parse_mode=ParseMode.HTML)
        return

    target_user = message.reply_to_message.from_user
    save_user_info(target_user)
    target = mention(target_user.id, get_nick(target_user))
    await message.answer(f"✋ {name} подрочив на {target} 💦\nВсього дрочок: <b>{count}</b>", parse_mode=ParseMode.HTML)

@dp.message(lambda m: m.text and m.text.lower().startswith("лік") or m.text and m.text.lower().startswith("дік"))
async def handle_dik(message: Message):
    # зверни увагу: у твоєму початковому коді хендлер для "дік" був окремий.
    # Тут обробляємо "дік" — збереження розміру в data["user_dik_sizes"].
    if not (message.text and message.text.lower().startswith("дік")):
        return
    save_user_info(message.from_user)
    user_id = message.from_user.id
    name = mention(user_id, get_nick(message.from_user))

    if is_on_cooldown("дік", user_id):
        await message.answer("🍌 Твій дік поки що не змінився. Спробуй пізніше.")
        return

    uid = _s(user_id)
    if uid not in data["user_dik_sizes"] or float(data["user_dik_sizes"].get(uid, 0)) == 0:
        size = round(random.uniform(10.0, 20.0), 2)
        set_dick_size(user_id, size)
        await message.answer(f"🍌 {name}, твій дік виріс до {size} см (вперше)")
    else:
        change = round(random.uniform(-2.0, 5.0), 2)
        new_size = round(max(1.0, float(data["user_dik_sizes"].get(uid, 0)) + change), 2)
        set_dick_size(user_id, new_size)
        trend = "📈" if change > 0 else "📉"
        verb = "виріс" if change > 0 else "зменшився"
        await message.answer(f"{trend} {name}, твій 🍌 {verb} на {abs(change)} см.\n📏 Новий розмір: {new_size} см.")

# Налаштування кулдауну
@dp.message(lambda m: m.text and m.text.lower().startswith("!кд"))
async def set_cooldown(message: Message):
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer("❗️ Формат: !кд <дроч/дік/зп> <хвилини>\nНапр: !кд дроч 10")
        return

    cmd, value = parts[1], parts[2]
    if cmd not in cooldowns:
        await message.answer("🚫 Команду не знайдено. Можна: дроч, дік, зп")
        return

    try:
        minutes = int(value)
        cooldowns[cmd] = max(0, minutes)
        await message.answer(f"✅ КД для <b>{cmd}</b> встановлено: {minutes} хв")
    except ValueError:
        await message.answer("❗️ Введи число для хвилин. Наприклад: !кд дік 5")

# ДОПОМОГА
@dp.message(lambda msg: msg.text and msg.text.lower() == "допомога")
async def help_main(message: Message):
    kb_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Фінанси", callback_data="help:finance")],
        [InlineKeyboardButton(text="❤️ Стосунки", callback_data="help:love")],
        [InlineKeyboardButton(text="🎮 Розваги", callback_data="help:fun")]
    ])
    await message.answer("📖 Обери категорію команд:", reply_markup=kb_markup)

@dp.message(lambda m: m.text and m.text.lower().startswith("лав"))
async def handle_love(message: Message):
    if not message.reply_to_message:
        await message.answer("💌 Відповідай на повідомлення, щоб зайнятись любов’ю!")
        return

    name = mention(message.from_user.id, get_nick(message.from_user))
    target_user = message.reply_to_message.from_user
    target = mention(target_user.id, get_nick(target_user))
    await message.answer(f"❤️ {name} та {target} зайнялися любов'ю... 😏", parse_mode=ParseMode.HTML)


@dp.callback_query(lambda c: c.data and c.data.startswith("help:"))
async def show_help_category(callback: CallbackQuery):
    category = callback.data.split(":")[1]

    help_texts = {
        "finance": (
            "💰 <b>Фінансові команди:</b>\n"
            "• !позичити — дати в борг (відповідь на повідомлення або @username)\n"
            "• !віддати — повернути борг\n"
            "• !борги — хто винен тобі\n"
            "• !мої борги — твої борги\n"
            "• баланс — показати рахунок\n"
            "• зп — отримати зарплату\n"
            "• !казино — випробуй удачу"
        ),
        "love": (
            "❤️ <b>Стосунки:</b>\n"
            "• запропонувати стосунки — запропонувати стосунки (у відповіді)\n"
            "• мої стосунки — подивитися список\n"
            "• запропонувати шлюб — у відповіді на повідомлення\n"
            "• мій шлюб — перевірити шлюб\n"
            "• розлучитись — розірвати шлюб"
        ),
        "fun": (
            "🎮 <b>Розваги:</b>\n"
            "• дроч — подрочити (є кулдаун)\n"
            "• дік — ріст 🍌 (є кулдаун)\n"
            "• лав — любов з кимось\n"
            "• поцілувати — вітання з ❤️"
        ),
    }

    await callback.message.edit_text(help_texts[category], parse_mode="HTML")
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":

    api_thread = threading.Thread(target=start_api)
    api_thread.start()

    import asyncio
    asyncio.run(dp.start_polling(bot))