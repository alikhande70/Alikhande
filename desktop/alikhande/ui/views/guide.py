"""Guide — how to use this application safely, inside the application.

The operator should never have to open ``docs/`` to find out what UNBOUNDED
means, why an order needs two clicks, or why a win rate says "n/a". A trading
tool whose safety properties are only documented outside itself has documented
them for the wrong audience.

The content lives in ``GUIDE`` as structured sections rather than one blob of
markup, so the same data renders in either language and the test suite can
assert that both are complete.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ...i18n import current, t
from ..components import Card, StatusChip, label
from ..theme import PALETTE, SPACE

# Each section is (icon, English title, English body, Persian title, Persian body).
# Kept as one table rather than two catalogues so a section can never exist in
# one language and not the other — the test asserts every tuple is complete.
GUIDE: list[tuple[str, str, str, str, str]] = [
    (
        "◈",
        "What this application is",
        "A standalone scanner for MetaTrader 5 symbols. It reads prices, finds "
        "pullback and rejection setups at confirmed H1 structure, scores them "
        "against a fixed rule set, and sizes them under a hard risk policy.\n\n"
        "It runs as its own Windows program with its own window and database. "
        "MetaTrader is not part of its interface — but it must be RUNNING and "
        "LOGGED IN in the background, because the MetaTrader5 Python package is "
        "the only path MetaQuotes publishes for reaching an MT5 account from "
        "outside. There is no REST or FIX alternative for a retail account.",
        "این برنامه چیست",
        "یک اسکنر مستقل برای نمادهای متاتریدر ۵. قیمت‌ها را می‌خواند، ستاپ‌های "
        "پولبک و برگشت روی ساختار تأییدشدهٔ H1 را پیدا می‌کند، آن‌ها را با یک "
        "مجموعه قوانین ثابت امتیاز می‌دهد و حجمشان را زیر یک سیاست ریسک سخت‌گیرانه "
        "محاسبه می‌کند.\n\n"
        "این برنامه یک نرم‌افزار ویندوزی مستقل با پنجره و پایگاه‌دادهٔ خودش است. "
        "متاتریدر بخشی از رابط آن نیست — اما باید در پس‌زمینه **باز و لاگین‌شده** "
        "باشد، چون پکیج پایتونی MetaTrader5 تنها راهی است که مِتاکوتس برای دسترسی "
        "بیرونی به حساب MT5 منتشر کرده. برای حساب خرده‌فروشی هیچ جایگزین REST یا "
        "FIX وجود ندارد.",
    ),
    (
        "✓",
        "Before you connect",
        "1. Start MetaTrader 5 and log in to a DEMO account.\n"
        "2. Tools → Options → Expert Advisors → enable Algo Trading.\n"
        "3. Add every symbol you want scanned to Market Watch — a symbol that is "
        "not in Market Watch returns no history and will show as unresolved.\n"
        "4. Run `python -m alikhande doctor` if anything looks wrong; it reports "
        "exactly which of these is missing.",
        "قبل از اتصال",
        "۱. متاتریدر ۵ را باز کنید و وارد یک حساب **دمو** شوید.\n"
        "۲. Tools ← Options ← Expert Advisors ← گزینهٔ Algo Trading را فعال کنید.\n"
        "۳. هر نمادی را که می‌خواهید پویش شود به Market Watch اضافه کنید — نمادی "
        "که در Market Watch نباشد هیچ تاریخچه‌ای برنمی‌گرداند و «شناسایی‌نشده» "
        "نمایش داده می‌شود.\n"
        "۴. اگر چیزی درست به نظر نمی‌رسد `python -m alikhande doctor` را اجرا کنید؛ "
        "دقیقاً می‌گوید کدام‌یک از این‌ها کم است.",
    ),
    (
        "✕",
        "Real accounts are refused — three times",
        "This build never trades a live account, and that is structural rather "
        "than a setting:\n\n"
        "• There is no run mode that selects live trading — the enum has no such "
        "member, so no configuration mistake can reach it.\n"
        "• The execution engine returns REAL_ACCOUNT_BLOCKED on any non-demo "
        "account.\n"
        "• The MetaTrader adapter refuses again inside send_order, through code "
        "that shares nothing with the check above.\n\n"
        "Deleting one of those does not disable the others.",
        "حساب واقعی سه بار رد می‌شود",
        "این نسخه هرگز روی حساب واقعی معامله نمی‌کند، و این یک تنظیم نیست بلکه "
        "ساختاری است:\n\n"
        "• هیچ حالت اجرایی برای معاملهٔ واقعی وجود ندارد — enum اصلاً چنین عضوی "
        "ندارد، پس هیچ اشتباه پیکربندی به آن نمی‌رسد.\n"
        "• موتور اجرا روی هر حساب غیر دمو مقدار REAL_ACCOUNT_BLOCKED برمی‌گرداند.\n"
        "• آداپتور متاتریدر داخل send_order دوباره رد می‌کند، با کدی که هیچ "
        "اشتراکی با بررسی بالا ندارد.\n\n"
        "حذف یکی از این‌ها بقیه را غیرفعال نمی‌کند.",
    ),
    (
        "◆",
        "The three run modes",
        "ALERT ONLY (default) — scans and reports. No order can leave the "
        "application in this mode.\n\n"
        "SHADOW — builds the plan and runs the full preflight, then stops short "
        "of sending. It exercises the real code path rather than a simulation of "
        "it, so a shadow run tells you what a live run would have done.\n\n"
        "DEMO · ARM + CONFIRM — demo accounts only. Requires two separate "
        "deliberate actions on two different controls, with a 20-second expiry "
        "between them. No mode sends automatically; an application that fires on "
        "its own is not supervised, it is merely watched.",
        "سه حالت اجرا",
        "**فقط هشدار** (پیش‌فرض) — پویش و گزارش. در این حالت هیچ سفارشی از برنامه "
        "خارج نمی‌شود.\n\n"
        "**سایه** — طرح را می‌سازد و کل بررسی‌های پیش از ارسال را اجرا می‌کند، اما "
        "درست پیش از ارسال متوقف می‌شود. مسیر کد واقعی را اجرا می‌کند نه شبیه‌سازی "
        "آن، پس یک اجرای سایه به شما می‌گوید یک اجرای واقعی چه می‌کرد.\n\n"
        "**دمو · مسلح + تأیید** — فقط حساب دمو. دو اقدام جداگانه و عمدی روی دو "
        "کنترل متفاوت لازم دارد، با مهلت ۲۰ ثانیه‌ای بینشان. هیچ حالتی خودکار "
        "ارسال نمی‌کند؛ برنامه‌ای که خودش شلیک کند تحت نظارت نیست، فقط تماشا می‌شود.",
    ),
    (
        "◎",
        "Reading a signal",
        "The score is a RULE SCORE — a weighted sum of conditions the author "
        "believes matter. It is NOT a probability and must never be read as one.\n\n"
        "A real probability appears in the 'Historical' row, and only after at "
        "least 30 resolved trades on the same symbol, setup and rule version. "
        "Below that it shows 'n/a' with the sample count, because a win rate from "
        "eight trades is not evidence.\n\n"
        "The chart draws the supply and demand zones on the same price scale as "
        "the candles, with entry, stop and target as labelled lines. It is there "
        "so you can disagree with the system — trusting a claim you cannot check "
        "is not trust.",
        "خواندن یک سیگنال",
        "امتیاز یک **امتیاز قانونی** است — جمع وزنی شرط‌هایی که نویسنده مهم "
        "می‌داند. این **احتمال نیست** و هرگز نباید به‌عنوان احتمال خوانده شود.\n\n"
        "احتمال واقعی در ردیف «سابقهٔ آماری» ظاهر می‌شود، و فقط پس از دست‌کم ۳۰ "
        "معاملهٔ بسته‌شده روی همان نماد، ستاپ و نسخهٔ قوانین. زیر آن، «نامعلوم» با "
        "تعداد نمونه نشان داده می‌شود، چون نرخ برد از هشت معامله شواهد نیست.\n\n"
        "نمودار نواحی عرضه و تقاضا را روی همان مقیاس قیمت کندل‌ها می‌کشد، با ورود، "
        "حد ضرر و حد سود به‌صورت خطوط برچسب‌دار. این برای آن است که بتوانید با "
        "سیستم مخالفت کنید — اعتماد به ادعایی که نمی‌توانید بررسی کنید، اعتماد نیست.",
    ),
    (
        "!",
        "UNBOUNDED — the most important warning",
        "A position with no stop loss, or on a symbol that cannot be priced, has "
        "no computable worst case. It is NOT a zero-risk position.\n\n"
        "While any such position is open, every exposure percentage on the Risk "
        "view is a LOWER BOUND on your true exposure, and the application refuses "
        "all new risk. This is deliberate: the alternative — treating an "
        "unmeasurable position as free — makes the caps look roomiest precisely "
        "when the account is most exposed.",
        "بدون کران — مهم‌ترین هشدار",
        "پوزیشنی که حد ضرر ندارد، یا روی نمادی است که قیمت‌گذاری نمی‌شود، بدترین "
        "حالت قابل محاسبه ندارد. این پوزیشن **بدون ریسک نیست**.\n\n"
        "تا وقتی چنین پوزیشنی باز باشد، همهٔ درصدهای ریسک در نمای «ریسک» **کران "
        "پایین** ریسک واقعی شما هستند و برنامه هر ریسک جدیدی را رد می‌کند. این "
        "عمدی است: حالت جایگزین — یعنی رایگان فرض کردن پوزیشن غیرقابل‌اندازه‌گیری — "
        "باعث می‌شود سقف‌ها دقیقاً وقتی خالی‌ترین به نظر برسند که حساب بیشترین "
        "ریسک را دارد.",
    ),
    (
        "?",
        "UNKNOWN is not CLEAR",
        "The news gate has three states, not two. CLEAR means a calendar was "
        "consulted and the window is empty. BLOCKED means a relevant event was "
        "found. UNKNOWN means no calendar could be consulted at all.\n\n"
        "The MetaTrader5 Python package exposes no calendar API, so a live "
        "session has no source unless you supply one. UNKNOWN blocks trading in a "
        "live session and does not block in a replay, where it is flagged "
        "NEWS-BLIND instead — a backtest that refused every trade would make the "
        "filter unfalsifiable rather than safe.\n\n"
        "The same principle governs execution: an order the broker cannot account "
        "for is UNKNOWN, and UNKNOWN holds the submit gate shut, across restarts, "
        "until a human clears it.",
        "«نامعلوم» با «پاک» فرق دارد",
        "دروازهٔ اخبار سه حالت دارد، نه دو تا. **پاک** یعنی یک تقویم بررسی شد و "
        "پنجره خالی بود. **مسدود** یعنی رویداد مرتبطی پیدا شد. **نامعلوم** یعنی "
        "اصلاً هیچ تقویمی قابل بررسی نبود.\n\n"
        "پکیج پایتونی MetaTrader5 هیچ API تقویمی ندارد، پس یک نشست زنده تا وقتی "
        "خودتان منبعی ندهید هیچ منبعی ندارد. «نامعلوم» در نشست زنده معامله را "
        "مسدود می‌کند و در بازپخش مسدود نمی‌کند بلکه با برچسب «کور نسبت به اخبار» "
        "علامت می‌خورد — بک‌تستی که همهٔ معاملات را رد کند فیلتر را به‌جای ایمن، "
        "غیرقابل‌ابطال می‌کند.\n\n"
        "همین اصل بر اجرا هم حاکم است: سفارشی که بروکر نتواند حسابش را بدهد "
        "«نامعلوم» است، و «نامعلوم» دروازهٔ ارسال را بسته نگه می‌دارد — حتی پس از "
        "ری‌استارت — تا یک انسان آن را پاک کند.",
    ),
    (
        "◇",
        "What is NOT proven",
        "Be clear about the limits of this build:\n\n"
        "• The live broker path has never executed. No Windows machine with "
        "MetaTrader existed where it was written.\n"
        "• Indicator agreement with MetaTrader is derived from the documented "
        "algorithms, not measured against a terminal.\n"
        "• There is NO out-of-sample result on real data. Nothing here "
        "establishes that the strategy is profitable, and nothing claims it.\n\n"
        "The Health view lists all of this per subsystem, and every assumed "
        "parameter is labelled [ASSUMED] so you can go and check it.",
        "چه چیزی اثبات نشده",
        "دربارهٔ محدودیت‌های این نسخه صریح باشیم:\n\n"
        "• مسیر بروکر زنده هرگز اجرا نشده است. جایی که این کد نوشته شد هیچ ماشین "
        "ویندوزی با متاتریدر وجود نداشت.\n"
        "• تطابق اندیکاتورها با متاتریدر از روی الگوریتم‌های مستند استنتاج شده، نه "
        "اندازه‌گیری‌شده روی ترمینال.\n"
        "• **هیچ نتیجهٔ خارج از نمونه روی دادهٔ واقعی وجود ندارد.** هیچ چیز اینجا "
        "سودآوری استراتژی را اثبات نمی‌کند و هیچ ادعایی هم نمی‌شود.\n\n"
        "نمای «سلامت» همهٔ این‌ها را به تفکیک زیرسیستم فهرست می‌کند، و هر پارامتر "
        "فرض‌شده با برچسب [ASSUMED] مشخص است تا بتوانید بررسی‌اش کنید.",
    ),
    (
        "◎",
        "Reading the Scanner — what the percentage means",
        "The Scanner is the first screen, and its WIN RATE column shows one of "
        "three different things. The chip under each symbol says which.\n\n"
        "MEASURED — at least 30 resolved trades for this symbol and setup. A "
        "real percentage, shown with its 95% interval. This is the only case in "
        "which a headline percentage appears anywhere in the application.\n\n"
        "PROVISIONAL — between 8 and 29 resolved trades. The interval is shown "
        "and the headline percentage is withheld, because \"67%\" over nine "
        "trades reads as precision it does not have.\n\n"
        "NO DATA — fewer than 8. The rule score is shown instead, in grey, "
        "labelled \"not a probability\". A score of 98 means the setup matched "
        "the rules strongly. It does not mean it wins 98% of the time, and "
        "nothing in this application will ever imply that it does.\n\n"
        "Rows are ordered by what is KNOWN, not by what scores highest: a "
        "measured 58% ranks above an unmeasured 95.",
        "خواندن اسکنر — این درصد یعنی چه",
        "اسکنر اولین صفحه است و ستون «نرخ برد» آن یکی از سه چیز متفاوت را نشان "
        "می‌دهد. برچسب زیر هر نماد می‌گوید کدام‌یک.\n\n"
        "اندازه‌گیری‌شده — دست‌کم ۳۰ معاملهٔ بسته‌شده برای این نماد و این ستاپ. "
        "یک درصد واقعی، همراه با بازهٔ اطمینان ۹۵٪. این تنها حالتی است که در کل "
        "برنامه یک درصد به‌عنوان عدد اصلی نمایش داده می‌شود.\n\n"
        "موقت — بین ۸ تا ۲۹ معاملهٔ بسته‌شده. فقط بازه نشان داده می‌شود و عدد "
        "اصلی نمایش داده نمی‌شود، چون «۶۷٪» روی ۹ معامله دقتی را القا می‌کند که "
        "وجود ندارد.\n\n"
        "بدون داده — کمتر از ۸. به‌جایش امتیاز قانون با رنگ خاکستری و برچسب "
        "«یک احتمال نیست» نشان داده می‌شود. امتیاز ۹۸ یعنی ستاپ قوی با قوانین "
        "منطبق شده. یعنی ۹۸٪ مواقع برنده نیست، و هیچ‌جای این برنامه چنین چیزی "
        "را القا نخواهد کرد.\n\n"
        "ردیف‌ها بر اساس آنچه **دانسته** است مرتب می‌شوند، نه بالاترین امتیاز: "
        "یک ۵۸٪ اندازه‌گیری‌شده بالاتر از یک ۹۵ اندازه‌گیری‌نشده می‌نشیند.",
    ),
    (
        "◔",
        "Why the EDGE column matters more than the win rate",
        "A 70% win rate at 0.5 reward-to-risk loses money. A 40% win rate at 3.0 "
        "makes money. Win rate alone cannot tell you whether to take a trade; "
        "the quantity that decides it is expectancy per trade, in R:\n\n"
        "    expectancy = win rate × RR − (1 − win rate)\n\n"
        "which is positive exactly when the win rate beats 1 ÷ (1 + RR). That "
        "break-even figure sits under the RR column, so you can check the claim "
        "yourself: \"needs 29%, measuring 62%\" is something you can verify, and "
        "\"62%\" on its own is not.\n\n"
        "EDGE is computed from the CONSERVATIVE end of the interval, not the "
        "middle. A setup only counts as backed by evidence when even the "
        "pessimistic reading of its sample still pays.",
        "چرا ستون «برتری» از نرخ برد مهم‌تر است",
        "نرخ برد ۷۰٪ با نسبت ریسک به ریوارد ۰٫۵ ضرر می‌دهد. نرخ برد ۴۰٪ با نسبت "
        "۳٫۰ سود می‌دهد. نرخ برد به‌تنهایی نمی‌تواند بگوید وارد معامله بشوید یا "
        "نه؛ کمیتی که تصمیم می‌گیرد، امید ریاضی هر معامله بر حسب R است:\n\n"
        "    امید ریاضی = نرخ برد × RR − (۱ − نرخ برد)\n\n"
        "که دقیقاً وقتی مثبت است که نرخ برد از ۱ ÷ (۱ + RR) بیشتر باشد. آن عدد "
        "سربه‌سر زیر ستون RR نوشته شده تا خودتان ادعا را بسنجید: «۲۹٪ لازم است و "
        "۶۲٪ اندازه‌گیری شده» چیزی است که می‌شود راستی‌آزمایی کرد؛ «۶۲٪» به‌تنهایی نه.\n\n"
        "«برتری» از سرِ **محافظه‌کارانهٔ** بازه محاسبه می‌شود، نه از وسط آن. یک "
        "ستاپ فقط وقتی «متکی بر شواهد» شمرده می‌شود که حتی خوانش بدبینانهٔ "
        "نمونه‌اش هم سودده باشد.",
    ),
    (
        "◇",
        "Where the numbers come from",
        "Every rate carries its source, on the right of its row: from backtest, "
        "from live/demo, or mixed. This matters more than it looks. A result "
        "replayed over synthetic bars and a result from a demo account are both "
        "real records of something, but they are not evidence about the same "
        "thing, and a win rate whose source is hidden is how a backtest ends up "
        "quoted as live performance.\n\n"
        "On a fresh install everything reads NO DATA, because nothing has been "
        "traded yet. To start with measured numbers, run:\n\n"
        "    python -m alikhande calibrate\n\n"
        "which replays history into the same database the application reads and "
        "labels everything it writes \"from backtest\". Running it again "
        "REPLACES the previous calibration rather than adding to it — appending "
        "would double the sample behind every rate while describing the same "
        "trades twice.",
        "این اعداد از کجا می‌آیند",
        "هر نرخ، منبعش را در سمت خودش حمل می‌کند: از بک‌تست، از زنده/دمو، یا "
        "ترکیبی. این مهم‌تر از آن است که به نظر می‌رسد. نتیجه‌ای که روی داده‌های "
        "مصنوعی بازپخش شده و نتیجه‌ای که از حساب دمو آمده، هر دو سابقهٔ واقعیِ "
        "چیزی هستند — ولی شواهدی دربارهٔ یک چیز نیستند، و نرخ بردی که منبعش "
        "پنهان باشد دقیقاً همان‌جایی است که یک بک‌تست به‌عنوان عملکرد زنده نقل "
        "می‌شود.\n\n"
        "روی نصب تازه همه‌چیز «بدون داده» است، چون هنوز چیزی معامله نشده. برای "
        "شروع با اعداد اندازه‌گیری‌شده این را اجرا کنید:\n\n"
        "    python -m alikhande calibrate\n\n"
        "که تاریخچه را در همان پایگاه‌دادهٔ برنامه بازپخش می‌کند و هر چه می‌نویسد "
        "را «از بک‌تست» برچسب می‌زند. اجرای دوباره‌اش کالیبراسیون قبلی را "
        "**جایگزین** می‌کند نه اینکه به آن اضافه کند — افزودن، نمونهٔ پشت هر نرخ "
        "را دو برابر می‌کرد در حالی که همان معاملات را دو بار توصیف می‌کند.",
    ),
    (
        "⚙",
        "Presets — Default, Auto and Manual",
        "Default is the shipped values. None of them has been validated against "
        "your broker; the Health tab lists every one as [ASSUMED] or [POLICY]. "
        "Default is not \"the right settings\", it is the honest starting point.\n\n"
        "Auto starts from Default and tightens where the measured record "
        "justifies it — if recorded expectancy over a meaningful sample is "
        "negative, the scanner becomes more selective. It has no mechanism for "
        "becoming LESS selective. That is deliberate: an adaptive system that "
        "can relax its own thresholds will eventually relax them all the way "
        "down after a good run.\n\n"
        "Manual is your values, kept across restarts.\n\n"
        "All three are clamped to the same floors. Risk per trade cannot exceed "
        "its ceiling, reward-to-risk cannot go below 2.0, and the 30-sample "
        "minimum before a rate is displayed can be raised but never lowered. "
        "Those floors are enforced where the configuration is built, so editing "
        "the preferences file by hand does not get past them either.",
        "پیش‌تنظیم‌ها — پیش‌فرض، خودکار و دستی",
        "«پیش‌فرض» مقادیر ارسالی است. هیچ‌کدام روی بروکر شما اعتبارسنجی نشده؛ تب "
        "سلامت همه را با برچسب [ASSUMED] یا [POLICY] فهرست می‌کند. پیش‌فرض یعنی "
        "«تنظیمات درست» نیست، بلکه نقطهٔ شروعِ صادقانه است.\n\n"
        "«خودکار» از پیش‌فرض شروع می‌کند و هرجا سابقهٔ اندازه‌گیری‌شده اجازه بدهد "
        "سخت‌گیرتر می‌شود — اگر امید ریاضی ثبت‌شده روی نمونه‌ای معنادار منفی باشد، "
        "اسکنر انتخابی‌تر می‌شود. هیچ سازوکاری برای **کم‌سخت‌گیرتر** شدن ندارد. "
        "این عمدی است: سیستمی که بتواند آستانه‌های خودش را شل کند، بعد از یک دورهٔ "
        "خوب سرانجام آن‌ها را تا ته شل می‌کند.\n\n"
        "«دستی» مقادیر خودتان است که بین اجراها حفظ می‌شود.\n\n"
        "هر سه به یک کف مشترک محدود می‌شوند. ریسک هر معامله از سقفش بالاتر "
        "نمی‌رود، نسبت ریسک به ریوارد زیر ۲٫۰ نمی‌آید، و حداقل ۳۰ نمونه پیش از "
        "نمایش نرخ را می‌شود بالا برد ولی هرگز پایین نه. این کف‌ها همان‌جایی که "
        "پیکربندی ساخته می‌شود اعمال می‌شوند، پس ویرایش دستی فایل تنظیمات هم از "
        "آن‌ها عبور نمی‌کند.",
    ),
    (
        "▤",
        "Running a backtest, and what the answer is worth",
        "The Backtest view replays history through the SAME pipeline the live "
        "scanner uses — the same signal engine, the same risk planner, the same "
        "outcome tracker. A backtest with its own copy of the strategy tests "
        "the copy, so this one does not have one.\n\n"
        "The first control is the data source, and it decides what the result "
        "means:\n\n"
        "SAMPLE DATA is a seeded generator. Its trend is a sum of sine waves, "
        "so the series is predictable by construction and a trend-pullback "
        "strategy scores far better on it than on any market. A good result "
        "here means the software runs end to end. It means nothing else.\n\n"
        "BROKER FILES are MetaTrader CSV exports — press Ctrl+S on a chart and "
        "save as SYMBOL_TIMEFRAME.csv into one folder. Real prices, so the "
        "result is worth reading.\n\n"
        "Either way the report tells you what it does and does not establish: "
        "whether the sample cleared the 30-trade floor, whether the data was "
        "real, that a bar spanning both stop and target was scored as a STOP, "
        "and that nothing beyond the configured spread was modelled. Read that "
        "section before the win rate, not after.\n\n"
        "The run happens on its own thread, so the window stays usable, and "
        "Stop actually stops it — a cancelled run is labelled CANCELLED in the "
        "report, because a truncated backtest quoted as a finished one is a "
        "silently smaller sample.",
        "اجرای بک‌تست، و اینکه جوابش چقدر می‌ارزد",
        "نمای بک‌تست تاریخچه را از **همان** مسیری بازپخش می‌کند که اسکنر زنده "
        "استفاده می‌کند — همان موتور سیگنال، همان محاسبهٔ ریسک، همان ردیاب "
        "نتیجه. بک‌تستی که نسخهٔ جداگانه‌ای از استراتژی داشته باشد، آن نسخه را "
        "تست می‌کند؛ این یکی ندارد.\n\n"
        "اولین کنترل، منبع داده است و همان تعیین می‌کند نتیجه چه معنایی دارد:\n\n"
        "دادهٔ نمونه یک تولیدکنندهٔ داده است. روندش جمع چند موج سینوسی است، پس "
        "سری قیمت ذاتاً قابل‌پیش‌بینی است و استراتژی پولبک روی آن خیلی بهتر از "
        "هر بازاری نتیجه می‌گیرد. نتیجهٔ خوب اینجا یعنی نرم‌افزار سرتاسر کار "
        "می‌کند. هیچ معنای دیگری ندارد.\n\n"
        "فایل‌های بروکر خروجی CSV متاتریدرند — روی چارت Ctrl+S بزنید و با نام "
        "SYMBOL_TIMEFRAME.csv در یک پوشه ذخیره کنید. قیمت واقعی است، پس نتیجه "
        "ارزش خواندن دارد.\n\n"
        "در هر دو حالت گزارش می‌گوید چه چیزی را اثبات می‌کند و چه چیزی را نه: "
        "اینکه نمونه از کف ۳۰ معامله عبور کرده یا نه، اینکه داده واقعی بوده یا "
        "نه، اینکه کندلی که هم حد ضرر و هم حد سود را لمس کرده به‌عنوان حد ضرر "
        "حساب شده، و اینکه هیچ هزینه‌ای فراتر از اسپرد تنظیم‌شده مدل نشده. آن "
        "بخش را **قبل** از نرخ برد بخوانید، نه بعد از آن.\n\n"
        "اجرا روی نخ جداگانه‌ای انجام می‌شود تا پنجره قابل‌استفاده بماند، و "
        "دکمهٔ توقف واقعاً متوقفش می‌کند — اجرای متوقف‌شده در گزارش با برچسب "
        "CANCELLED مشخص می‌شود، چون بک‌تست ناتمامی که به‌عنوان تمام‌شده نقل شود "
        "یعنی یک نمونهٔ کوچک‌ترِ اعلام‌نشده.",
    ),
    (
        "◈",
        "Keyboard",
        "Ctrl+1 … Ctrl+9 — jump to a view\n"
        "Ctrl+L — switch language\n"
        "Ctrl+F — focus the symbol picker on the Signal view\n"
        "F1 — open this guide\n"
        "Ctrl+Q — quit",
        "میان‌برهای صفحه‌کلید",
        "‏Ctrl+1 تا Ctrl+9 — پرش به یک نما\n"
        "‏Ctrl+L — تعویض زبان\n"
        "‏Ctrl+F — فوکوس روی انتخابگر نماد در نمای سیگنال\n"
        "‏F1 — باز کردن همین راهنما\n"
        "‏Ctrl+Q — خروج",
    ),
]


def _rich(text: str) -> str:
    """Turn the guide's light markup into the HTML subset QLabel understands.

    The bodies are written with ``**emphasis**`` and blank-line paragraphs
    because that is readable in the source. Without this they render as literal
    asterisks, which looks like a bug in the one view whose job is to inspire
    confidence.
    """
    import html

    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")


class GuideView(QWidget):
    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        page = QWidget()
        page.setObjectName("Content")
        self._root = QVBoxLayout(page)
        self._root.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.xl)
        self._root.setSpacing(SPACE.md)
        scroll.setWidget(page)

        self._cards: list[tuple[Card, object, object]] = []
        for icon, en_title, en_body, fa_title, fa_body in GUIDE:
            card = Card()
            header = QHBoxLayout()
            header.setSpacing(SPACE.sm)
            chip = StatusChip(icon, "", "neutral")
            chip.setVisible(False)  # the icon lives in the title row instead
            title = label("", "H2")
            icon_label = label(icon, "H2", PALETTE.accent)
            header.addWidget(icon_label)
            header.addWidget(title, 1)
            card.add_layout(header)

            body = label("", "Body")
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setWordWrap(True)
            body.setStyleSheet(f"color: {PALETTE.ink_secondary}; line-height: 160%;")
            card.add(body)

            self._root.addWidget(card)
            self._cards.append((card, title, body))

        self._root.addStretch(1)
        self.retranslate()

    def retranslate(self) -> None:
        """Re-render the guide in the current language.

        Called on construction and whenever the language changes, so the guide
        never lags a language switch — which, for the one view whose whole job is
        explaining things, would be the worst place to lag.
        """
        persian = current().code == "fa"
        alignment = (
            Qt.AlignmentFlag.AlignRight if persian else Qt.AlignmentFlag.AlignLeft
        )
        for (_, title, body), section in zip(self._cards, GUIDE):
            _, en_title, en_body, fa_title, fa_body = section
            title.setText(fa_title if persian else en_title)
            body.setText(_rich(fa_body if persian else en_body))
            title.setAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
            body.setAlignment(alignment | Qt.AlignmentFlag.AlignTop)
