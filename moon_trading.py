# ==========================================
# moon_trading.py - المضاربة اليومية على القمر (Excel Interpolation)
# ==========================================

import datetime
import pandas as pd
from config import ZODIAC_SIGNS
from transits import angle_diff, get_aspect_details

def get_moon_position_interpolated(transit_df, target_dt):
    """
    حساب موقع القمر بالتقريب (Interpolation) من ملف الترانزيت اليومي
    """
    # 1. البحث عن بيانات اليوم واليوم التالي
    target_date = target_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    next_date = target_date + datetime.timedelta(days=1)
    
    # التأكد من وجود عمود القمر
    if "Moon Lng" not in transit_df.columns:
        return None, None, 0
        
    row_today = transit_df[transit_df["Datetime"] == target_date]
    row_next = transit_df[transit_df["Datetime"] == next_date]
    
    if row_today.empty:
        return None, None, 0
        
    pos_today = float(row_today.iloc[0]["Moon Lng"])
    
    # إذا لم نجد بيانات الغد، نستخدم سرعة تقريبية (13 درجة/يوم)
    if row_next.empty:
        pos_next = pos_today + 13.2
    else:
        pos_next = float(row_next.iloc[0]["Moon Lng"])
        
    # التعامل مع الانتقال من الحوت (360) للحمل (0)
    if pos_next < pos_today:
        pos_next += 360
        
    # 2. حساب النسبة المئوية للوقت المنقضي من اليوم
    seconds_passed = (target_dt - target_date).total_seconds()
    total_seconds = 86400 # 24 hours
    ratio = seconds_passed / total_seconds
    
    # 3. Interpolation
    current_pos = pos_today + (pos_next - pos_today) * ratio
    current_pos = current_pos % 360
    
    # تحديد البرج
    sign_index = int(current_pos // 30)
    sign_name = ZODIAC_SIGNS[sign_index % 12]
    degree_in_sign = current_pos % 30
    
    return sign_name, degree_in_sign, current_pos

def check_moon_intraday(stock_df, transit_df, target_date=None):
    """
    فحص فرص المضاربة اللحظية للقمر مع أسهم القائمة
    """
    # تحديد التاريخ المستهدف (افتراضياً الآن بتوقيت السعودية)
    if target_date is None:
        now_ksa = datetime.datetime.now() + datetime.timedelta(hours=3)
    else:
        # إذا تم تمرير تاريخ، نستخدم منتصف ذلك اليوم كنقطة مرجعية
        now_ksa = target_date.replace(hour=12, minute=0, second=0)

    sign_name, moon_deg_sign, moon_abs_deg = get_moon_position_interpolated(transit_df, now_ksa)
    
    if sign_name is None:
        return [], "غير معروف", 0
    
    # تحديد عنصر البرج
    element = ""
    if sign_name in ["الحمل", "الأسد", "القوس"]:
        element = "ناري 🔥"
    elif sign_name in ["الثور", "العذراء", "الجدي"]:
        element = "ترابي ⛰️"
    elif sign_name in ["الجوزاء", "الميزان", "الدلو"]:
        element = "هوائي 💨"
    elif sign_name in ["السرطان", "العقرب", "الحوت"]:
        element = "مائي 💧"

    results = []
    
    for _, row in stock_df.iterrows():
        stock_planet_deg = row["الدرجة الفلكية"]
        stock_name = row["السهم"]
        planet_name = row["الكوكب"]
        
        angle = angle_diff(moon_abs_deg, stock_planet_deg)
        
        # نستخدم دالة get_aspect_details مع orb أوسع (2.5 درجة)
        asp_name, exact, dev, icon, asp_type, is_applying = get_aspect_details(angle, orb=2.5)
        
        # الشرط الجديد: تفعيل العلاقة إذا كانت في حدود 1 درجة (تفعيل أو صميم)
        if asp_name and is_applying and dev <= 1.0:
            status = ""
            advice = ""
            
            # الصميم (أقل من 0.1 درجة)
            if dev < 0.1:
                status = "🔥 **في الصميم (Now)**"
                if asp_type == "positive":
                    advice = "✅ **فرصة:** ردة فعل إيجابية متوقعة (ارتداد)"
                else:
                    advice = "⚠️ **انتبه:** ردة فعل سلبية متوقعة (جني أرباح)"
            
            # التفعيل (بين 0.1 و 1.0 درجة)
            else:
                status = "⏳ **تفعيل (قادم للصميم)**"
                if asp_type == "positive":
                    advice = "📈 **إيجابي:** السعر يتحرك مع الاتجاه"
                else:
                    advice = "📉 **سلبي:** ضغط بيعي يزداد"
            
            results.append({
                "السهم": stock_name,
                "الكوكب": planet_name,
                "العلاقة": asp_name,
                "الرمز": icon,
                "الحالة": status,
                "النصيحة": advice,
                "moon_sign": sign_name,
                "moon_deg": moon_deg_sign,
                "dev": dev,
                "element": element,
                "type": asp_type
            })
            
    return results, sign_name, moon_deg_sign, element
