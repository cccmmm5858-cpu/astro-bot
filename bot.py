import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import os
import sys
import datetime
import time

# استيراد الوحدات الجديدة
# استيراد الوحدات الجديدة
from config import TRANSIT_PLANETS, TRANSIT_TIMEFRAMES, ZODIAC_SIGNS, ASPECTS, TOKEN, ALLOWED_USERS
from dignity import get_sign_name, get_sign_degree, format_planet_position, get_planet_dignity
from rating import calculate_opportunity_rating
from dignity import get_sign_name, get_sign_degree, format_planet_position, get_planet_dignity
from rating import calculate_opportunity_rating
from transits import calc_transit_to_transit, get_current_planetary_positions, angle_diff, get_aspect_details
from moon_trading import check_moon_intraday

# ==========================================
# 1. إعدادات البوت
# ==========================================
# TOKEN & ALLOWED_USERS moved to config.py

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
# ==========================================
# 3. تحميل البيانات
# ==========================================
def load_data_once():
    global GLOBAL_STOCK_DF, GLOBAL_TRANSIT_DF
    print("Loading data...")

    if not os.path.exists("Stock.xlsx") or not os.path.exists("Transit.xlsx"):
        print("Files not found!")
        return False

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
            print(f"Stock data loaded: {len(GLOBAL_STOCK_DF)} rows.")
        else:
            print("No valid data in Stock.xlsx")

        # Transit
        df_trans = pd.read_excel("Transit.xlsx")
        df_trans["Datetime"] = pd.to_datetime(df_trans["Datetime"], errors="coerce")
        GLOBAL_TRANSIT_DF = df_trans.dropna(subset=["Datetime"])
        print(f"Transit data loaded: {len(GLOBAL_TRANSIT_DF)} rows.")
        return True

    except Exception as e:
        print(f"Error loading data: {e}")
        return False

def reload_data():
    """إعادة تحميل البيانات وتحديث المتغيرات العامة"""
    return load_data_once()

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
                asp, exact, dev, icon, asp_type, is_applying = get_aspect_details(ang)

                if asp:
                    # 1. Node Logic: Ignore Opposition if Node involved
                    if "Node" in t_name or "العقدة" in t_name:
                         if exact == 180: # Opposition
                             continue

                    # 2. Action/Reaction Logic
                    # If exact (deviation very small, e.g. < 0.1), reverse the sentiment
                    final_type = asp_type
                    reaction_note = ""
                    
                    if dev < 0.1: # Exact / Samim
                        if asp_type == "negative":
                            final_type = "positive"
                            reaction_note = " (ردة فعل إيجابية 🟢)"
                        elif asp_type == "positive":
                            final_type = "negative"
                            reaction_note = " (ردة فعل سلبية 🔴)"
                    
                    results.append({
                        "السهم": srow["السهم"],
                        "كوكب السهم": srow["الكوكب"],
                        "برج السهم": srow["البرج"],
                        "كوكب العبور": t_name,
                        "رمز العبور": t_icon,
                        "العلاقة": asp,
                        "الزاوية التامة": exact,
                        "الرمز": icon,
                        "النوع": final_type,
                        "ملاحظة": reaction_note,
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

    # --- Combined Rating Logic ---
    # 1. Calculate General Transit Rating
    transit_aspects = calc_transit_to_transit(GLOBAL_TRANSIT_DF, target_date)
    gen_score = 0
    for t_asp in transit_aspects:
        if t_asp['النوع'] == 'positive': gen_score += 1
        elif t_asp['النوع'] == 'negative': gen_score -= 1
    
    gen_rating = "positive" if gen_score >= 0 else "negative"
    stock_rating = "positive" if score >= 0 else "negative"

    combined_status = ""
    if gen_rating == "negative" and stock_rating == "positive":
        combined_status = "⚠️ الحركة ضعيفة (الزمن العام سلبي)"
    elif gen_rating == "negative" and stock_rating == "negative":
        combined_status = "⛔ طحن خطر (الزمن العام والسهم سلبيان)"
    elif gen_rating == "positive" and stock_rating == "positive":
        combined_status = "🚀 صعود (الزمن العام والسهم إيجابيان)"
    else:
        combined_status = "⚖️ متباين"

    # الترويسة مع التقييم
    header = (
        f"📌 **السهم:** {stock_name}\n"
        f"📅 **التاريخ:** {target_date.strftime('%Y-%m-%d')}\n"
        f"🧠 **تقييم الفرصة:** {stars} ({rating_text})\n"
        f"📊 **الوضع العام:** {combined_status}\n\n"
        f"──────────────\n\n"
        f"🎯 **الفواصل للزوايا السلبيه والايجابيه هذا اليوم:**\n\n"
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
            f"   📝 **الحالة:** {best_row.get('ملاحظة', '')}\n"
            f"   {time_text}\n\n"
        )
        lines.append(block)

        lines.append(block)

    # إضافة ملخص الزمن العام (بدون تغيير تفاصيل السهم)
    lines.append("──────────────\n🌍 **الزمن العام (Transit to Transit):**\n")
    # نستخدم دالة format_transit_msg لكن نحتاج لتعديلها لترجع نصاً مختصراً أو نستخدمها كما هي
    # هنا سنقوم بجلب العلاقات فقط وإضافتها
    if not transit_aspects:
        lines.append("لا توجد علاقات عامة نشطة.\n")
    else:
        for result in transit_aspects[:5]: # عرض أهم 5 علاقات عامة
             planet1_pos = format_planet_position(result["كوكب1"], result["درجة1"])
             planet2_pos = format_planet_position(result["كوكب2"], result["درجة2"])
             lines.append(
                f"🔹 {result['رمز1']} {result['العلاقة']} {result['الرمز']} {result['رمز2']}\n"
             )

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
    markup.row(InlineKeyboardButton("🌙 المضاربة اليومية (القمر)", callback_data="menu:moon"))
    markup.row(InlineKeyboardButton("🔄 تحديث البيانات", callback_data="admin:reload"))
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

        elif menu_type == "moon":
            if GLOBAL_STOCK_DF is None or GLOBAL_TRANSIT_DF is None:
                bot.answer_callback_query(call.id, "⚠️ لا توجد بيانات أسهم أو عبور محملة!")
                return

            results, moon_sign, moon_deg = check_moon_intraday(GLOBAL_STOCK_DF, GLOBAL_TRANSIT_DF)
            
            header = (
                f"🌙 **المضاربة اليومية على القمر**\n"
                f"📍 **موقع القمر:** {moon_sign} {int(moon_deg)}°\n"
                f"⏰ **الوقت:** {(datetime.datetime.now() + datetime.timedelta(hours=3)).strftime('%H:%M')}\n\n"
                f"──────────────\n\n"
            )
            
            if not results:
                msg_text = header + "لا توجد فرص مضاربة نشطة حالياً (فريم 15د - 1س).\n"
            else:
                msg_text = header
                for res in results:
                    msg_text += (
                        f"🔹 **{res['السهم']}** ({res['الكوكب']})\n"
                        f"   {res['العلاقة']} {res['الرمز']} القمر\n"
                        f"   {res['الحالة']}\n"
                        f"   💡 {res['النصيحة']}\n\n"
                    )
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔄 تحديث", callback_data="menu:moon"))
            markup.row(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=msg_text[:4000],
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

    elif action == "admin":
        if data[1] == "reload":
            bot.answer_callback_query(call.id, "جاري تحديث البيانات...")
            success = reload_data()
            if success:
                bot.send_message(call.message.chat.id, "✅ تم تحديث البيانات بنجاح!")
            else:
                bot.send_message(call.message.chat.id, "❌ حدث خطأ أثناء تحديث البيانات.")

# ==========================================
# 9. التشغيل
# ==========================================
if __name__ == "__main__":
    load_data_once()
    print("BOT RUNNING... (Press Ctrl+C to stop)")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(5)
