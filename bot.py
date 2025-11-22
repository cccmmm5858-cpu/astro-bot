def format_msg(stock_name, results, target_date):
    if not results: return f"لا توجد زوايا فلكية لسهم {stock_name} بتاريخ {target_date.strftime('%Y-%m-%d')}."
    
    df = pd.DataFrame(results).sort_values("الوقت")
    groups = df.groupby(["كوكب العبور", "كوكب السهم", "العلاقة"])
    
    # الجزء الأول: الملخص
    summary_lines = [f"📌 **السهم:** {stock_name}\n📅 **التاريخ:** {target_date.strftime('%Y-%m-%d')}\n"]
    
    # الجزء الثاني: التفاصيل
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

        # إضافة للملخص
        summary_lines.append(
            f"⏳ **زمن العبور:** {format_time_ar(start_time)} ➔ {format_time_ar(end_time)}\n"
            f"✨ **{tplanet}** ({t_sign}) {aspect} **{nplanet}** ({get_sign_name(n_deg)})\n"
        )

        # إضافة للتفاصيل
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
