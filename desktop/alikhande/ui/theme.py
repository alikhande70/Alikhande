"""Design tokens and the application stylesheet.

Tokens first, stylesheet second. Every colour, size and space in the UI comes
from here, so a change is made once rather than hunted through widget code.

## The system is monochrome, and that is a functional choice

Surfaces, borders, text and every piece of chrome are pure neutrals. Nothing
about a panel, a table, a button or a heading is coloured. What this buys is
not tastefulness — it is that **the few coloured things left on screen are the
only things carrying meaning**, so colour becomes a signal instead of
decoration. An interface where the sidebar, the headings and the buttons are
all tinted has spent its colour budget before the first warning appears.

Two palettes, same tokens. Dark is near-black rather than black (``#0D0D0D``):
true black behind bright text produces halation that makes small type vibrate,
and this application is mostly small type.

## Colour is assigned by job, and only three jobs qualify

**Direction — LONG vs SHORT.** Carried primarily by an arrow and a word, never
by hue alone. A low-chroma blue/amber pair backs them up so a column can be
scanned at speed. Deliberately not green/red: green/red is spent below on
permission, and a SHORT painted red reads as an error rather than a direction.

**State — gates, guards, evidence tiers.** The fixed status palette. These four
are *not* a categorical palette and do not pass a categorical validation, which
is expected: warning and serious sit in the same warm family by design. The
mitigation is structural — **every status colour in this UI ships with an icon
and a text label**, so hue never carries meaning on its own. ``StatusChip``
enforces that by taking the icon and the label as required arguments.

**Magnitude — rule score, realised R.** A *neutral* ramp for score, because a
rule score is not a probability and a saturated blue-to-navy ramp makes it look
like one reading off a calibrated instrument. Grey says "more of something"
without claiming to say what. A diverging pair for realised R, where the sign
genuinely is the message.

## Switching

``PALETTE`` is a proxy that forwards to whichever palette is active, so the
hundred or so ``PALETTE.ink`` reads across the widget layer need no change and
a theme switch takes effect without a restart. Qt stylesheets are strings
captured at apply time, so the window re-applies :func:`stylesheet` and rebuilds
its views — the same mechanism the language switch already uses.

## Type

A real scale, because uniform 13px everywhere is what makes an interface read as
a data dump: nothing is emphasised, so the eye has nowhere to land.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str = "dark"
    dark: bool = True

    # ---- surfaces, furthest back to furthest forward --------------------
    plane: str = "#0D0D0D"  # the window behind everything
    surface: str = "#171717"  # cards
    surface_high: str = "#212121"  # nested panels, inputs, table headers
    surface_hover: str = "#2A2A2A"
    border: str = "#262626"
    border_strong: str = "#3A3A3A"

    # ---- ink ------------------------------------------------------------
    ink: str = "#ECECEC"
    ink_secondary: str = "#B4B4B4"
    ink_muted: str = "#8F8F8F"
    ink_faint: str = "#6B6B6B"

    # ---- identity: direction (icon + word always accompany these) --------
    long: str = "#5E97D6"
    short: str = "#D08A4E"
    long_wash: str = "rgba(94,151,214,0.12)"
    short_wash: str = "rgba(208,138,78,0.12)"

    # ---- interactive: the accent is the inverse of the plane -------------
    # A white button on near-black, a black button on white. Exactly one
    # primary action is visible at a time, and this makes it unmistakable
    # without introducing a brand hue that would compete with the status
    # colours for the operator's attention.
    accent: str = "#ECECEC"
    accent_hover: str = "#FFFFFF"
    accent_ink: str = "#0D0D0D"
    focus: str = "#8F8F8F"

    # ---- state: the fixed status palette (icon + label always) ----------
    good: str = "#4FA96B"
    warning: str = "#D9A441"
    serious: str = "#D3813F"
    critical: str = "#D25B5B"
    good_wash: str = "rgba(79,169,107,0.12)"
    warning_wash: str = "rgba(217,164,65,0.12)"
    serious_wash: str = "rgba(211,129,63,0.12)"
    critical_wash: str = "rgba(210,91,91,0.12)"
    # Unknown is not a status. It is the absence of one, and it must never
    # borrow a status colour — an unseen calendar that renders amber reads as
    # "mildly concerning" when the truth is "nobody looked".
    unknown: str = "#8F8F8F"
    unknown_wash: str = "rgba(143,143,143,0.10)"

    # ---- magnitude: a neutral ramp, strongest to faintest ----------------
    seq_100: str = "#ECECEC"
    seq_250: str = "#B4B4B4"
    seq_400: str = "#8F8F8F"
    seq_550: str = "#6B6B6B"
    seq_700: str = "#4A4A4A"

    # ---- chart chrome ---------------------------------------------------
    grid: str = "#1E1E1E"
    axis: str = "#333333"
    candle_up: str = "#B4B4B4"
    candle_down: str = "#5C5C5C"

    # ---- type -----------------------------------------------------------
    font: str = "'Segoe UI Variable', 'Segoe UI', 'Inter', 'DejaVu Sans', system-ui, sans-serif"
    mono: str = "'Cascadia Mono', 'JetBrains Mono', 'Consolas', 'DejaVu Sans Mono', monospace"


DARK = Palette()

LIGHT = Palette(
    name="light",
    dark=False,
    plane="#FFFFFF",
    surface="#FAFAFA",
    surface_high="#F2F2F2",
    surface_hover="#E9E9E9",
    border="#E5E5E5",
    border_strong="#CFCFCF",
    ink="#0D0D0D",
    ink_secondary="#3F3F3F",
    ink_muted="#6E6E6E",
    ink_faint="#9B9B9B",
    long="#2F6FB5",
    short="#A85D23",
    long_wash="rgba(47,111,181,0.10)",
    short_wash="rgba(168,93,35,0.10)",
    accent="#0D0D0D",
    accent_hover="#2B2B2B",
    accent_ink="#FFFFFF",
    focus="#6E6E6E",
    good="#2E7D4F",
    warning="#8A6410",
    serious="#B25A1E",
    critical="#B3352F",
    good_wash="rgba(46,125,79,0.10)",
    warning_wash="rgba(138,100,16,0.12)",
    serious_wash="rgba(178,90,30,0.10)",
    critical_wash="rgba(179,53,47,0.10)",
    unknown="#6E6E6E",
    unknown_wash="rgba(110,110,110,0.09)",
    # The ramp inverts with the theme: magnitude reads as "further from the
    # page", which is darker on white and lighter on near-black.
    seq_100="#1A1A1A",
    seq_250="#4A4A4A",
    seq_400="#7A7A7A",
    seq_550="#A5A5A5",
    seq_700="#CFCFCF",
    grid="#F0F0F0",
    axis="#D8D8D8",
    candle_up="#4A4A4A",
    candle_down="#B0B0B0",
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

    display: int = 34
    h1: int = 22
    h2: int = 17
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

RADIUS = 10
RADIUS_SM = 6
RADIUS_PILL = 999


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
        font-size: {t.h3}px;
        font-weight: 700;
        letter-spacing: 0.2px;
        color: {p.ink};
    }}
    QLabel#BrandSub {{
        font-size: {t.micro}px;
        color: {p.ink_faint};
        letter-spacing: 0.5px;
    }}
    QPushButton#NavItem {{
        background: transparent;
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 10px 12px;
        text-align: left;
        color: {p.ink_secondary};
        font-size: {t.body}px;
        font-weight: 500;
    }}
    QPushButton#NavItem:hover {{ background: {p.surface_high}; color: {p.ink}; }}
    QPushButton#NavItem:checked {{
        background: {p.surface_hover};
        color: {p.ink};
        font-weight: 600;
    }}
    QLabel#NavBadge {{
        background: {p.accent};
        color: {p.accent_ink};
        border-radius: {RADIUS_PILL}px;
        padding: 1px 7px;
        font-size: {t.micro}px;
        font-weight: 700;
    }}

    /* ------------------------------------------------------------ topbar */
    QFrame#TopBar {{
        background: {p.plane};
        border-bottom: 1px solid {p.border};
    }}
    QLabel#ViewTitle {{ font-size: {t.h1}px; font-weight: 600; }}
    QLabel#ViewSubtitle {{ font-size: {t.small}px; color: {p.ink_muted}; }}

    /* ------------------------------------------------------------- cards */
    QFrame#Card {{
        background: {p.surface};
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
    QFrame#SignalCard:hover {{ background: {p.surface_high}; }}

    QLabel#CardTitle {{
        color: {p.ink_muted};
        font-size: {t.micro}px;
        font-weight: 700;
        letter-spacing: 1.1px;
    }}
    QLabel#Display  {{ font-size: {t.display}px; font-weight: 600; }}
    QLabel#H1       {{ font-size: {t.h1}px; font-weight: 600; }}
    QLabel#H2       {{ font-size: {t.h2}px; font-weight: 600; }}
    QLabel#H3       {{ font-size: {t.h3}px; font-weight: 600; }}
    QLabel#Body     {{ font-size: {t.body}px; color: {p.ink_secondary}; }}
    QLabel#Caption  {{ font-size: {t.small}px; color: {p.ink_muted}; }}
    QLabel#Micro    {{ font-size: {t.micro}px; color: {p.ink_faint}; }}
    QLabel#Mono     {{ font-family: {p.mono}; font-size: {t.small}px; }}
    QLabel#MonoBig  {{ font-family: {p.mono}; font-size: {t.h3}px; font-weight: 600; }}

    /* ------------------------------------------------------------ tables */
    QTableWidget {{
        background: transparent;
        border: none;
        gridline-color: transparent;
        selection-background-color: {p.surface_hover};
        selection-color: {p.ink};
    }}
    QTableWidget::item {{
        padding: {s.md}px {s.sm}px;
        border: none;
        border-bottom: 1px solid {p.border};
    }}
    QTableWidget::item:selected {{ background: {p.surface_hover}; }}
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
        letter-spacing: 0.8px;
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
    QPushButton:hover {{ background: {p.surface_hover}; }}
    QPushButton:disabled {{
        color: {p.ink_faint};
        background: transparent;
        border-color: {p.border};
    }}
    QPushButton#Primary {{
        background: {p.accent}; border-color: {p.accent}; color: {p.accent_ink};
    }}
    QPushButton#Primary:hover {{ background: {p.accent_hover}; }}
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
        selection-background-color: {p.surface_hover};
        selection-color: {p.ink};
    }}
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {p.focus};
    }}
    QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {p.ink_faint}; background: transparent; border-color: {p.border};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_SM}px;
        selection-background-color: {p.surface_hover};
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
    }}
    QStatusBar::item {{ border: none; }}

    QSplitter::handle {{ background: {p.border}; }}
    QToolTip {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        color: {p.ink};
        padding: 7px 9px;
        border-radius: {RADIUS_SM}px;
    }}
    """
