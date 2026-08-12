# Installing on Windows / نصب روی ویندوز

Two versions of the same instructions. English first, Persian below.

---

## English

### What you need first

| | |
|---|---|
| Windows | 10 or 11, 64-bit |
| Python | 3.10 or newer, **with "Add python.exe to PATH" ticked during install** |
| Disk | about 700 MB while building, ~180 MB for the finished application |
| MetaTrader 5 | only for live broker access — everything else works without it |

The PATH checkbox is off by default in the Python installer and is the single
most common reason the build fails. If you have already installed Python
without it, re-run the installer and choose *Modify*.

### Install

1. Download the project (green **Code** button → *Download ZIP*) and unzip it.
2. Open the `desktop\packaging` folder.
3. Double-click **`INSTALL_WINDOWS.bat`**.

That script installs the dependencies, runs the 222-test suite, checks the
environment, and only then builds the executable. It refuses to package a build
whose tests fail — an `.exe` is the thing you actually run, and shipping one
from a red suite is how an untested build reaches a live terminal.

When it finishes you will have:

```
desktop\dist\AlikhandeScanner\AlikhandeScanner.exe
```

Right-click it → *Send to* → *Desktop (create shortcut)* if you want an icon.

### If you prefer the command line

```powershell
cd desktop
python -m pip install -r requirements.txt
python -m alikhande doctor          # what is and is not available here
python -m alikhande                 # run the UI straight from source
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

Running from source is worth knowing about: you do not have to build an `.exe`
at all. `python -m alikhande` gives you the same application.

### First launch — why everything says NO DATA

The Scanner refuses to show a win rate until it has at least 30 resolved trades
for that symbol and setup. That floor is deliberate, and on a fresh install it
means every row reads **NO DATA** with a rule score in grey beside it.

To start with measured numbers:

```powershell
cd desktop
python -m alikhande calibrate
```

That replays history into the same database the application reads and labels
everything it writes **from backtest**, which is what every row will then say.
Running it again *replaces* the previous calibration rather than adding to it.

The bars it ships are synthetic. They prove the whole pipeline end to end and
say nothing about this strategy's edge on real prices. For evidence worth
acting on, export real history from MetaTrader (Ctrl+S on a chart) and run:

```powershell
python -m alikhande backtest --data <folder> --database <file>
```

### Connecting to a broker

The app runs fully offline out of the box — the UI, the analysis engines and
the backtest all work with no broker at all. For live data and orders:

1. Start MetaTrader 5 and log in to a **demo** account.
2. *Tools → Options → Expert Advisors* → enable **Algo Trading**.
3. Add every symbol you want scanned to *Market Watch*.
4. Leave the terminal running. The Python package talks to it over local IPC;
   there is no supported REST or FIX path for retail accounts.

The build refuses to send an order to a non-demo account. That refusal is
structural — it is not a setting you can turn off in the UI.

### Verifying it yourself

Do not take the test count on trust. Run it:

```powershell
cd desktop
python -m unittest discover -s tests -t .
python -m alikhande backtest --symbols EURUSD XAUUSD --steps 2000
```

### When something goes wrong

| Symptom | Cause |
|---|---|
| `'python' is not recognized` | PATH checkbox — see above |
| `ModuleNotFoundError: PySide6` | dependencies not installed; run `pip install -r requirements.txt` |
| `MetaTrader5 unavailable` in doctor | expected on Linux/macOS; on Windows, install with `pip install MetaTrader5` |
| The app starts but shows no live data | MetaTrader 5 is not running, not logged in, or Algo Trading is off |
| Antivirus quarantines the `.exe` | unsigned PyInstaller bundles are a known false positive; run from source instead if this bothers you |

---

<div dir="rtl">

## فارسی

### پیش‌نیازها

| | |
|---|---|
| ویندوز | ۱۰ یا ۱۱، ۶۴ بیتی |
| پایتون | ۳٫۱۰ یا بالاتر، **با تیک زدن گزینه‌ی «Add python.exe to PATH» هنگام نصب** |
| فضای دیسک | حدود ۷۰۰ مگابایت هنگام ساخت، حدود ۱۸۰ مگابایت برای برنامه‌ی نهایی |
| متاتریدر ۵ | فقط برای اتصال زنده به بروکر — بقیه‌ی بخش‌ها بدون آن کار می‌کنند |

آن تیک PATH به‌صورت پیش‌فرض خاموش است و شایع‌ترین دلیل شکست نصب همین است.
اگر پایتون را قبلاً بدون آن نصب کرده‌اید، نصب‌کننده را دوباره اجرا کنید و
گزینه‌ی *Modify* را بزنید.

### نصب

۱. پروژه را دانلود کنید (دکمه‌ی سبز **Code** ← *Download ZIP*) و از حالت فشرده خارج کنید.
۲. پوشه‌ی `desktop\packaging` را باز کنید.
۳. روی **`INSTALL_WINDOWS.bat`** دوبار کلیک کنید.

این اسکریپت وابستگی‌ها را نصب می‌کند، هر ۲۲۲ تست را اجرا می‌کند، محیط را
بررسی می‌کند و تنها پس از آن فایل اجرایی را می‌سازد. اگر تست‌ها رد شوند،
از ساختن خروجی خودداری می‌کند — چون فایل اجرایی همان چیزی است که واقعاً
اجرا می‌شود و ساختن آن از یک بیلد قرمز، دقیقاً همان راهی است که یک نسخه‌ی
تست‌نشده به ترمینال زنده می‌رسد.

پس از پایان، این فایل را خواهید داشت:

```
desktop\dist\AlikhandeScanner\AlikhandeScanner.exe
```

اگر میان‌بر روی دسکتاپ می‌خواهید: کلیک راست ← *Send to* ← *Desktop (create shortcut)*.

### اگر خط فرمان را ترجیح می‌دهید

```powershell
cd desktop
python -m pip install -r requirements.txt
python -m alikhande doctor          ‎# چه چیزی در دسترس هست و چه چیزی نیست
python -m alikhande                 ‎# اجرای مستقیم رابط کاربری از روی سورس
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

این نکته ارزش دانستن دارد: لازم نیست حتماً فایل اجرایی بسازید. دستور
`python -m alikhande` دقیقاً همان برنامه را اجرا می‌کند.

### اولین اجرا — چرا همه‌جا نوشته «بدون داده»

اسکنر تا وقتی دست‌کم ۳۰ معاملهٔ بسته‌شده برای آن نماد و آن ستاپ نداشته باشد،
نرخ برد نشان نمی‌دهد. این کف عمدی است، و روی نصب تازه یعنی همهٔ ردیف‌ها
**بدون داده** می‌خوانند و کنارشان امتیاز قانون به رنگ خاکستری می‌آید.

برای شروع با اعداد اندازه‌گیری‌شده:

```powershell
cd desktop
python -m alikhande calibrate
```

این دستور تاریخچه را در همان پایگاه‌داده‌ای که برنامه می‌خواند بازپخش می‌کند و
هر چه می‌نویسد را **از بک‌تست** برچسب می‌زند — همان چیزی که بعداً در هر ردیف
خواهید دید. اجرای دوباره‌اش کالیبراسیون قبلی را جایگزین می‌کند، نه اینکه به آن
اضافه کند.

داده‌هایی که همراه دارد مصنوعی هستند. کل مسیر را سرتاسر اثبات می‌کنند و
هیچ چیزی دربارهٔ برتری این استراتژی روی قیمت‌های واقعی نمی‌گویند. برای شواهدی
که ارزش عمل‌کردن داشته باشد، تاریخچهٔ واقعی را از متاتریدر خروجی بگیرید
(‏Ctrl+S روی چارت) و این را اجرا کنید:

```powershell
python -m alikhande backtest --data <folder> --database <file>
```

### اتصال به بروکر

برنامه به‌صورت پیش‌فرض کاملاً آفلاین کار می‌کند — رابط کاربری، موتورهای
تحلیل و بک‌تست همگی بدون هیچ بروکری کار می‌کنند. برای داده و سفارش زنده:

۱. متاتریدر ۵ را اجرا کنید و وارد یک حساب **دمو** شوید.
۲. مسیر *Tools → Options → Expert Advisors* و فعال‌کردن **Algo Trading**.
۳. هر نمادی که می‌خواهید اسکن شود را به *Market Watch* اضافه کنید.
۴. ترمینال را باز نگه دارید. پکیج پایتون از طریق IPC محلی با آن صحبت می‌کند؛
   برای حساب‌های خرد هیچ مسیر REST یا FIX پشتیبانی‌شده‌ای وجود ندارد.

این نسخه از ارسال سفارش به حساب غیردمو خودداری می‌کند. این محدودیت ساختاری
است، نه تنظیمی که بشود از داخل رابط کاربری خاموشش کرد.

### خودتان راستی‌آزمایی کنید

عدد تست‌ها را باور نکنید؛ اجرایش کنید:

```powershell
cd desktop
python -m unittest discover -s tests -t .
python -m alikhande backtest --symbols EURUSD XAUUSD --steps 2000
```

### وقتی چیزی درست کار نکرد

| نشانه | علت |
|---|---|
| `'python' is not recognized` | همان تیک PATH — بالاتر توضیح داده شد |
| `ModuleNotFoundError: PySide6` | وابستگی‌ها نصب نشده‌اند؛ `pip install -r requirements.txt` را اجرا کنید |
| پیام `MetaTrader5 unavailable` در doctor | روی لینوکس/مک طبیعی است؛ روی ویندوز با `pip install MetaTrader5` نصب کنید |
| برنامه بالا می‌آید ولی داده‌ی زنده ندارد | متاتریدر ۵ اجرا نیست، لاگین نیست، یا Algo Trading خاموش است |
| آنتی‌ویروس فایل اجرایی را قرنطینه می‌کند | مثبت کاذبِ شناخته‌شده برای بسته‌های امضانشده‌ی PyInstaller؛ اگر آزاردهنده است، برنامه را از روی سورس اجرا کنید |

</div>
