def format_msg(stock_name, stock_results, sky_results, target_date):
    # حساب التقييم الذكي
    ai_rating, ai_color = calculate_ai_score(stock_results) if stock_results else ("⚪ (لا يوجد نشاط)", "⚪")

    msg = [
        f"📌 **السهم:** {stock_name}",
        f"📅 **التاريخ:** {target_date.strftime('%Y-%m-%d')}",
        f"🧠 **تقييم الفرصة:** {ai_rating}\n"
    ]

    msg.append("──────────────\n")
    
    # --- القسم الوحيد: التأثير على السهم ---
    msg.append(f"🎯 **التأثير على سهم {stock_name} (Transit to Natal):**")
    
    if not stock_results:
        msg.append(f"_(لا توجد زوايا فلكية مؤثرة على السهم اليوم)_")
    else:
        df_stock = pd.DataFrame(stock_results).sort_values("الوقت")
        groups_stock = df_stock.groupby(["كوكب العبور", "كوكب السهم", "العلاقة"])

        for (tplanet, nplanet, aspect), g in groups_stock:
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
            
            duration_hours = (end_time - start_time).total_seconds() / 3600
            time_str = "🔄 مستمر طوال اليوم" if duration_hours > 20 else f"{format_time_ar(start_time)} ➔ {format_time_ar(end_time)}"

            msg.append(
                f"\n🔹 **{tplanet}** (العبور) {aspect} {icon} **{nplanet}** (السهم)\n"
                f"   🔸 {tplanet} في {t_sign} {int(get_sign_degree(t_deg))}°{t_status}\n"
                f"   🔸 {nplanet} في {get_sign_name(n_deg)} {int(get_sign_degree(n_deg))}°\n"
                f"   ⏱️ **الفريم:** {timeframe}\n"
                f"   ⏰ {time_str}"
            )

    return "\n".join(msg)[:4000]
