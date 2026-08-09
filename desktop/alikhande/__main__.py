"""Command-line entry point.

``python -m alikhande ui``        launch the desktop application
``python -m alikhande backtest``  replay bars through the pipeline
``python -m alikhande selftest``  run the test suite
``python -m alikhande doctor``    report what this machine can and cannot do

``doctor`` exists because the single most confusing failure mode of this
application is environmental: MetaTrader not running, Algo Trading off, or the
``MetaTrader5`` package missing because the machine is not Windows. Those
produce very different fixes and should not all surface as "cannot connect".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_doctor(_: argparse.Namespace) -> int:
    import platform

    print(f"platform         {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"python           {sys.version.split()[0]}")

    try:
        import PySide6  # noqa: F401

        print("PySide6          installed — the desktop UI can run")
    except ImportError:
        print("PySide6          MISSING — install with: pip install PySide6")

    if platform.system() != "Windows":
        print(
            "MetaTrader5      unavailable — the package is Windows-only.\n"
            "                 The UI, the backtest and every core engine still run\n"
            "                 here; only live broker access needs Windows."
        )
        return 0

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("MetaTrader5      MISSING — install with: pip install MetaTrader5")
        return 0

    print(f"MetaTrader5      {mt5.__version__} installed")
    if not mt5.initialize():
        code, message = mt5.last_error()
        print(f"terminal         NOT REACHABLE ({code}: {message})")
        print("                 Start MetaTrader 5, log in, and enable Algo Trading.")
        return 1

    terminal = mt5.terminal_info()
    account = mt5.account_info()
    print(f"terminal         connected — build {terminal.build}")
    print(f"algo trading     {'ENABLED' if terminal.trade_allowed else 'DISABLED — enable it'}")
    if account is not None:
        kind = {0: "DEMO", 1: "REAL", 2: "CONTEST"}.get(int(account.trade_mode), "?")
        print(f"account          {account.login} @ {account.server} [{kind}]")
        if kind != "DEMO":
            print("                 This build refuses to trade a non-demo account.")
    mt5.shutdown()
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    from .adapters.offline.gateway import OfflineGateway
    from .app.backtest import BACKTEST_TIMEFRAMES, Backtester
    from .config import AppConfig

    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    config = AppConfig().with_symbols(symbols)

    gateway = OfflineGateway(equity=args.equity)
    if args.data:
        source = _load_csv_bars(gateway, Path(args.data), symbols)
    else:
        gateway.load_synthetic(symbols, BACKTEST_TIMEFRAMES, args.h4_bars, seed=args.seed)
        source = "synthetic"

    repositories = None
    database = None
    if args.database:
        from .adapters.sqlite.database import Database
        from .adapters.sqlite.repositories import Repositories

        database = Database()
        database.open(args.database)
        repositories = Repositories(database)

    result = Backtester(config).run(
        gateway,
        symbols,
        warmup_bars=args.warmup,
        max_steps=args.steps,
        step=args.step,
        data_source=source,
        repositories=repositories,
    )
    print(result.report(min_sample=config.statistics.min_outcome_sample))

    if database is not None:
        database.close()
        print(f"\n  database written to {args.database}")
    return 0


def _load_csv_bars(gateway, folder: Path, symbols: tuple[str, ...]) -> str:
    """Load MetaTrader CSV exports named ``<SYMBOL>_<TIMEFRAME>.csv``.

    Accepts MetaTrader's own export layout: a header row, then
    ``DATE TIME OPEN HIGH LOW CLOSE TICKVOL VOL SPREAD`` separated by tabs or
    commas. Anything it cannot parse is a hard failure rather than a skipped
    row — a backtest quietly missing a third of its bars is worse than one that
    refuses to start.
    """
    import csv
    from datetime import datetime, timezone

    from .adapters.offline.gateway import Bar
    from .core.enums import Timeframe

    loaded = 0
    for symbol in symbols:
        for timeframe in (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
            path = folder / f"{symbol}_{timeframe.label}.csv"
            if not path.exists():
                continue
            bars: list[Bar] = []
            with path.open(newline="", encoding="utf-8-sig") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                delimiter = "\t" if "\t" in sample else ","
                reader = csv.reader(handle, delimiter=delimiter)
                header = next(reader, None)
                for line, row in enumerate(reader, start=2):
                    row = [c for c in row if c != ""]
                    if len(row) < 6:
                        continue
                    stamp = f"{row[0]} {row[1]}".replace(".", "-")
                    try:
                        moment = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
                        bars.append(
                            Bar(
                                time=int(moment.timestamp()),
                                open=float(row[2]),
                                high=float(row[3]),
                                low=float(row[4]),
                                close=float(row[5]),
                                tick_volume=int(float(row[6])) if len(row) > 6 else 0,
                            )
                        )
                    except ValueError as error:
                        raise SystemExit(
                            f"{path}:{line}: could not parse row {row!r} ({error}). "
                            "Export from MetaTrader with Ctrl+S on the chart."
                        ) from error
            if bars:
                gateway.load_bars(symbol, timeframe, bars)
                loaded += len(bars)

    if loaded == 0:
        raise SystemExit(
            f"no CSV bars found under {folder}. Expected files named like "
            f"{symbols[0]}_M5.csv, {symbols[0]}_H1.csv ..."
        )
    return f"broker export ({folder}, {loaded:,} bars)"


def _cmd_selftest(_: argparse.Namespace) -> int:
    import unittest

    root = Path(__file__).resolve().parent.parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), top_level_dir=str(root))
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


def _cmd_ui(args: argparse.Namespace) -> int:
    try:
        from .ui.main_window import run_application
    except ImportError as error:
        print(f"the desktop UI needs PySide6: {error}", file=sys.stderr)
        print("install it with:  pip install PySide6", file=sys.stderr)
        return 2
    return run_application(offline=args.offline)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="alikhande",
        description="Alikhande Scanner Desktop — a standalone scanner that uses "
        "MetaTrader 5 as a data and execution gateway.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ui = sub.add_parser("ui", help="launch the desktop application")
    ui.add_argument(
        "--offline",
        action="store_true",
        help="run against synthetic data with no MetaTrader terminal",
    )
    ui.set_defaults(func=_cmd_ui)

    back = sub.add_parser("backtest", help="replay bars through the live pipeline")
    back.add_argument("--symbols", default="EURUSD,XAUUSD")
    back.add_argument(
        "--data",
        default="",
        help="folder of MetaTrader CSV exports (SYMBOL_TIMEFRAME.csv). "
        "Omit to use synthetic bars, which prove the machinery and nothing else.",
    )
    back.add_argument("--h4-bars", type=int, default=1500, dest="h4_bars")
    back.add_argument("--warmup", type=int, default=10_000)
    back.add_argument("--steps", type=int, default=None)
    back.add_argument("--step", type=int, default=1)
    back.add_argument("--seed", type=int, default=20260806)
    back.add_argument("--equity", type=float, default=10_000.0)
    back.add_argument("--database", default="", help="write results to this SQLite file")
    back.set_defaults(func=_cmd_backtest)

    doctor = sub.add_parser("doctor", help="report what this machine can do")
    doctor.set_defaults(func=_cmd_doctor)

    selftest = sub.add_parser("selftest", help="run the test suite")
    selftest.set_defaults(func=_cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
