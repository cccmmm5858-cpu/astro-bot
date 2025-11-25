import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import os
import sys
import datetime
import time

# استيراد الوحدات الجديدة
from config import TRANSIT_PLANETS, TRANSIT_TIMEFRAMES, ZODIAC_SIGNS, ASPECTS
from dignity import get_sign_name, get_sign_degree, format_planet_position, get_planet_dignity
from rating import calculate_opportunity_rating
from transits import calc_transit_to_transit, get_current_planetary_positions, angle_diff, get_aspect_details

# ==========================================
# 1. إعدادات البوت
# ==========================================
TOKEN = "8250995383:AAEp7GD_mbhMCbURlAAOZ2pASdKzs2ydNzo"

ALLOWED_USERS = [
    344671948  # ضع الـ ID الخاص بك هنا
]

try:
    bot = telebot.TeleBot(TOKEN)
except Exception as e:
    print(f"خطأ في التوكن: {e}")
    sys.exit(1)

# ==========================================
# 2. المتغيرات العامة
# ==========================================
GLOBAL_STOCK_DF = None
GLOBAL_TRANSIT_DF = None

# ==========================================
# 3. تحميل البيانات
# ==========================================
def load_data_once():
    global GLOBAL_STOCK_DF, GLOBAL_TRANSIT_DF
    print("جاري تحميل البيانات...")

    if not os.path.exists("Stock.xlsx") or not os.path.exists("Transit.xlsx"):
        print("❌ الملفات غير موجودة!")
        sys.exit(1)

    try:
        # Stock
        xls = pd.ExcelFile("Stock.xlsx")
        frames = []
        for sh in xls.sheet_names:
            df = xls.parse(sh, header=0)
            if df.shape[1] < 4:
                continue
            tmp = df.iloc[:, :4].copy()
            tmp.columns = ["السهم", "الكوكب", "البرج", "الدرجة الفلكية"]
            tmp["السهم"] = tmp["السهم"].fillna(sh).replace("", sh)
            tmp = tmp.dropna(subset=["الدرجة الفلكية"])
            tmp["الدرجة الفلكية"] = pd.to_numeric(tmp["الدرجة الفلكية"], errors='coerce')
            frames.append(tmp)

        if frames:
            GLOBAL_STOCK_DF = pd.concat(frames, ignore_index=True)
            print(f"✅ تم تحميل الأسهم: {len(GLOBAL_STOCK_DF)} صف.")
        else:
            print("⚠️ لا توجد بيانات صالحة في Stock.xlsx")

        # Transit
        df_trans = pd.read_excel("Transit.xlsx")
        df_trans["Datetime"] = pd.to_datetime(df_trans["Datetime"], errors="coerce")
        GLOBAL_TRANSIT_DF = df_trans.dropna(subset=["Datetime"])
        print(f"✅ تم تحميل العبور: {len(GLOBAL_TRANSIT_DF)} صف.")

    except Exception as e:
        print(f"❌ خطأ في التحميل: {e}")
        sys.exit(1)

# ==========================================
# 4. حساب العلاقات (Transit to Natal)
# ==========================================
def calc_aspects(stock_name, target_date):
    """حساب علاقات كواكب العبور مع كواكب السهم"""
    start_dt = target_date.replace(hour=0, minute=0, second=0)
    end_dt = target_date.replace(hour=23, minute=59, second=59)

    mask_stock = GLOBAL_STOCK_DF["السهم"].astype(str).str.contains(stock_name, case=False, regex=False)
    sdf = GLOBAL_STOCK_DF.loc[mask_stock].copy()

    if sdf.empty:
        return [], None

    mask_time = (GLOBAL_TRANSIT_DF["Datetime"] >= start_dt) & (GLOBAL_TRANSIT_DF["Datetime"] <= end_dt)
    tdf = GLOBAL_TRANSIT_DF.loc[mask_time].copy()

    if tdf.empty:
        return [], sdf["السهم"].iloc[0]

    results = []
    for _, srow in sdf.iterrows():
        for _, trow in tdf.iterrows():
            for t_name, col, t_icon in TRANSIT_PLANETS:
                if col not in trow or pd.isna(trow[col]):
                    continue

                ang = angle_diff(srow["الدرجة الفلكية"], float(trow[col]))
                asp, exact, dev, icon, asp_type = get_aspect_details(ang)

                if asp:
                    results.append({
                        "السهم": srow["السهم"],
                        "كوكب السهم": srow["الكوكب"],
                        "برج السهم": srow["البرج"],
                        "كوكب العبور": t_name,
                        "رمز العبور": t_icon,
                        "العلاقة": asp,
                        "الزاوية التامة": exact,
                        "الرمز": icon,
                        "النوع": asp_type,
                        "درجة المولد": srow["الدرجة الفلكية"],
                        "درجة العبور": float(trow[col]),
                        "الوقت": trow["Datetime"],
                        "deviation": dev
                    })

    return results, sdf["السهم"].iloc[0]

# ==========================================
# 5. تنسيق الرسالة المحسّنة
# ==========================================
def format_msg(stock_name, results, target_date):
    """تنسيق رسالة تحليل السهم مع التقييم والحالات"""
    if not results:
        return f"لا توجد زوايا فلكية لسهم {stock_name} بتاريخ {target_date.strftime('%Y-%m-%d')}."

    # حساب التقييم
    stars, rating_text, score = calculate_opportunity_rating(results)

    # الترويسة مع التقييم
    header = (
        f"📌 **السهم:** {stock_name}\n"
        f"📅 **التاريخ:** {target_date.strftime('%Y-%m-%d')}\n"
        f"🧠 **تقييم الفرصة:** {stars} ({rating_text})\n\n"
        f"──────────────\n\n"
        f"🎯 **التأثير على سهم {stock_name} (Transit to Natal):**\n\n"
    )

    # تجميع العلاقات
    df = pd.DataFrame(results).sort_values("الوقت")
    groups = df.groupby(["كوكب العبور", "كوكب السهم", "العلاقة"])

    lines = [header]

    for (tplanet, nplanet, aspect), g in groups:
        start_time = g.iloc[0]["الوقت"]
        end_time = g.iloc[-1]["الوقت"]
        best_row = g.loc[g['deviation'].idxmin()]
        exact_time = best_row["الوقت"]

        t_deg = best_row['درجة العبور']
        n_deg = best_row['درجة المولد']
        icon = best_row['الرمز']
        t_icon = best_row['رمز العبور']

        # تنسيق موقع كوكب العبور مع حالته
        transit_pos = format_planet_position(tplanet, t_deg)
        natal_sign = get_sign_name(n_deg)
        natal_deg = int(get_sign_degree(n_deg))

        # التحقق من الفريم
        is_continuous = (end_time - start_time).total_seconds() > 86400  # أكثر من يوم

        if is_continuous:
            time_text = "⏰ 🔄 مستمر طوال اليوم"
        else:
            time_text = (
                f"⏰ {start_time.strftime('%I:%M %p')} ➔ "
                f"🎯 {exact_time.strftime('%I:%M %p')} ➔ "
                f"{end_time.strftime('%I:%M %p')}"
            )

        block = (
            f"🔹 **{tplanet}** (العبور) {aspect} {icon} **{nplanet}** (السهم)\n"
            f"   🔸 {transit_pos}\n"
            f"   🔸 {nplanet} في {natal_sign} {natal_deg}°\n"
            f"   ⏱️ **الفريم:** {TRANSIT_TIMEFRAMES.get(tplanet, '-')}\n"
            f"   {time_text}\n\n"
        )
        lines.append(block)

    return "".join(lines)[:4000]

# ==========================================
# 6. تنسيق رسالة الزمن العام
# ==========================================
def format_transit_msg(target_datetime):
    """تنسيق رسالة الزمن العام (Transit to Transit)"""
    
    # الحصول على مواقع الكواكب
    positions = get_current_planetary_positions(GLOBAL_TRANSIT_DF, target_datetime)
    
    # حساب العلاقات بين الكواكب
    transit_aspects = calc_transit_to_transit(GLOBAL_TRANSIT_DF, target_datetime)
    
    # الترويسة
    header = (
        f"🌍 **الزمن العام - الآن**\n"
        f"📅 {target_datetime.strftime('%Y-%m-%d')} | "
        f"⏰ {target_datetime.strftime('%H:%M')}\n\n"
    )
    
    # مواقع الكواكب
    positions_text = "📍 **مواقع الكواكب:**\n"
    for planet_name, data in positions.items():
        planet_pos = format_planet_position(planet_name, data["degree"])
        positions_text += f"{data['icon']} {planet_pos}\n"
    
    # العلاقات النشطة
    aspects_text = "\n──────────────\n🔥 **العلاقات النشطة (Transit to Transit):**\n\n"
    
    if not transit_aspects:
        aspects_text += "لا توجد علاقات نشطة في الوقت الحالي.\n"
    else:
        for result in transit_aspects[:10]:  # أول 10 علاقات
            planet1_pos = format_planet_position(result["كوكب1"], result["درجة1"])
            planet2_pos = format_planet_position(result["كوكب2"], result["درجة2"])
            
            block = (
                f"🔹 {result['رمز1']} {planet1_pos}\n"
                f"   🔸 {result['رمز2']} {planet2_pos}\n"
                f"   🔹 {result['العلاقة']} {result['الرمز']} ({int(result['الزاوية التامة'])}°)\n"
                f"   ⏰ نشطة الآن\n\n"
            )
            aspects_text += block
    
    return (header + positions_text + aspects_text)[:4000]

# ==========================================
# 7. لوحة التحكم (الأزرار)
# ==========================================
def get_main_menu():
    """القائمة الرئيسية"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 تحليل الأسهم", callback_data="menu:stocks"),
        InlineKeyboardButton("🌍 الزمن العام", callback_data="menu:transits")
    )
    return markup

def get_stock_keyboard():
    """إنشاء أزرار بأسماء جميع الأسهم"""
    markup = InlineKeyboardMarkup()
    if GLOBAL_STOCK_DF is not None:
        unique_stocks = GLOBAL_STOCK_DF["السهم"].unique()
        for stock in unique_stocks:
            markup.add(InlineKeyboardButton(stock, callback_data=f"view:{stock}:{datetime.date.today()}"))
    markup.add(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
    return markup

def get_nav_keyboard(stock_name, current_date_str):
    """أزرار التنقل بين الأيام"""
    curr_date = datetime.datetime.strptime(current_date_str, "%Y-%m-%d").date()
    prev_date = curr_date - datetime.timedelta(days=1)
    next_date = curr_date + datetime.timedelta(days=1)

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⬅️ السابق", callback_data=f"view:{stock_name}:{prev_date}"),
        InlineKeyboardButton("التالي ➡️", callback_data=f"view:{stock_name}:{next_date}")
    )
    markup.row(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
    return markup

# ==========================================
# 8. معالجة الرسائل والضغطات
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id not in ALLOWED_USERS:
        bot.reply_to(message, "⛔ البوت للمشتركين فقط.")
        return
    
    welcome_text = (
        "🌟 **مرحباً بك في بوت الفلك المتقدم!**\n\n"
        "اختر ما تريد:\n"
        "📊 **تحليل الأسهم** - تحليل فلكي شامل للأسهم\n"
        "🌍 **الزمن العام** - مواقع الكواكب والعلاقات النشطة"
    )
    bot.reply_to(message, welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.from_user.id not in ALLOWED_USERS:
        return

    data = call.data.split(":")
    action = data[0]

    if action == "main_menu":
        welcome_text = (
            "🌟 **بوت الفلك المتقدم**\n\n"
            "اختر ما تريد:\n"
            "📊 **تحليل الأسهم**\n"
            "🌍 **الزمن العام**"
        )
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=welcome_text,
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

    elif action == "menu":
        menu_type = data[1]
        
        if menu_type == "stocks":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📊 **اختر سهماً لعرض تقريره الفلكي:**",
                reply_markup=get_stock_keyboard(),
                parse_mode="Markdown"
            )
        
        elif menu_type == "transits":
            now = datetime.datetime.now()
            transit_msg = format_transit_msg(now)
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔄 تحديث", callback_data="menu:transits"))
            markup.row(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=transit_msg,
                reply_markup=markup,
                parse_mode="Markdown"
            )

    elif action == "view":
        stock_name = data[1]
        date_str = data[2]
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")

        # حساب وعرض النتائج
        res, real_name = calc_aspects(stock_name, target_date)
        msg_text = format_msg(real_name if real_name else stock_name, res, target_date)

        # تحديث الرسالة الحالية
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=msg_text,
                reply_markup=get_nav_keyboard(stock_name, date_str),
                parse_mode="Markdown"
            )
        except:
            pass  # تجاهل الخطأ إذا كانت الرسالة لم تتغير

# ==========================================
# 9. التشغيل
# ==========================================
if __name__ == "__main__":
    load_data_once()
    print("🚀 BOT RUNNING... (Press Ctrl+C to stop)")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(5)
