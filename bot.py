import telebot
import pandas as pd
from datetime import datetime, timedelta
import pytz
import re
# ========================
# إعدادات عامة
# =========================
TZ = pytz.timezone("Asia/Riyadh")   # توقيت السعودية
ORB_DEG = 1.0                       # سماح الزاوية ±1 درجة
# كواكب العبور (اسم عربي + اسم العمود في Transit.xlsx)
TRANSIT_PLANETS = [
    ("الشمس",  "Sun Lng"),
    ("القمر",  "Moon Lng"),
    ("عطارد",  "Mercury Lng"),
    ("الزهرة", "Venus Lng"),
    ("المريخ", "Mars Lng"),
    ("المشتري", "Jupiter Lng"),
    ("زحل",    "Saturn Lng"),
    ("أورانوس","Uranus Lng"),
    ("نبتون",  "Neptune Lng"),
    ("بلوتو",  "Pluto Lng"),
    ("العقدة الشمالية", "Lunar North Node (True) Lng"),
    ("العقدة الجنوبية", "Lunar South Node (True) Lng"),
]

# =========================
# قراءة ملف الأسهم بدون الاعتماد على أسماء الأعمدة
# =========================

def load_stock_data():
    """
    يقرأ Stock.xlsx
    - يمر على جميع الأوراق (نسيج، تاسي، الراجحي، ابو معطي، البابطين، أو أي ورقة أخرى)
    - يأخذ أول 4 أعمدة فقط ويعتبرها:
      [السهم، الكوكب، البرج، الدرجة الفلكية]
    - لو عمود السهم فاضي، يملأه باسم الورقة.
    """
    xls = pd.ExcelFile("Stock.xlsx")
    frames = []

    for sh in xls.sheet_names:
        df = xls.parse(sh, header=0)

        # لو الورقة أقل من 4 أعمدة نتجاهلها
        if df.shape[1] < 4:
            continue

        # أول 4 أعمدة فقط
        tmp = df.iloc[:, :4].copy()
        tmp.columns = ["السهم", "الكوكب", "البرج", "الدرجة الفلكية"]

        # لو عمود السهم فاضي ← نستخدم اسم الورقة
        tmp["السهم"] = tmp["السهم"].fillna(sh)
        tmp["السهم"] = tmp["السهم"].replace("", sh)

        # حذف الصفوف اللي ما فيها درجة
        tmp = tmp.dropna(subset=["الدرجة الفلكية"])

        # تحويل الدرجة إلى float
        tmp["الدرجة الفلكية"] = tmp["الدرجة الفلكية"].astype(float)

        frames.append(tmp)

    if not frames:
        raise Exception("ملف Stock.xlsx لا يحتوي على بيانات صالحة.")

    stock_df = pd.concat(frames, ignore_index=True)
    return stock_df

# =========================
# قراءة ملف العبور
# =========================

def load_transit_data():
    df = pd.read_excel("Transit.xlsx")
    # تحويل عمود التاريخ/الوقت
    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["Datetime"])
    return df

# =========================
# دوال الزوايا
# =========================

def angle_diff(a, b):
    """الفرق الزاوي 0–180 درجة"""
    d = abs(a - b) % 360
    if d > 180:
        d = 360 - d
    return d

def get_aspect(angle, orb=ORB_DEG):
    """تحديد نوع الزاوية من 0/90/120/180 ضمن أورب معيّن"""
    aspects = [
        (0,   "اقتران"),
        (90,  "تربيع"),
        (120, "تثليث"),
        (180, "مقابلة"),
    ]
    for exact, name in aspects:
        if abs(angle - exact) <= orb:
            return name
    return None

# =========================
# حساب الزوايا في المدى الزمني
# =========================

def calc_aspects_range(stock_df, transit_df, start_dt, end_dt):
    """
    يحسب كل الزوايا بين كواكب الأسهم وكواكب العبور
    داخل المدى الزمني [start_dt, end_dt]
    """
    mask = (transit_df["Datetime"] >= start_dt) & (transit_df["Datetime"] <= end_dt)
    tdf = transit_df.loc[mask].copy()
    if tdf.empty:
        return []

    results = []

    for _, stock in stock_df.iterrows():
        stock_name   = stock["السهم"]
        natal_planet = stock["الكوكب"]
        natal_deg    = float(stock["الدرجة الفلكية"])

        for _, row in tdf.iterrows():
            dt = row["Datetime"]

            for planet_name, col in TRANSIT_PLANETS:
                if col not in row or pd.isna(row[col]):
                    continue

                trans_deg = float(row[col])
                ang = angle_diff(natal_deg, trans_deg)
                asp = get_aspect(ang)
                if asp:
                    results.append({
                        "السهم": stock_name,
                        "كوكب السهم": natal_planet,
                        "كوكب العبور": planet_name,
                        "العلاقة": asp,
                        "درجة المولد": natal_deg,
                        "درجة العبور": trans_deg,
                        "الوقت": dt,
                    })
    return results

# =========================
# تلخيص (بداية / صميم / نهاية) لكل علاقة
# =========================

def summarize_aspects(results):
    """
    يجمع النتائج على مستوى:
    (السهم، كوكب السهم، كوكب العبور، نوع العلاقة)
    ويعطي:
    - بداية الزاوية
    - صميم الزاوية
    - نهاية الزاوية
    مع درجات العبور في هذه النقاط.
    """
    if not results:
        return []

    df = pd.DataFrame(results)
    groups = df.groupby(["السهم", "كوكب السهم", "كوكب العبور", "العلاقة"])

    summarized = []
    for (stock_name, natal_p, transit_p, aspect), g in groups:
        g = g.sort_values("الوقت")
        start_row = g.iloc[0]
        end_row   = g.iloc[-1]
        mid_row   = g.iloc[len(g) // 2]

        summarized.append({
            "السهم": stock_name,
            "كوكب السهم": natal_p,
            "كوكب العبور": transit_p,
            "العلاقة": aspect,
            "بداية": start_row["الوقت"],
            "صميم": mid_row["الوقت"],
            "نهاية": end_row["الوقت"],
            "درجة المولد": start_row["درجة المولد"],
            "درجة العبور بداية": start_row["درجة العبور"],
            "درجة العبور صميم":  mid_row["درجة العبور"],
            "درجة العبور نهاية": end_row["درجة العبور"],
        })
    return summarized

# =========================
# تنسيق الرسالة
# =========================

def format_message(summary, start_dt, end_dt):
    if not summary:
        return "لا توجد أي زوايا مفعّلة للأسهم في هذا المدى الزمني."

    header = (
        "العلاقات الفلكية للأسهم مع العبور\n"
        f"من {start_dt.strftime('%Y-%m-%d %H:%M')} "
        f"إلى {end_dt.strftime('%Y-%m-%d %H:%M')}\n\n"
    )

    lines = []
    max_len = 3500  # حد أقصى لطول الرسالة

    for r in summary:
        line = (
            f"📌 السهم: {r['السهم']}\n"
            f"🌗 كوكب السهم: {r['كوكب السهم']}\n"
            f"🪐 كوكب العبور: {r['كوكب العبور']}\n"
            f"🔺 العلاقة: {r['العلاقة']}\n"
            f"° درجة المولد: {r['درجة المولد']:.2f}\n"
            f"° درجة العبور (البداية): {r['درجة العبور بداية']:.2f}\n"
            f"° درجة العبور (الصميم): {r['درجة العبور صميم']:.2f}\n"
            f"° درجة العبور (النهاية): {r['درجة العبور نهاية']:.2f}\n"
            f"⏰ البداية: {r['بداية'].strftime('%Y-%m-%d %H:%M')}\n"
            f"⏰ الصميم: {r['صميم'].strftime('%Y-%m-%d %H:%M')}\n"
            f"⏰ النهاية: {r['نهاية'].strftime('%Y-%m-%d %H:%M')}\n"
            "----------------------\n"
        )

        if len(header) + sum(len(l) for l in lines) + len(line) > max_len:
            lines.append("… تم إخفاء باقي العلاقات بسبب طول الرسالة.\n")
            break

        lines.append(line)

    return header + "".join(lines)

# =========================
# دالة رئيسية لمعالجة أي مدى زمني
# =========================

def process_range(start_dt, end_dt):
    stock_df   = load_stock_data()
    transit_df = load_transit_data()
    aspects    = calc_aspects_range(stock_df, transit_df, start_dt, end_dt)
    summary    = summarize_aspects(aspects)
    return format_message(summary, start_dt, end_dt)

# =========================
# أوامر تيليجرام
# =========================

@bot.message_handler(commands=["start"])
def start_cmd(message):
    txt = (
        "🚀 أهلاً بك في البوت الفلكي الذكي!\n\n"
        "استخدم:\n"
        "/today – علاقات اليوم\n"
        "/range YYYY-MM-DD HH:MM YYYY-MM-DD HH:MM – لمدى زمني مخصص"
    )
    bot.reply_to(message, txt)

@bot.message_handler(commands=["today"])
def today_cmd(message):
    now = datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=1) - timedelta(minutes=1)

    # نحذف الـ timezone قبل المقارنة مع الإكسل
    s = start.replace(tzinfo=None)
    e = end.replace(tzinfo=None)

    try:
        txt = process_range(s, e)
    except Exception as ex:
        txt = f"حدث خطأ أثناء معالجة الطلب:\n{ex}"

    bot.reply_to(message, txt)

@bot.message_handler(commands=["range"])
def range_cmd(message):
    text = message.text.strip()

    # نستخدم Regex عشان نقبل الصيغة بدقة:
    m = re.match(
        r"^/range\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})$",
        text
    )

    if not m:
        usage = (
            "❌ الصيغة خاطئة.\n"
            "مثال:\n"
            "/range 2025-11-16 15:00 2025-11-17 15:00"
        )
        bot.reply_to(message, usage)
        return

    start_str, end_str = m.group(1), m.group(2)

    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
        end_dt   = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
    except ValueError as ex:
        bot.reply_to(message, f"صيغة التاريخ غير صحيحة:\n{ex}")
        return

    try:
        txt = process_range(start_dt, end_dt)
    except Exception as ex:
        txt = f"حدث خطأ أثناء معالجة الطلب:\n{ex}"

    bot.reply_to(message, txt)

print("BOT RUNNING...")
bot.polling(none_stop=True)

