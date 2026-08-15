"""Run a backtest from inside the application.

This existed only as a CLI subcommand, which meant the one thing that turns
this from a scanner into something you can *check* was reachable only by
opening a terminal. It is now a view.

## The data source is the first control, not a footnote

Two sources, and the difference between them is the difference between
"the software works" and "the strategy might work":

**Sample data** is a seeded generator. Its trend component is a sum of sine
waves, so the series is autocorrelated by construction and a trend-pullback
strategy scores far better on it than on any market. A high win rate here means
the pipeline runs. It means nothing else, and the banner above the report says
so in the same words every time.

**Broker files** are MetaTrader CSV exports (Ctrl+S on a chart), named
``SYMBOL_TIMEFRAME.csv``. These are real prices, so a result from them is worth
reading — subject to every caveat the report already prints about bar-resolution
fills and cost modelling.

The chosen source is shown as a chip that never disappears, because the single
most damaging mistake available on this screen is reading a synthetic result as
a real one.

## The run happens on a worker thread

A backtest is tens of thousands of iterations of the real pipeline; on the GUI
thread it would freeze the window for minutes, which is indistinguishable from
a crash. The worker reports progress about a hundred times over the run and
stops when asked — a long computation with no cancel button is one the operator
has to kill the application to escape.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...core.hashing import fnv1a
from ...i18n import fmt_count, t
from ..components import Card, StatusChip, label
from ..theme import PALETTE, SPACE


class BacktestWorker(QObject):
    """Runs a replay off the GUI thread and streams progress back."""

    progress = Signal(int, int)  # done, total
    finished = Signal(str, bool)  # report text, ok
    failed = Signal(str)

    def __init__(self, request: dict) -> None:
        super().__init__()
        self._request = request
        self._stop = False

    def stop(self) -> None:
        """Called from the GUI thread. A plain bool is enough — it is written
        by one thread and read by another, never incremented, so there is no
        read-modify-write to lose."""
        self._stop = True

    def run(self) -> None:
        try:
            self.finished.emit(*self._run())
        except Exception as error:  # a dead worker must not fail silently
            self.failed.emit(f"{type(error).__name__}: {error}")

    def _run(self) -> tuple[str, bool]:
        from ...adapters.offline.gateway import OfflineGateway
        from ...app.backtest import BACKTEST_TIMEFRAMES, Backtester

        request = self._request
        symbols = tuple(request["symbols"])
        config = AppConfig().with_symbols(symbols)

        gateway = OfflineGateway(equity=request["equity"])
        folder = request["folder"]
        if folder:
            source = _load_folder(gateway, Path(folder), symbols)
        else:
            gateway.load_synthetic(
                symbols, BACKTEST_TIMEFRAMES, request["h4_bars"], seed=request["seed"]
            )
            source = "synthetic"

        repositories = None
        database = None
        if request["persist"]:
            from ...adapters.sqlite.database import Database
            from ...adapters.sqlite.repositories import Repositories
            from ...core.enums import RuntimeKind

            database = Database()
            database.open(request["database"])
            repositories = Repositories(database)

        def progress(done: int, total: int) -> bool:
            self.progress.emit(done, total)
            return not self._stop

        # A fresh identity for this run, so the old calibration and the new one
        # can coexist in the database until we know the new one is worth
        # keeping.
        run_id = fnv1a(f"backtest|{time.time()}")
        result = None
        try:
            result = Backtester(config).run(
                gateway,
                symbols,
                warmup_bars=request["warmup"],
                data_source=source,
                repositories=repositories,
                progress=progress,
                run_id=run_id,
            )
        finally:
            if repositories is not None:
                # Replace, but only once there is something to replace *with*.
                #
                # This used to purge before replaying. An operator who pressed
                # Stop, or a replay that raised halfway, was then left with no
                # calibration at all and nothing to restore it from — the
                # previous evidence destroyed by an action that produced none.
                #
                # A cancelled run is discarded rather than kept: it describes a
                # smaller sample than was asked for, and stored under the same
                # label as a complete one it is indistinguishable from it.
                if result is not None and not result.cancelled:
                    repositories.purge_runs_of_kind(
                        RuntimeKind.REPLAY.name, keep_run_id=run_id
                    )
                else:
                    repositories.purge_run(run_id)
            if database is not None:
                database.close()

        return result.report(min_sample=config.statistics.min_outcome_sample), True


def _load_folder(gateway, folder: Path, symbols: tuple[str, ...]) -> str:
    """Load MetaTrader CSV exports, reusing the CLI's parser.

    Imported here rather than at module scope so this view does not drag the
    CLI module into the UI's import graph — and so the two can never drift into
    two different CSV dialects, which is exactly how a file that loads on the
    command line fails to load in the window.
    """
    from ...__main__ import _load_csv_bars

    return _load_csv_bars(gateway, folder, symbols)


class BacktestView(QWidget):
    """Data source, parameters, a run button and the report."""

    def __init__(self, config: AppConfig, database_path: str = "", parent=None):
        super().__init__(parent)
        self._config = config
        self._database_path = database_path
        self._folder = ""
        self._thread: QThread | None = None
        self._worker: BacktestWorker | None = None

        column = QVBoxLayout(self)
        column.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.lg)
        column.setSpacing(SPACE.md)

        column.addWidget(self._build_source_card())
        column.addWidget(self._build_parameters_card())
        column.addWidget(self._build_report_card(), 1)

        self._refresh_source()

    # ----------------------------------------------------------------- source
    def _build_source_card(self) -> QWidget:
        card = Card(t("bt.source"))

        row = QHBoxLayout()
        row.setSpacing(SPACE.sm)
        self._sample = QPushButton(t("bt.source.sample"))
        self._sample.setObjectName("Ghost")
        self._sample.clicked.connect(self._choose_sample)
        self._files = QPushButton(t("bt.source.files"))
        self._files.setObjectName("Ghost")
        self._files.clicked.connect(self._choose_folder)
        row.addWidget(self._sample)
        row.addWidget(self._files)
        row.addStretch(1)
        self._source_chip = StatusChip("◇", t("bt.source.sample"), "warning")
        row.addWidget(self._source_chip)
        card.add_layout(row)

        self._source_note = label("", "Body")
        self._source_note.setWordWrap(True)
        card.add(self._source_note)
        return card

    def _choose_sample(self) -> None:
        self._folder = ""
        self._refresh_source()

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, t("bt.source.files"))
        if chosen:
            self._folder = chosen
        self._refresh_source()

    def _refresh_source(self) -> None:
        """Chip, note and tone all move together.

        Amber for sample data is deliberate. It is not an error — it is the
        default and it works — but it is the state in which every number on
        this screen describes the software rather than a market, and that
        deserves to look different from the state in which they do not.
        """
        if self._folder:
            self._source_chip.set("✓", t("bt.source.files.chip"), "good")
            self._source_note.setText(t("bt.source.files.body", folder=self._folder))
        else:
            self._source_chip.set("!", t("bt.source.sample.chip"), "warning")
            self._source_note.setText(t("bt.source.sample.body"))

    # ------------------------------------------------------------- parameters
    def _build_parameters_card(self) -> QWidget:
        card = Card(t("bt.parameters"))

        self._symbols = QLineEdit(",".join(self._config.symbols[:2]))
        self._symbols.setPlaceholderText("EURUSD,XAUUSD")

        self._h4_bars = QSpinBox()
        self._h4_bars.setRange(200, 20_000)
        self._h4_bars.setSingleStep(100)
        self._h4_bars.setValue(700)

        self._warmup = QSpinBox()
        self._warmup.setRange(1_000, 100_000)
        self._warmup.setSingleStep(500)
        self._warmup.setValue(8_000)

        for key, widget in (
            ("bt.symbols", self._symbols),
            ("bt.h4_bars", self._h4_bars),
            ("bt.warmup", self._warmup),
        ):
            row = QHBoxLayout()
            row.setSpacing(SPACE.md)
            row.addWidget(label(t(key), "Body"), 1)
            widget.setFixedWidth(220)
            row.addWidget(widget)
            card.add_layout(row)

        self._persist = QCheckBox(t("bt.persist"))
        self._persist.setEnabled(bool(self._database_path))
        self._persist.setToolTip(
            t("bt.persist.tip") if self._database_path else t("bt.persist.unavailable")
        )
        card.add(self._persist)

        self._persist_note = label(t("bt.persist.body"), "Caption")
        self._persist_note.setWordWrap(True)
        card.add(self._persist_note)

        actions = QHBoxLayout()
        actions.setSpacing(SPACE.sm)
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setVisible(False)
        actions.addWidget(self._progress, 1)

        self._stop = QPushButton(t("bt.stop"))
        self._stop.setObjectName("Ghost")
        self._stop.setVisible(False)
        self._stop.clicked.connect(self._cancel)
        actions.addWidget(self._stop)

        self._run = QPushButton(t("bt.run"))
        self._run.setObjectName("Primary")
        self._run.clicked.connect(self._start)
        actions.addWidget(self._run)
        card.add_layout(actions)
        return card

    # ----------------------------------------------------------------- report
    def _build_report_card(self) -> QWidget:
        card = Card(t("bt.report"))
        self._report = QPlainTextEdit()
        self._report.setReadOnly(True)
        # Always left-to-right, whatever the interface direction. The report is
        # a fixed-column monospaced table whose meaning lives in its alignment
        # — the same reason the price chart never mirrors. Prose mirrors;
        # tabulated numbers do not.
        self._report.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._report.setPlainText(t("bt.report.empty"))
        card.add(self._report, 1)
        return card

    # -------------------------------------------------------------------- run
    def _start(self) -> None:
        if self._thread is not None:
            return

        symbols = [s.strip().upper() for s in self._symbols.text().split(",") if s.strip()]
        if not symbols:
            self._report.setPlainText(t("bt.error.no_symbols"))
            return

        request = {
            "symbols": symbols,
            "folder": self._folder,
            "h4_bars": self._h4_bars.value(),
            "warmup": self._warmup.value(),
            "seed": 20260806,
            "equity": 10_000.0,
            "persist": self._persist.isChecked() and bool(self._database_path),
            "database": self._database_path,
        }

        self._thread = QThread(self)
        self._worker = BacktestWorker(request)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._run.setEnabled(False)
        self._stop.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._report.setPlainText(t("bt.running"))
        self._thread.start()

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._stop.setEnabled(False)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.setMaximum(max(1, total))
        self._progress.setValue(done)
        self._progress.setFormat(
            t("bt.progress", done=fmt_count(done), total=fmt_count(total))
        )

    def _on_finished(self, report: str, _ok: bool) -> None:
        self._report.setPlainText(report)
        self._teardown()

    def _on_failed(self, message: str) -> None:
        self._report.setPlainText(t("bt.error.failed", message=message))
        self._teardown()

    def _teardown(self) -> None:
        """Join the thread before dropping it.

        Letting Qt destroy a still-running QThread prints a warning and can
        wedge the process — and this view can be torn down mid-run by a
        language or theme switch, so it has to be handled rather than hoped
        about.
        """
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
            self._thread = None
        self._worker = None
        self._run.setEnabled(True)
        self._stop.setVisible(False)
        self._stop.setEnabled(True)
        self._progress.setVisible(False)

    def shutdown(self) -> None:
        """Stop any run in flight. Called when the view is discarded."""
        if self._worker is not None:
            self._worker.stop()
        self._teardown()
