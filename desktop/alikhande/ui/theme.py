"""Design tokens and the application stylesheet.

Tokens first, stylesheet second. Every colour, size and space in the UI comes
from here, so a change is made once rather than hunted through widget code.

## Colour is assigned by job, and the palette was validated, not eyeballed

Four distinct jobs, four rules:

**Identity — direction.** LONG and SHORT are two categories, so they take
categorical slots 1 and 2. Validated all-pairs against this app's own dark
surface (`#12161F`): CVD ΔE 26.8, normal-vision ΔE 31.8, both well clear of
their floors, and both above 3:1 contrast.

Not green/red, deliberately. Green/red is reserved here for *permission* —
allowed versus blocked — and a SHORT signal painted red reads as an error at a
glance. Blue/orange keeps direction and permission in separate colour families.

**Magnitude — the rule score.** One hue, light to dark. A sequential blue ramp,
never a rainbow, never a hue change part-way up.

**Polarity — realised R.** Diverging blue↔red around a neutral grey midpoint.

**State — gates and guards.** The fixed status palette. These four are *not* a
categorical palette and do not pass a categorical validation, which is expected:
warning and serious sit in the same warm family by design. The mitigation is
structural — **every status colour in this UI ships with an icon and a text
label**, so hue never carries meaning on its own. `StatusChip` enforces that by
taking the icon and the label as required arguments.

## Type

A real scale, because uniform 13px everywhere is what makes an interface read as
a data dump: nothing is emphasised, so the eye has nowhere to land.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # ---- surfaces, darkest to lightest ---------------------------------
    plane: str = "#0B0E14"  # the window behind everything
    surface: str = "#12161F"  # cards; the surface the palette was validated on
    surface_high: str = "#1A1F2B"  # nested panels, table headers
    surface_hover: str = "#232A38"
    border: str = "#242B39"
    border_strong: str = "#37415480"

    # ---- ink ------------------------------------------------------------
    ink: str = "#F2F5FA"
    ink_secondary: str = "#A6B0C3"
    ink_muted: str = "#6C7789"
    ink_faint: str = "#4A5364"

    # ---- identity: direction (categorical slots 1 and 2) -----------------
    long: str = "#3987E5"
    short: str = "#D95926"
    long_wash: str = "rgba(57,135,229,0.14)"
    short_wash: str = "rgba(217,89,38,0.14)"

    # ---- interactive ----------------------------------------------------
    accent: str = "#3987E5"
    accent_hover: str = "#5A9DEC"
    accent_ink: str = "#06101F"

    # ---- state: the fixed status palette (icon + label always) ----------
    good: str = "#0CA30C"
    warning: str = "#FAB219"
    serious: str = "#EC835A"
    critical: str = "#D03B3B"
    good_wash: str = "rgba(12,163,12,0.13)"
    warning_wash: str = "rgba(250,178,25,0.13)"
    serious_wash: str = "rgba(236,131,90,0.13)"
    critical_wash: str = "rgba(208,59,59,0.13)"
    # Unknown is not a status. It is the absence of one, and it must never
    # borrow a status colour — an unseen calendar that renders amber reads as
    # "mildly concerning" when the truth is "nobody looked".
    unknown: str = "#6C7789"
    unknown_wash: str = "rgba(108,119,137,0.12)"

    # ---- magnitude: sequential blue, light -> dark -----------------------
    seq_100: str = "#CDE2FB"
    seq_250: str = "#86B6EF"
    seq_400: str = "#3987E5"
    seq_550: str = "#1C5CAB"
    seq_700: str = "#0D366B"

    # ---- chart chrome ---------------------------------------------------
    grid: str = "#1E2532"
    axis: str = "#2C3444"

    # ---- type -----------------------------------------------------------
    font: str = "'Segoe UI Variable', 'Segoe UI', 'Inter', 'DejaVu Sans', system-ui, sans-serif"
    mono: str = "'Cascadia Mono', 'JetBrains Mono', 'Consolas', 'DejaVu Sans Mono', monospace"


PALETTE = Palette()


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


def score_ramp(score: float, threshold: float) -> str:
    """Sequential blue for a rule score.

    One hue, darkening with magnitude. Below threshold the score is not a
    failure — it is simply not a signal — so it recedes to muted ink rather than
    turning red. Colouring an ordinary low score as an error is how an operator
    learns to ignore the colour that does mean one.
    """
    if score >= threshold + 15:
        return PALETTE.seq_100
    if score >= threshold:
        return PALETTE.seq_250
    if score >= threshold * 0.75:
        return PALETTE.seq_400
    return PALETTE.ink_muted


def r_colour(value: float) -> str:
    """Diverging colour for a realised R multiple."""
    if value > 0.05:
        return PALETTE.long
    if value < -0.05:
        return PALETTE.critical
    return PALETTE.ink_muted


def stylesheet(p: Palette = PALETTE) -> str:
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
        letter-spacing: 0.4px;
        color: {p.ink};
    }}
    QLabel#BrandSub {{
        font-size: {t.micro}px;
        color: {p.ink_faint};
        letter-spacing: 0.6px;
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
        background: rgba(57,135,229,0.14);
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
        letter-spacing: 1.2px;
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
       Qt's default light palette showing through behind the sections, which
       renders as a white strip across the top of every table. */
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

    /* Arm and Confirm look different on purpose. They are two separate
       deliberate actions, and making them look alike invites a double-click
       straight through both. */
    QPushButton#Arm {{
        background: {p.warning_wash}; border-color: {p.warning}; color: {p.warning};
        padding: 12px 26px; font-size: {t.h3}px;
    }}
    QPushButton#Arm:hover {{ background: rgba(250,178,25,0.24); }}
    QPushButton#Confirm {{
        background: {p.critical_wash}; border-color: {p.critical}; color: {p.critical};
        padding: 12px 26px; font-size: {t.h3}px;
    }}
    QPushButton#Confirm:hover {{ background: rgba(208,59,59,0.26); }}
    QPushButton#Arm:disabled, QPushButton#Confirm:disabled {{
        background: transparent; border-color: {p.border}; color: {p.ink_faint};
    }}

    /* ------------------------------------------------------------ inputs */
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_SM}px;
        padding: 8px 12px;
        selection-background-color: {p.accent};
    }}
    QComboBox:focus, QLineEdit:focus {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_SM}px;
        selection-background-color: {p.surface_hover};
        padding: 4px;
    }}

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

    QSplitter::handle {{ background: {p.border}; }}
    QToolTip {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        color: {p.ink};
        padding: 7px 9px;
        border-radius: {RADIUS_SM}px;
    }}
    """
