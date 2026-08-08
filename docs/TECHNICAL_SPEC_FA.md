# مشخصات فنی Alikhande Scanner v1.2.0-rc1

این نسخه بر «قابلیت اثبات و پایداری» تمرکز دارد، نه افزایش تعداد اندیکاتورها.

- H4/H1/M15/M5 برای زمینه و تأیید چندتایم‌فریمی.
- حمایت/مقاومت ساختاری و هدف حداقل 2R.
- SQLite برای Signal/Plan/Execution/Outcome و بازیابی پس از Restart.
- `OnTradeTransaction` برای تطبیق نتیجه اجرای سفارش.
- `OrderCheck` و کنترل Drift/Stop/Exposure پیش از اجرای Demo.
- Real Account در v1.x به‌صورت Hard Block باقی می‌ماند.
- سه حالت Alert Only، Shadow و Demo Confirm.
- Market Regime ساده و قابل توضیح؛ بدون ML در این فاز.
- News Gate زنده برای رویدادهای High Impact؛ دیتاست تاریخی خبر برای Tester هنوز Gate بعدی است.
- پنل چندتب سبک و قابل کنترل داخل MT5.

مرز صداقت: تا زمانی که لاگ واقعی MetaEditor و تست Runtime وجود نداشته باشد، وضعیت این نسخه فقط Static Candidate است.
