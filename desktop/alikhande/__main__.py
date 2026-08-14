"""Command-line entry point.

``python -m alikhande ui``         launch the desktop application
``python -m alikhande calibrate``  seed the evidence base so the scanner can
                                   show measured rates on first launch
``python -m alikhande backtest``   replay bars through the pipeline
``python -m alikhande selftest``   run the test suite
``python -m alikhande doctor``     report what this machine can and cannot do

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
    """Report what this machine can and cannot do — by trying it.

    This is the first thing that runs on the Windows machine before a demo
    account is ever attached, so it is deliberately not a list of imports. It
    walks the same path the application walks, in the same order, and stops at
    the first thing that would stop the app:

        package -> terminal -> account -> algo trading -> symbols -> history

    Each step reports the *fix*, not just the failure. "cannot connect" is the
    single most confusing thing this application can say, because it has at
    least four unrelated causes and they need four different actions.

    Exit code 0 means the machine could run a demo session today; 1 means
    something named below has to be dealt with first.
    """
    import platform

    ok = True

    def line(name: str, status: str, hint: str = "") -> None:
        print(f"{name:<18}{status}")
        if hint:
            for part in hint.splitlines():
                print(f"{'':<18}{part}")

    line("platform", f"{platform.system()} {platform.release()} ({platform.machine()})")
    line("python", sys.version.split()[0])

    try:
        import PySide6

        line("PySide6", f"{PySide6.__version__} — the desktop UI can run")
    except ImportError:
        ok = False
        line("PySide6", "MISSING", "install with: pip install PySide6")

    if platform.system() != "Windows":
        line(
            "MetaTrader5",
            "unavailable — the package is Windows-only",
            "The UI, the backtest and every core engine still run here.\n"
            "Only live broker access needs Windows.",
        )
        return 0 if ok else 1

    from .adapters.mt5.gateway import MT5Gateway, probe_terminal

    try:
        import MetaTrader5 as mt5

        line("MetaTrader5", f"{mt5.__version__} installed")
    except ImportError:
        line("MetaTrader5", "MISSING", "install with: pip install MetaTrader5")
        return 1

    probe = probe_terminal()
    if not probe.available:
        line("terminal", f"NOT REACHABLE — {probe.reason}",
             "Start MetaTrader 5 and log in to the account you intend to use.")
        return 1
    line("terminal", f"connected — build {probe.build}")

    if not probe.account_known:
        ok = False
        line("account", "NOT READABLE",
             "The terminal answered but reported no account. Log in first.")
    else:
        kind = "DEMO" if probe.is_demo else "REAL"
        line("account", f"{probe.login} @ {probe.server} [{kind}]")
        if not probe.is_demo:
            line("", "This build never sends an order on a non-demo account.",
                 "Declare the Production environment to rehearse everything\n"
                 "except the send, or log in to a demo account to trade.")

    if not probe.trade_allowed:
        ok = False
        line("algo trading", "DISABLED",
             "Enable it: Tools -> Options -> Expert Advisors -> Allow algorithmic trading.")
    else:
        line("algo trading", "enabled")

    # ---- the real path, on one thread, exactly as the worker does it -------
    from .config import AppConfig
    from .core.enums import Timeframe

    gateway = MT5Gateway()
    try:
        gateway.ensure_connected()
    except Exception as error:
        line("gateway", f"FAILED — {error}")
        return 1

    try:
        config = AppConfig()
        resolved, missing, thin = [], [], []
        for requested in config.symbols:
            name = gateway.resolve_symbol(requested)
            if name is None:
                missing.append(requested)
                continue
            spec = gateway.symbol_spec(name)
            if spec is None or not spec.ready:
                missing.append(f"{requested} (no specification)")
                continue
            bars = gateway.bars(name, Timeframe.M5, config.scan.minimum_bars)
            if len(bars) < config.scan.minimum_bars:
                thin.append(f"{name}: {len(bars)}/{config.scan.minimum_bars} M5 bars")
            resolved.append(f"{requested} -> {name}")

        line("symbols", f"{len(resolved)} of {len(config.symbols)} resolved")
        for entry in resolved:
            line("", entry)
        if missing:
            ok = False
            line("", "NOT FOUND: " + ", ".join(missing),
                 "Add them to Market Watch in the terminal, or correct the names.")
        if thin:
            ok = False
            line("history", "INSUFFICIENT")
            for entry in thin:
                line("", entry)
            line("", "Open each symbol's M5 chart in MetaTrader and scroll back\n"
                     "so the terminal downloads the history.")
        elif resolved:
            line("history", f"at least {config.scan.minimum_bars} M5 bars per symbol")
    finally:
        gateway.shutdown()

    print()
    print("READY — this machine can run a demo session." if ok
          else "NOT READY — deal with the items marked above first.")
    return 0 if ok else 1


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


def _cmd_calibrate(args: argparse.Namespace) -> int:
    """Seed the application's evidence base from a replay.

    Solves a real chicken-and-egg problem. The scanner refuses to display a win
    rate below thirty resolved trades, which is correct — but it means a fresh
    install shows "NO DATA" against every symbol until the operator has run a
    demo account for weeks. That is a long time to spend looking at a screen
    that cannot tell you anything.

    This fills the gap without lying about where the numbers came from. The
    outcomes land in the database the application actually reads, under a run
    whose kind is ``REPLAY``, and every rate derived from them is labelled
    "from backtest" in the UI. The separation that used to be enforced by
    writing to a different file is now enforced by the query and stated on
    screen — which is strictly more use, because a file the operator never
    opens cannot tell them anything either.

    Re-running replaces the previous calibration rather than adding to it.
    Appending would double the sample behind every rate while describing the
    same trades twice, and the numbers would appear to be improving.
    """
    from .adapters.offline.gateway import OfflineGateway
    from .adapters.sqlite.database import Database
    from .adapters.sqlite.repositories import Repositories
    from .app.backtest import BACKTEST_TIMEFRAMES, Backtester
    from .config import AppConfig
    from .core.enums import RuntimeKind
    from .core.models import RuntimeContext
    from .core.runtime import persistence_plan
    from .ui.main_window import data_directory
    from .version import RULE_VERSION

    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    config = AppConfig().with_symbols(symbols)

    target = args.database
    if not target:
        # The live database, because that is the one the application opens.
        # Writing anywhere else would produce a calibration nothing reads.
        target = persistence_plan(
            RuntimeContext(kind=RuntimeKind.LIVE, is_production=True), data_directory()
        ).filename

    print(f"  database    {target}")
    print(f"  symbols     {', '.join(symbols)}")

    database = Database()
    database.open(target)
    repositories = Repositories(database)

    removed = repositories.purge_runs_of_kind(RuntimeKind.REPLAY.name)
    if removed:
        print(f"  replaced    {removed:,} signals from the previous calibration")

    gateway = OfflineGateway(equity=args.equity)
    gateway.load_synthetic(symbols, BACKTEST_TIMEFRAMES, args.h4_bars, seed=args.seed)

    result = Backtester(config).run(
        gateway,
        symbols,
        warmup_bars=args.warmup,
        max_steps=args.steps,
        data_source="synthetic",
        repositories=repositories,
    )
    print(result.report(min_sample=config.statistics.min_outcome_sample))

    print("  per symbol and setup, as the scanner will read it:")
    floor = config.statistics.min_outcome_sample
    for symbol in symbols:
        for setup in range(1, 5):
            wins, total, kinds = repositories.outcome_provenance(
                symbol, setup, RULE_VERSION
            )
            if not total:
                continue
            tier = "MEASURED" if total >= floor else "too few"
            print(
                f"    {symbol:<8} setup {setup}   {wins:>4}/{total:<5}"
                f" {tier:<9} {', '.join(sorted(kinds)) or 'unknown'}"
            )

    database.close()
    print(
        "\n  These are SYNTHETIC bars. They prove the machinery end to end and\n"
        "  say nothing whatever about this strategy's edge on real prices.\n"
        "  For evidence worth acting on, export real history from MetaTrader\n"
        "  and run:  alikhande backtest --data <folder> --database <file>"
    )
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
                # Consumed for its side effect: MetaTrader's export has a
                # header row that must not be parsed as a bar.
                next(reader, None)
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

    calibrate = sub.add_parser(
        "calibrate",
        help="seed the application's evidence base from a replay, so the "
        "scanner has measured (backtest-sourced) rates on first launch",
    )
    calibrate.add_argument("--symbols", default="XAUUSD,EURUSD,GBPUSD,USDJPY")
    calibrate.add_argument("--h4-bars", type=int, default=4000, dest="h4_bars")
    calibrate.add_argument("--warmup", type=int, default=10_000)
    calibrate.add_argument("--steps", type=int, default=None)
    calibrate.add_argument("--seed", type=int, default=20260806)
    calibrate.add_argument("--equity", type=float, default=10_000.0)
    calibrate.add_argument(
        "--database",
        default="",
        help="write here instead of the application's own database",
    )
    calibrate.set_defaults(func=_cmd_calibrate)

    doctor = sub.add_parser("doctor", help="report what this machine can do")
    doctor.set_defaults(func=_cmd_doctor)

    selftest = sub.add_parser("selftest", help="run the test suite")
    selftest.set_defaults(func=_cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
