"""Design tokens and the application stylesheet.

Tokens first, stylesheet second. Every colour, size and space in the UI comes
from here, so a change is made once rather than hunted through widget code.

## What changed in 2.2, and why

The previous system was strictly monochrome: every surface, border and control
was a pure neutral, so that the few coloured things left on screen were the
only ones carrying meaning. The reasoning was sound and it is kept. The result
was not: with no elevation between them, a card and the window behind it were
two greys a few points apart, nothing on screen sat in front of anything else,
and an interface with no depth reads as unfinished rather than as restrained.

So the discipline stays and the execution changes. Colour is still spent only
on meaning. **Depth** is what carries structure now — five surface steps from
the window plane to a raised popover, each with its own border, so hierarchy is
visible without tinting anything.

## Colour is assigned by job, and only four jobs qualify

**Direction — LONG vs SHORT.** Carried primarily by an arrow and a word, never
by hue alone. A blue/amber pair backs them up so a column can be scanned at
speed. Deliberately not green/red: green/red is spent below on permission, and
a SHORT painted red reads as an error rather than a direction.

**State — gates, guards, evidence tiers.** The fixed status palette. These four
are *not* a categorical palette and do not pass a categorical validation, which
is expected: warning and serious sit in the same warm family by design. The
mitigation is structural — **every status colour in this UI ships with an icon
and a text label**, so hue never carries meaning on its own. ``StatusChip``
enforces that by taking the icon and the label as required arguments.

**Magnitude — rule score, realised R.** A *neutral* ramp for score, because a
rule score is not a probability and a saturated ramp makes it look like one
reading off a calibrated instrument. Grey says "more of something" without
claiming to say what. A diverging pair for realised R, where the sign genuinely
is the message.

**Interaction — and this one is new.** A single indigo, used for exactly four
things: the active navigation indicator, the focus ring, the primary action,
and a selected row. It is deliberately a hue no other job uses. Indigo, rather
than a blue, because LONG is already a blue and the two would be confusable in
peripheral vision — which is precisely where a focus ring and a direction
column both get read.

That is the whole colour budget. Nothing else on screen is tinted.

## Switching

``PALETTE`` is a proxy that forwards to whichever palette is active, so the
hundred or so ``PALETTE.ink`` reads across the widget layer need no change and
a theme switch takes effect without a restart. Qt stylesheets are strings
captured at apply time, so the window re-applies :func:`stylesheet` and rebuilds
its views — the same mechanism the language switch already uses.

## Type

A real scale with real weight contrast. Uniform 13px everywhere is what makes
an interface read as a data dump: nothing is emphasised, so the eye has nowhere
to land. Numbers that are meant to be compared down a column are set in the
monospace face, because proportional digits in a price column do not align and
a column that does not align cannot be scanned.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str = "dark"
    dark: bool = True

    # ---- surfaces, furthest back to furthest forward --------------------
    # Five steps, not two. Each is a real elevation the eye can order, and the
    # cool cast (a few points of blue in every neutral) is what keeps a large
    # dark field from reading as flat charcoal.
    plane: str = "#080A0F"  # the window behind everything
    surface: str = "#0E1117"  # cards
    surface_high: str = "#151922"  # nested panels, inputs, table headers
    surface_hover: str = "#1D222C"
    surface_raised: str = "#242A36"  # popovers, tooltips, the thing on top
    border: str = "#1B2029"
    border_strong: str = "#2C3340"

    # ---- ink ------------------------------------------------------------
    ink: str = "#E9ECF2"
    ink_secondary: str = "#AAB2C0"
    ink_muted: str = "#7E8797"
    ink_faint: str = "#5A6270"

    # ---- identity: direction (icon + word always accompany these) --------
    long: str = "#4E9DE0"
    short: str = "#DE9448"
    long_wash: str = "rgba(78,157,224,0.13)"
    short_wash: str = "rgba(222,148,72,0.13)"

    # ---- interactive: one indigo, four uses -----------------------------
    # Not a blue. LONG is a blue, and a focus ring and a direction column are
    # both read peripherally, which is exactly where two blues merge.
    accent: str = "#7D7AF0"
    accent_hover: str = "#9491FF"
    accent_ink: str = "#080A0F"
    accent_wash: str = "rgba(125,122,240,0.14)"
    accent_soft: str = "rgba(125,122,240,0.28)"
    focus: str = "#7D7AF0"

    # ---- state: the fixed status palette (icon + label always) ----------
    good: str = "#43B581"
    warning: str = "#D9A441"
    serious: str = "#D3813F"
    critical: str = "#E05561"
    good_wash: str = "rgba(67,181,129,0.13)"
    warning_wash: str = "rgba(217,164,65,0.13)"
    serious_wash: str = "rgba(211,129,63,0.13)"
    critical_wash: str = "rgba(224,85,97,0.13)"
    # Unknown is not a status. It is the absence of one, and it must never
    # borrow a status colour — an unseen calendar that renders amber reads as
    # "mildly concerning" when the truth is "nobody looked".
    unknown: str = "#7E8797"
    unknown_wash: str = "rgba(126,135,151,0.10)"

    # ---- magnitude: a neutral ramp, strongest to faintest ----------------
    seq_100: str = "#E9ECF2"
    seq_250: str = "#AAB2C0"
    seq_400: str = "#7E8797"
    seq_550: str = "#5A6270"
    seq_700: str = "#3B4250"

    # ---- chart chrome ---------------------------------------------------
    # The plot area is a step *below* its card rather than above it. A chart is
    # a window onto something, and a window that sits proud of the wall it is
    # cut into looks like a sticker.
    chart_plane: str = "#0A0D13"
    grid: str = "#151A23"
    axis: str = "#262D39"
    crosshair: str = "#4A5364"
    candle_up: str = "#C3CAD8"
    candle_down: str = "#5A6270"

    # ---- type -----------------------------------------------------------
    font: str = "'Segoe UI Variable', 'Segoe UI', 'Inter', 'DejaVu Sans', system-ui, sans-serif"
    mono: str = "'Cascadia Mono', 'JetBrains Mono', 'Consolas', 'DejaVu Sans Mono', monospace"


DARK = Palette()

LIGHT = Palette(
    name="light",
    dark=False,
    plane="#FFFFFF",
    surface="#FBFBFD",
    surface_high="#F3F4F7",
    surface_hover="#E9EBF0",
    surface_raised="#FFFFFF",
    border="#E4E6EC",
    border_strong="#CBD0DA",
    ink="#0C0F16",
    ink_secondary="#3D4453",
    ink_muted="#69707F",
    ink_faint="#98A0AF",
    long="#2A6FB5",
    short="#A8621F",
    long_wash="rgba(42,111,181,0.10)",
    short_wash="rgba(168,98,31,0.10)",
    accent="#5B57D8",
    accent_hover="#4844C4",
    accent_ink="#FFFFFF",
    accent_wash="rgba(91,87,216,0.10)",
    accent_soft="rgba(91,87,216,0.22)",
    focus="#5B57D8",
    good="#1F7A4D",
    warning="#8A6410",
    serious="#B25A1E",
    critical="#B3352F",
    good_wash="rgba(31,122,77,0.10)",
    warning_wash="rgba(138,100,16,0.12)",
    serious_wash="rgba(178,90,30,0.10)",
    critical_wash="rgba(179,53,47,0.10)",
    unknown="#69707F",
    unknown_wash="rgba(105,112,127,0.09)",
    # The ramp inverts with the theme: magnitude reads as "further from the
    # page", which is darker on white and lighter on near-black.
    seq_100="#12161F",
    seq_250="#414855",
    seq_400="#727A88",
    seq_550="#A2A9B6",
    seq_700="#CDD2DB",
    chart_plane="#FCFCFE",
    grid="#F0F1F5",
    axis="#D5D9E1",
    crosshair="#9BA3B2",
    candle_up="#3D4453",
    candle_down="#A2A9B6",
)

THEMES: dict[str, Palette] = {"dark": DARK, "light": LIGHT}

# A one-element list rather than a module global rebound by ``set_theme``: the
# proxy below closes over the container, so the two cannot drift apart no
# matter how this module was imported.
_ACTIVE: list[Palette] = [DARK]


class _ActivePalette:
    """Forwards every attribute read to whichever palette is active.

    This exists so ``from .theme import PALETTE`` — which every widget module
    already does — keeps working while the palette underneath can change. A
    plain module constant would be captured at import time by each importer,
    and a theme switch would repaint half the window.
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> str:
        return getattr(_ACTIVE[0], name)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<PALETTE active={_ACTIVE[0].name}>"


PALETTE = _ActivePalette()


def set_theme(name: str) -> Palette:
    """Activate a palette by name, falling back to dark for an unknown one.

    Falling back rather than raising: the name arrives from a preferences file
    the user can edit by hand, and a typo there should not stop the
    application starting.
    """
    _ACTIVE[0] = THEMES.get(name, DARK)
    return _ACTIVE[0]


def active_theme() -> Palette:
    return _ACTIVE[0]


@dataclass(frozen=True)
class Type:
    """Type scale. Sizes in px, weights as Qt expects them."""

    display: int = 38
    h1: int = 23
    h2: int = 18
    h3: int = 15
    body: int = 14
    small: int = 12
    micro: int = 11


@dataclass(frozen=True)
class Space:
    """Spacing scale. Everything is one of these; nothing is a magic number."""

    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


TYPE = Type()
SPACE = Space()

RADIUS = 12
RADIUS_SM = 7
RADIUS_PILL = 999

#: Milliseconds. One duration for everything that moves, because an interface
#: whose animations disagree about their own speed reads as several interfaces.
#: 140ms is under the ~200ms threshold at which motion starts to feel like
#: waiting, and above the ~80ms at which it stops registering as motion at all.
MOTION_MS = 140
#: For things that are appearing rather than merely changing.
MOTION_SLOW_MS = 220


def direction_colour(direction: int) -> str:
    """Tint for LONG (+1) / SHORT (-1); neutral ink for anything else."""
    if direction > 0:
        return PALETTE.long
    if direction < 0:
        return PALETTE.short
    return PALETTE.ink_muted


def score_ramp(score: float, threshold: float) -> str:
    """Neutral ramp for a rule score.

    Below threshold the score is not a failure — it is simply not a signal — so
    it recedes to muted ink rather than turning red. Colouring an ordinary low
    score as an error is how an operator learns to ignore the colour that does
    mean one.
    """
    if score >= threshold + 15:
        return PALETTE.seq_100
    if score >= threshold:
        return PALETTE.seq_250
    if score >= threshold * 0.75:
        return PALETTE.seq_400
    return PALETTE.ink_muted


def r_colour(value: float) -> str:
    """Diverging colour for a realised R multiple.

    One of the few places hue carries meaning without an accompanying icon,
    which is defensible here because the number itself carries a sign: the
    colour reinforces "+0.8" rather than replacing it.
    """
    if value > 0.05:
        return PALETTE.good
    if value < -0.05:
        return PALETTE.critical
    return PALETTE.ink_muted


def severity_colour(severity: str) -> str:
    """Map a severity word onto its colour.

    Severity travels as a string through the core — ``supervision``,
    ``recovery`` and ``environment`` all return one — so the widget layer needs
    one place to resolve it rather than four ``if`` ladders that drift.
    """
    return {
        "good": PALETTE.good,
        "warning": PALETTE.warning,
        "serious": PALETTE.serious,
        "critical": PALETTE.critical,
        "unknown": PALETTE.unknown,
    }.get(severity, PALETTE.unknown)


def severity_wash(severity: str) -> str:
    return {
        "good": PALETTE.good_wash,
        "warning": PALETTE.warning_wash,
        "serious": PALETTE.serious_wash,
        "critical": PALETTE.critical_wash,
        "unknown": PALETTE.unknown_wash,
    }.get(severity, PALETTE.unknown_wash)


def stylesheet(p: Palette | _ActivePalette = PALETTE) -> str:
    t, s = TYPE, SPACE
    return f"""
    * {{
        font-family: {p.font};
        font-size: {t.body}px;
        color: {p.ink};
        outline: none;
    }}
    QMainWindow, QWidget#Plane {{ background: {p.plane}; }}
    QWidget#Content {{ background: {p.plane}; }}

    /* ------------------------------------------------------ sidebar rail */
    QFrame#Sidebar {{
        background: {p.surface};
        border-right: 1px solid {p.border};
    }}
    QLabel#Brand {{
        font-size: {t.h2}px;
        font-weight: 700;
        letter-spacing: 1.4px;
        color: {p.ink};
    }}
    QLabel#BrandSub {{
        font-size: {t.micro}px;
        color: {p.ink_faint};
        letter-spacing: 1.6px;
        font-weight: 600;
    }}
    /* The nav item is a plain button; the active indicator is a separate 3px
       bar drawn beside it. Putting the indicator in a border-left would make
       the label shift by three pixels every time the selection moved, which is
       the kind of jitter nobody consciously notices and everybody feels. */
    QPushButton#NavItem {{
        background: transparent;
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 9px 12px;
        text-align: left;
        color: {p.ink_muted};
        font-size: {t.body}px;
        font-weight: 500;
    }}
    QPushButton#NavItem:hover {{ background: {p.surface_high}; color: {p.ink_secondary}; }}
    QPushButton#NavItem:checked {{
        background: {p.surface_hover};
        color: {p.ink};
        font-weight: 600;
    }}
    QFrame#NavIndicator {{
        background: {p.accent};
        border: none;
        border-radius: 2px;
    }}
    QFrame#NavIndicatorIdle {{
        background: transparent;
        border: none;
    }}
    QLabel#NavBadge {{
        background: {p.accent};
        color: {p.accent_ink};
        border-radius: {RADIUS_PILL}px;
        padding: 1px 7px;
        font-size: {t.micro}px;
        font-weight: 700;
    }}
    QLabel#NavSection {{
        color: {p.ink_faint};
        font-size: {t.micro}px;
        font-weight: 700;
        letter-spacing: 1.3px;
    }}

    /* ------------------------------------------------------------ topbar */
    QFrame#TopBar {{
        background: {p.surface};
        border-bottom: 1px solid {p.border};
    }}
    QLabel#ViewTitle {{ font-size: {t.h1}px; font-weight: 650; letter-spacing: -0.2px; }}
    QLabel#ViewSubtitle {{ font-size: {t.small}px; color: {p.ink_muted}; }}

    /* ------------------------------------------------------------- cards */
    /* A one-stop gradient rather than a flat fill. It is barely visible and it
       is what stops a large panel from looking like a hole: real surfaces
       catch slightly more light at the top. */
    QFrame#Card {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {p.surface_high}, stop:0.45 {p.surface}, stop:1 {p.surface});
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}
    QFrame#CardQuiet {{
        background: transparent;
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}
    /* A signal card is the one surface allowed to draw attention to itself. */
    QFrame#SignalCard {{
        background: {p.surface};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS}px;
    }}
    QFrame#SignalCard:hover {{
        background: {p.surface_hover};
        border-color: {p.accent_soft};
    }}
    /* The chart's own plate. Recessed rather than raised — see the token. */
    QFrame#Plot {{
        background: {p.chart_plane};
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}

    QLabel#CardTitle {{
        color: {p.ink_muted};
        font-size: {t.micro}px;
        font-weight: 700;
        letter-spacing: 1.2px;
    }}
    QLabel#Display  {{ font-size: {t.display}px; font-weight: 620; letter-spacing: -0.8px; }}
    QLabel#H1       {{ font-size: {t.h1}px; font-weight: 620; letter-spacing: -0.2px; }}
    QLabel#H2       {{ font-size: {t.h2}px; font-weight: 620; }}
    QLabel#H3       {{ font-size: {t.h3}px; font-weight: 600; }}
    QLabel#Body     {{ font-size: {t.body}px; color: {p.ink_secondary}; }}
    QLabel#Caption  {{ font-size: {t.small}px; color: {p.ink_muted}; }}
    QLabel#Micro    {{ font-size: {t.micro}px; color: {p.ink_faint}; }}
    QLabel#Mono     {{ font-family: {p.mono}; font-size: {t.small}px; }}
    QLabel#MonoBig  {{ font-family: {p.mono}; font-size: {t.h3}px; font-weight: 600; }}
    /* A price. Tabular by construction, because a column of proportional
       digits does not align and a column that does not align cannot be
       scanned — which is the only reason to put it in a column. */
    QLabel#Numeric  {{
        font-family: {p.mono}; font-size: {t.h2}px; font-weight: 600;
        letter-spacing: -0.3px;
    }}

    /* ------------------------------------------------------------ tables */
    QTableWidget {{
        background: transparent;
        border: none;
        gridline-color: transparent;
        selection-background-color: {p.accent_wash};
        selection-color: {p.ink};
    }}
    QTableWidget::item {{
        padding: {s.md}px {s.sm}px;
        border: none;
        border-bottom: 1px solid {p.border};
    }}
    QTableWidget::item:selected {{ background: {p.accent_wash}; }}
    QTableWidget::item:hover {{ background: {p.surface_high}; }}
    /* The header VIEW needs its own background. Styling only ::section leaves
       Qt's default palette showing through behind the sections, which renders
       as a pale strip across the top of every table in dark mode. */
    QHeaderView {{ background: transparent; border: none; }}
    QTableWidget QHeaderView::section:horizontal {{ background: transparent; }}
    QHeaderView::section {{
        background: transparent;
        color: {p.ink_faint};
        padding: {s.sm}px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-size: {t.micro}px;
        font-weight: 700;
        letter-spacing: 0.9px;
    }}
    QTableCornerButton::section {{ background: transparent; border: none; }}

    /* ----------------------------------------------------------- buttons */
    QPushButton {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_SM}px;
        padding: 9px 18px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {p.surface_hover}; border-color: {p.ink_faint}; }}
    QPushButton:disabled {{
        color: {p.ink_faint};
        background: transparent;
        border-color: {p.border};
    }}
    QPushButton#Primary {{
        background: {p.accent}; border-color: {p.accent}; color: {p.accent_ink};
    }}
    QPushButton#Primary:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
    QPushButton#Primary:disabled {{
        background: transparent; border-color: {p.border}; color: {p.ink_faint};
    }}
    QPushButton#Ghost {{
        background: transparent; border: 1px solid {p.border_strong};
        color: {p.ink_secondary};
    }}
    QPushButton#Ghost:hover {{ background: {p.surface_high}; color: {p.ink}; }}
    /* A segmented control: no border, selection carried by surface and ink.
       Deliberately NOT by font weight — Qt sizes the button before the checked
       state applies, so a bolder selected label overflows the width the layout
       already agreed on and clips its last character. */
    QPushButton#Quiet {{
        background: transparent; border: none; color: {p.ink_muted};
        padding: 7px 16px; font-weight: 600; border-radius: {RADIUS_SM}px;
    }}
    QPushButton#Quiet:hover {{ color: {p.ink}; background: {p.surface_high}; }}
    QPushButton#Quiet:checked {{ color: {p.ink}; background: {p.surface_hover}; }}
    QFrame#Segmented {{
        background: {p.surface_high};
        border: 1px solid {p.border};
        border-radius: {RADIUS_SM + 2}px;
    }}

    /* Arm and Confirm look different on purpose. They are two separate
       deliberate actions, and making them look alike invites a double-click
       straight through both. */
    QPushButton#Arm {{
        background: {p.warning_wash}; border-color: {p.warning}; color: {p.warning};
        padding: 12px 26px; font-size: {t.h3}px;
    }}
    QPushButton#Arm:hover {{ background: {p.surface_hover}; }}
    QPushButton#Confirm {{
        background: {p.critical_wash}; border-color: {p.critical}; color: {p.critical};
        padding: 12px 26px; font-size: {t.h3}px;
    }}
    QPushButton#Confirm:hover {{ background: {p.surface_hover}; }}
    QPushButton#Arm:disabled, QPushButton#Confirm:disabled {{
        background: transparent; border-color: {p.border}; color: {p.ink_faint};
    }}

    /* ------------------------------------------------------------ inputs */
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_SM}px;
        padding: 8px 12px;
        selection-background-color: {p.accent_wash};
        selection-color: {p.ink};
    }}
    QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
        border-color: {p.ink_faint};
    }}
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {p.focus};
    }}
    QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {p.ink_faint}; background: transparent; border-color: {p.border};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_raised};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_SM}px;
        selection-background-color: {p.accent_wash};
        padding: 4px;
    }}
    QCheckBox {{ spacing: {s.sm}px; color: {p.ink_secondary}; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px;
        border: 1px solid {p.border_strong};
        border-radius: 4px;
        background: {p.surface_high};
    }}
    QCheckBox::indicator:checked {{
        background: {p.accent}; border-color: {p.accent};
    }}
    QCheckBox:disabled {{ color: {p.ink_faint}; }}

    QPlainTextEdit, QTextEdit {{
        background: {p.surface_high};
        border: 1px solid {p.border};
        border-radius: {RADIUS_SM}px;
        font-family: {p.mono};
        font-size: {t.small}px;
        padding: {s.sm}px;
    }}

    /* --------------------------------------------------------- scrollbars */
    QScrollArea {{ background: transparent; border: none; }}
    /* The square where two scrollbars meet. Left unstyled it paints from the
       default palette, which shows as a pale notch in the corner of every
       scrolling panel in dark mode. */
    QAbstractScrollArea::corner {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {p.border_strong}; border-radius: 5px; min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.ink_faint}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{
        background: {p.border_strong}; border-radius: 5px; min-width: 32px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* In the global sheet rather than set on the widget, so it follows a theme
       switch for free. A status bar left painting the old palette is the most
       conspicuous thing on screen after a switch — it runs the full width. */
    QStatusBar {{
        background: {p.surface};
        border-top: 1px solid {p.border};
        color: {p.ink_muted};
        font-size: {t.small}px;
    }}
    QStatusBar::item {{ border: none; }}

    QSplitter::handle {{ background: {p.border}; }}
    QSplitter::handle:hover {{ background: {p.border_strong}; }}
    QToolTip {{
        background: {p.surface_raised};
        border: 1px solid {p.border_strong};
        color: {p.ink};
        padding: 7px 9px;
        border-radius: {RADIUS_SM}px;
    }}
    """
