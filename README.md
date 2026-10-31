# GoldScalper

بوت سكالب للذهب (XAUUSD) على MetaTrader 5.

البوت مبني كإطار: إدارة المخاطرة والفلاتر وتنفيذ الصفقات جاهزة، والاستراتيجية قطعة تتبدل من الإعدادات. الاستراتيجية النهائية نحددها بعد الاختبارات.

## التركيب

1. افتح MetaTrader 5، ثم **File → Open Data Folder**.
2. انسخ مجلد `GoldScalper` كامل إلى `MQL5/Experts/`.
3. افتح `GoldScalper.mq5` في MetaEditor واضغط **Compile** (F7).
4. افتح شارت XAUUSD واسحب البوت عليه، وفعّل **Algo Trading**.

## الاختبار في Strategy Tester

1. **View → Strategy Tester** (Ctrl+R).
2. اختر `GoldScalper`، الرمز XAUUSD، والفريم M5.
3. Modelling: **Every tick based on real ticks** (الأدق للسكالب لأنه يستخدم السبريد الحقيقي).
4. غيّر `InpStrategy` والإعدادات، وقارن النتائج. للتحسين التلقائي استخدم تبويب **Optimization**، وخلّ فترة **Forward** (مثلاً 1/3) عشان تشوف هل النتيجة تصمد على بيانات ما شافها التحسين.

## الإعدادات

| المجموعة | الإعداد | الافتراضي | المعنى |
|---|---|---|---|
| Strategy | `InpStrategy` | Bollinger | الاستراتيجية: ارتداد بولنجر، أو تقاطع EMA |
| | `InpTimeframe` | M5 | فريم الإشارات |
| | `InpBandsPeriod` / `InpBandsDeviation` | 50 / 3.0 | إعدادات بولنجر |
| | `InpFastEma` / `InpSlowEma` | 9 / 21 | إعدادات تقاطع EMA |
| Exits | `InpStopAtr` | 3.0 | الستوب = ATR × هذا الرقم |
| | `InpRewardRisk` | 2.0 | الهدف = الستوب × هذا الرقم |
| | `InpMaxBars` | 30 | إغلاق الصفقة بعد عدد شموع (0 = بدون) |
| Risk | `InpRiskPercent` | 0.5 | نسبة الحساب المعرّضة للخسارة في كل صفقة |
| | `InpFixedLots` | 0 | لو أكبر من 0 يستخدم لوت ثابت بدل حساب المخاطرة |
| | `InpMaxTradesPerDay` | 10 | أقصى عدد صفقات في اليوم (0 = بدون حد) |
| | `InpMaxDailyLossPct` | 2.0 | يوقف التداول لباقي اليوم بعد هذه الخسارة % |
| Filters | `InpSessionStartHour` / `InpSessionEndHour` | 0 / 24 | ساعات التداول **بتوقيت سيرفر البروكر** |
| | `InpMaxSpreadPoints` | 60 | أقصى سبريد بالبوينت (يختلف حسب البروكر) |
| General | `InpMagic` | 26103101 | رقم يميّز صفقات البوت |

## طريقة العمل

- الإشارة تُحسب على **الشمعة المغلقة** فقط، مرة واحدة في كل شمعة جديدة.
- صفقة واحدة في نفس الوقت، بستوب وهدف محددين عند الفتح.
- حجم اللوت يُحسب بحيث ضرب الستوب يخسر `InpRiskPercent` من الحساب بالضبط.
- حدود اليوم (عدد الصفقات والخسارة) تُقرأ من سجل الحساب، فإعادة تشغيل البوت ما تصفّرها.

## إضافة استراتيجية جديدة

في `Strategies.mqh` أضف كلاس يرث من `CStrategy` ويرجع `SIGNAL_BUY` أو `SIGNAL_SELL` أو `SIGNAL_NONE` من `Signal()`، ثم أضفه إلى `ENUM_STRATEGY` و `switch` في `OnInit`.

## تنبيه

جرّب على حساب **ديمو** أولاً. لا توجد استراتيجية مثبتة الربح حتى الآن.
