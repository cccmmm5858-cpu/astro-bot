import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import os
import sys
import datetime
import time
from flask import Flask
from threading import Thread

# ==========================================
# 1. إعدادات البوت والأدمن
# ==========================================
TOKEN = "8250995383:AAGedE3pilv1gmcw2ovj52hyTgb6t9KZlCc"
ADMIN_ID = 344671948 

try:
    bot = telebot.TeleBot(TOKEN)
except Exception as e:
    print(f"خطأ في التوكن: {e}")
    sys.exit(1)

# ==========================================
# 2. سيرفر Flask الوهمي (لإرضاء Render)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "I am alive! Bot is running..."

def run_server():
    try:
        app.run(host='0.0.0.0', port=8080)
    except:
        pass

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# ==========================================
# 3. نظام إدارة المشتركين
# ==========================================
USERS_FILE = "users.txt"

def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            f.write(str(ADMIN_ID) + "\n")
        return [ADMIN_ID]
    with open(USERS_FILE, "r") as f:
        users = []
        for line in f:
            try: users.append(int(line.strip()))
            except: pass
        if ADMIN_ID not in users: users.append(ADMIN_ID)
        return users

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        with open(USERS_FILE, "a") as f: f.write(f"{user_id}\n")
        return True
    return False

def remove_user(user_id):
    users = load_users()
    if user_id in users:
        users.remove(user_id)
        with open(USERS_FILE, "w") as f:
            for u in users: f.write(f"{u}\n")
        return True
    return False

ALLOWED_USERS = load_users()

# ==========================================
# 4. الثوابت الفلكية وقواعد الحظوظ
# ==========================================
TRANSIT_PLANETS = [
    ("الشمس",  "Sun Lng"), ("القمر",  "Moon Lng"), ("عطارد",  "Mercury Lng"),
    ("الزهرة", "Venus Lng"), ("المريخ", "Mars Lng"), ("المشتري", "Jupiter Lng"),
    ("زحل",    "Saturn Lng"), ("أورانوس","Uranus Lng"), ("نبتون",  "Neptune Lng"),
    ("بلوتو",  "Pluto Lng"), ("العقدة الشمالية", "Lunar North Node (True) Lng"),
    ("العقدة الجنوبية", "Lunar South Node (True) Lng"),
]

TRANSIT_TIMEFRAMES = {
    "القمر": "15m / 1H", "الشمس": "4H / 10H", "عطارد": "1H / 4H",
    "الزهرة": "1H / 4H", "المريخ": "4H / 1Day", "المشتري": "1W",
    "زحل": "1W", "أورانوس": "1M", "نبتون": "1M", "بلوتو": "1M",
    "العقدة الشمالية": "1W", "العقدة الجنوبية": "1W",
}

ZODIAC_SIGNS = [
    "الحمل", "الثور", "الجوزاء", "السرطان", "الأسد", "العذراء",
    "الميزان", "العقرب", "القوس", "الجدي", "الدلو", "الحوت"
]

PLANET_DIGNITIES = {
    "الشمس":   {"home": ["الأسد"], "exalt": ["الحمل"], "fall": ["الميزان"], "detriment": ["الدلو"]},
    "القمر":   {"home": ["السرطان"], "exalt": ["الثور"], "fall": ["العقرب"], "detriment": ["الجدي"]},
    "عطارد":   {"home": ["الجوزاء", "العذراء"], "exalt": ["العذراء"], "fall": ["الحوت"], "detriment": ["القوس", "الحوت"]},
    "الزهرة":  {"home": ["الثور", "الميزان"], "exalt": ["الحوت"], "fall": ["العذراء"], "detriment": ["العقرب", "الحمل"]},
    "المريخ":  {"home": ["الحمل", "العقرب"], "exalt": ["الجدي"], "fall": ["السرطان"], "detriment": ["الميزان", "الثور"]},
    "المشتري": {"home": ["القوس", "الحوت"], "exalt": ["السرطان"], "fall": ["الجدي"], "detriment": ["الجوزاء", "العذراء"]},
    "زحل":     {"home": ["الجدي", "الدلو"], "exalt": ["الميزان"], "fall": ["الحمل"], "detriment": ["السرطان", "الأسد"]},
}

GLOBAL_STOCK_DF = None
GLOBAL_TRANSIT_DF = None

# ==========================================
# 5. دوال مساعدة وتحليل
# ==========================================
def get_sign_name(degree):
    try: return ZODIAC_SIGNS[int(degree // 30) % 12]
    except: return ""

def get_sign_degree(degree):
    return degree % 30

def get_planet_status(planet_name, sign_name):
    if planet_name not in PLANET_DIGNITIES: return ""
    d = PLANET_DIGNITIES[planet_name]
    if sign_name in d["home"]: return " (في بيته 🏠)"
    if sign_name in d["exalt"]: return " (في شرفه 👑)"
    if sign_name in d["fall"]: return " (في هبوطه 🔻)"
    if sign_name in d["detriment"]: return " (في وباله ⚠️)"
    return ""

def angle_diff(a, b):
    d = abs(a - b) % 360
    if d > 180: d = 360 - d
    return d

def get_aspect_details(angle, orb=1.0):
    aspects = [
        (0,   "اقتران", "🔥"), 
        (60,  "تسديس",  "🟢"), 
        (90,  "تربيع",  "🔴"), 
        (120, "تثليث",  "🟢"), 
        (180, "مقابلة", "🔴"), 
    ]
    for exact, name, icon in aspects:
        diff = abs(angle - exact)
        if diff <= orb: return name, exact, diff, icon
    return None, None, None, None

# ==========================================
# 6. تحميل البيانات
# ==========================================
def load_data_once():
    global GLOBAL_STOCK_DF, GLOBAL_TRANSIT_DF
    if not os.path.exists("Stock.xlsx") or not os.path.exists("Transit.xlsx"): return 
    try:
        xls = pd.ExcelFile("Stock.xlsx")
        frames = []
        for sh in xls.sheet_names:
            df = xls.parse(sh, header=0)
            if df.shape[1] < 4: continue
            tmp = df.iloc[:, :4].copy()
            tmp.columns = ["السهم", "الكوكب", "البرج", "الدرجة الفلكية"]
            tmp["السهم"] = tmp["السهم"].fillna(sh).replace("", sh)
            tmp = tmp.dropna(subset=["الدرجة الفلكية"])
            tmp["الدرجة الفلكية"] = pd.to_numeric(tmp["الدرجة الفلكية"], errors='coerce')
            frames.append(tmp)
        if frames: GLOBAL_STOCK_DF = pd.concat(frames, ignore_index=True)
        
        df_trans = pd.read_excel("Transit.xlsx")
        df_trans["Datetime"] = pd.to_datetime(df_trans["Datetime"], errors="coerce")
        GLOBAL_TRANSIT_DF = df_trans.dropna(subset=["Datetime"])
    except Exception as e: print(f"Error loading data: {e}")

# ==========================================
# 7. الحسابات وتنسيق الرسالة
# ==========================================
def calc_aspects(stock_name, target_date):
    if GLOBAL_STOCK_DF is None or GLOBAL_TRANSIT_DF is None: return [], None
    start_dt = target_date.replace(hour=0, minute=0, second=0)
    end_dt = target_date.replace(hour=23, minute=59, second=59)

    mask_stock = GLOBAL_STOCK_DF["السهم"].astype(str).str.contains(stock_name, case=False, regex=False)
    sdf = GLOBAL_STOCK_DF.loc[mask_stock].copy()
    if sdf.empty: return [], None

    mask_time = (GLOBAL_TRANSIT_DF["Datetime"] >= start_dt) & (GLOBAL_TRANSIT_DF["Datetime"] <= end_dt)
    tdf = GLOBAL_TRANSIT_DF.loc[mask_time].copy()
    if tdf.empty: return [], sdf["السهم"].iloc[0]

    results = []
    for _, srow in sdf.iterrows():
        for _, trow in tdf.iterrows():
            for t_name, col in TRANSIT_PLANETS:
                if col not in trow or pd.isna(trow[col]): continue
                ang = angle_diff(srow["الدرجة الفلكية"], float(trow[col]))
                asp, exact, dev, icon = get_aspect_details(ang)
                if asp:
                    results.append({
                        "السهم": srow["السهم"], "كوكب السهم": srow["الكوكب"],
                        "برج السهم": srow["البرج"], "كوكب العبور": t_name,
                        "العلاقة": asp, "الزاوية التامة": exact, "الرمز": icon,
                        "درجة المولد": srow["الدرجة الفلكية"], "درجة العبور": float(trow[col]),
                        "الوقت": trow["Datetime"], "deviation": dev
                    })
    return results, sdf["السهم"].iloc[0]

def format_time_ar(dt):
    return dt.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")

def format_msg(stock_name, results, target_date):
    if not results: return f"لا توجد زوايا فلكية لسهم {stock_name} بتاريخ {target_date.strftime('%Y-%m-%d')}."
    
    df = pd.DataFrame(results).sort_values("الوقت")
    groups = df.groupby(["كوكب العبور", "كوكب السهم", "العلاقة"])
    
    summary_lines = [f"📌 **السهم:** {stock_name}\n📅 **التاريخ:** {target_date.strftime('%Y-%m-%d')}\n"]
    detail_lines = ["\n──────────────\n*(التفاصيل الكاملة)*\n"]

    for (tplanet, nplanet, aspect), g in groups:
        start_time = g.iloc[0]["الوقت"]
        end_time = g.iloc[-1]["الوقت"]
        best_row = g.loc[g['deviation'].idxmin()]
        exact_time = best_row["الوقت"]
        
        t_deg = best_row['درجة العبور']
        n_deg = best_row['درجة المولد']
        icon = best_row['الرمز']
        
        t_sign = get_sign_name(t_deg)
        t_status = get_planet_status(tplanet, t_sign)
        timeframe = TRANSIT_TIMEFRAMES.get(tplanet, "")

        summary_lines.append(
            f"⏳ **زمن العبور:** {format_time_ar(start_time)} ➔ {format_time_ar(end_time)}\n"
            f"✨ **{tplanet}** ({t_sign}) {aspect} **{nplanet}** ({get_sign_name(n_deg)})\n"
        )

        detail_lines.append(
            "──────────────\n"
            f"🔸 **{tplanet}** في **{t_sign} {int(get_sign_degree(t_deg))}°**{t_status}\n"
            f"🔸 **{nplanet}** مولد في **{get_sign_name(n_deg)} {int(get_sign_degree(n_deg))}°**\n"
            f"🔹 **العلاقة:** {aspect} {icon} ({int(best_row['الزاوية التامة'])}°)\n"
            f"🔹 **الفريم:** {timeframe}\n"
            f"⏰ {format_time_ar(start_time)} ➔ 🎯 {format_time_ar(exact_time)} ➔ 🏁 {format_time_ar(end_time)}\n"
        )

    full_msg = "".join(summary_lines) + "".join(detail_lines)
    return full_msg[:4000]

# ==========================================
# 8. لوحة التحكم والأوامر
# ==========================================
def get_stock_keyboard():
    markup = InlineKeyboardMarkup()
    if GLOBAL_STOCK_DF is not None:
        for stock in GLOBAL_STOCK_DF["السهم"].unique():
            markup.add(InlineKeyboardButton(stock, callback_data=f"view:{stock}:{datetime.date.today()}"))
    return markup

def get_nav_keyboard(stock_name, current_date_str):
    curr_date = datetime.datetime.strptime(current_date_str, "%Y-%m-%d").date()
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⬅️ السابق", callback_data=f"view:{stock_name}:{curr_date - datetime.timedelta(days=1)}"),
        InlineKeyboardButton("التالي ➡️", callback_data=f"view:{stock_name}:{curr_date + datetime.timedelta(days=1)}")
    )
    markup.row(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
    return markup

@bot.message_handler(commands=['add'])
def add_user_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        if save_user(int(message.text.split()[1])):
            global ALLOWED_USERS; ALLOWED_USERS = load_users()
            bot.reply_to(message, "✅ تم التفعيل")
        else: bot.reply_to(message, "⚠️ مشترك مسبقاً")
    except: bot.reply_to(message, "/add 123456")

@bot.message_handler(commands=['del'])
def del_user_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        if remove_user(int(message.text.split()[1])):
            global ALLOWED_USERS; ALLOWED_USERS = load_users()
            bot.reply_to(message, "❌ تم الحذف")
        else: bot.reply_to(message, "⚠️ غير موجود")
    except: bot.reply_to(message, "/del 123456")

@bot.message_handler(commands=['users'])
def list_users_cmd(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, f"👥 المشتركين: {len(load_users())}\n" + "\n".join(map(str, load_users())))

@bot.message_handler(commands=['myid'])
def myid_cmd(message):
    bot.reply_to(message, f"🆔 `{message.from_user.id}`", parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id not in ALLOWED_USERS:
        bot.reply_to(message, "⛔ للمشتركين فقط.")
        return
    bot.reply_to(message, "مرحباً! اختر سهماً:", reply_markup=get_stock_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.from_user.id not in ALLOWED_USERS: return
    data = call.data.split(":")
    
    if data[0] == "main_menu":
        bot.edit_message_text("اختر سهماً:", call.message.chat.id, call.message.message_id, reply_markup=get_stock_keyboard())
    elif data[0] == "view":
        stock, date_str = data[1], data[2]
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        res, real_name = calc_aspects(stock, target_date)
        try:
            bot.edit_message_text(format_msg(real_name or stock, res, target_date), 
                                  call.message.chat.id, call.message.message_id, 
                                  reply_markup=get_nav_keyboard(stock, date_str))
        except: pass

if __name__ == "__main__":
    load_data_once()
    keep_alive() # ✅ تشغيل السيرفر الوهمي
    print("BOT RUNNING...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(15)
