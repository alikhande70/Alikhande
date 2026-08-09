"""Design tokens and the application stylesheet.

Tokens first, stylesheet second. Every colour, radius and spacing value in the
UI comes from the palette below, so a change is made once rather than hunted
through widget code — the same reason the MQL5 build had a ``Theme.mqh``.

The visual language is deliberately restrained. This is an instrument panel for
a system whose entire argument is "do not trust unverified numbers", and a
dashboard that looks like a casino undermines that before a single figure is
read. Colour carries meaning and nothing else:

* **Accent (blue)** — interactive, neutral.
* **Long (teal) / Short (amber)** — direction. Not green/red, because
  green/red is reserved for *permission*, and using it for direction makes a
  short signal look like an error.
* **Danger (red)** — blocked, refused, or requiring human attention.
* **Muted grey** — anything unknown or unavailable. Unknown must never look
  like a value.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # Surfaces, darkest to lightest.
    base: str = "#0B0E14"
    surface: str = "#12161F"
    surface_high: str = "#1A1F2B"
    surface_hover: str = "#222836"
    border: str = "#2A3140"
    border_strong: str = "#3A4356"

    # Text.
    text: str = "#E4E8F0"
    text_dim: str = "#96A0B5"
    text_faint: str = "#5E6980"

    # Meaning.
    accent: str = "#4C8DFF"
    accent_dim: str = "#2E5FB0"
    long: str = "#2BC4A5"
    short: str = "#F0A63C"
    danger: str = "#F0553C"
    warning: str = "#E8C547"
    ok: str = "#2BC46A"
    muted: str = "#5E6980"

    # Typography and metrics.
    font_family: str = "'Segoe UI', 'Inter', 'DejaVu Sans', system-ui, sans-serif"
    font_mono: str = "'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', monospace"
    radius: int = 8
    radius_small: int = 5
    gap: int = 12


PALETTE = Palette()


def score_colour(score: float, threshold: float) -> str:
    """Colour for a rule score.

    Below threshold reads as muted rather than red: a score of 40 is not an
    error, it is simply not a signal, and colouring it as a failure trains the
    operator to ignore the colour that does mean failure.
    """
    if score >= threshold:
        return PALETTE.accent
    if score >= threshold * 0.8:
        return PALETTE.text_dim
    return PALETTE.text_faint


def stylesheet(palette: Palette = PALETTE) -> str:
    p = palette
    return f"""
    * {{
        font-family: {p.font_family};
        font-size: 13px;
        color: {p.text};
        outline: none;
    }}
    QWidget#Root, QMainWindow {{ background: {p.base}; }}

    /* ---------------------------------------------------------- header */
    QFrame#Header {{
        background: {p.surface};
        border-bottom: 1px solid {p.border};
    }}
    QLabel#AppTitle {{ font-size: 15px; font-weight: 600; letter-spacing: 0.3px; }}
    QLabel#AppVersion {{ color: {p.text_faint}; font-size: 11px; }}

    /* Status pills. The banner variant is for states the operator must not be
       able to miss — a real account, or an execution needing review. */
    QLabel#Pill {{
        background: {p.surface_high};
        border: 1px solid {p.border};
        border-radius: {p.radius_small}px;
        padding: 3px 10px;
        color: {p.text_dim};
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#PillOk     {{ background: rgba(43,196,106,0.14); border-color: {p.ok};      color: {p.ok}; }}
    QLabel#PillWarn   {{ background: rgba(232,197,71,0.14); border-color: {p.warning}; color: {p.warning}; }}
    QLabel#PillDanger {{ background: rgba(240,85,60,0.16);  border-color: {p.danger};  color: {p.danger}; }}

    QFrame#Banner {{
        background: rgba(240,85,60,0.13);
        border: 1px solid {p.danger};
        border-radius: {p.radius}px;
    }}
    QLabel#BannerText {{ color: {p.danger}; font-weight: 600; }}

    /* ------------------------------------------------------------ tabs */
    QTabWidget::pane {{
        border: none;
        background: {p.base};
        top: -1px;
    }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: transparent;
        color: {p.text_faint};
        padding: 9px 20px;
        margin-right: 2px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 600;
        font-size: 12px;
    }}
    QTabBar::tab:hover  {{ color: {p.text_dim}; }}
    QTabBar::tab:selected {{
        color: {p.text};
        border-bottom: 2px solid {p.accent};
    }}

    /* ----------------------------------------------------------- cards */
    QFrame#Card {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: {p.radius}px;
    }}
    QLabel#CardTitle {{
        color: {p.text_faint};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.1px;
    }}
    QLabel#Metric      {{ font-size: 21px; font-weight: 600; }}
    QLabel#MetricSmall {{ font-size: 15px; font-weight: 600; }}
    QLabel#Caption     {{ color: {p.text_faint}; font-size: 11px; }}
    QLabel#Mono        {{ font-family: {p.font_mono}; font-size: 12px; }}

    /* ---------------------------------------------------------- tables */
    QTableWidget {{
        background: {p.surface};
        alternate-background-color: {p.surface_high};
        border: 1px solid {p.border};
        border-radius: {p.radius}px;
        gridline-color: {p.border};
        selection-background-color: {p.accent_dim};
        selection-color: #FFFFFF;
    }}
    QTableWidget::item {{ padding: 7px 9px; border: none; }}
    QHeaderView::section {{
        background: {p.surface_high};
        color: {p.text_faint};
        padding: 8px 9px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.7px;
    }}
    QTableCornerButton::section {{ background: {p.surface_high}; border: none; }}

    /* --------------------------------------------------------- buttons */
    QPushButton {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {p.radius_small}px;
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton:hover    {{ background: {p.surface_hover}; }}
    QPushButton:disabled {{ color: {p.text_faint}; background: {p.surface}; border-color: {p.border}; }}

    QPushButton#Primary {{ background: {p.accent}; border-color: {p.accent}; color: #06101F; }}
    QPushButton#Primary:hover {{ background: #6BA1FF; }}
    QPushButton#Primary:disabled {{ background: {p.surface}; border-color: {p.border}; color: {p.text_faint}; }}

    /* Arm and Confirm are visually distinct on purpose. They are two separate
       deliberate actions, and making them look alike invites a double-click
       through both. */
    QPushButton#Arm {{ background: rgba(232,197,71,0.16); border-color: {p.warning}; color: {p.warning}; }}
    QPushButton#Arm:hover {{ background: rgba(232,197,71,0.26); }}
    QPushButton#Confirm {{ background: rgba(240,85,60,0.18); border-color: {p.danger}; color: {p.danger}; }}
    QPushButton#Confirm:hover {{ background: rgba(240,85,60,0.30); }}
    QPushButton#Arm:disabled, QPushButton#Confirm:disabled {{
        background: {p.surface}; border-color: {p.border}; color: {p.text_faint};
    }}

    /* --------------------------------------------------------- inputs */
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        border-radius: {p.radius_small}px;
        padding: 6px 10px;
    }}
    QComboBox:focus, QLineEdit:focus {{ border-color: {p.accent}; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        selection-background-color: {p.accent_dim};
    }}

    QPlainTextEdit, QTextEdit {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: {p.radius}px;
        font-family: {p.font_mono};
        font-size: 12px;
    }}

    QProgressBar {{
        background: {p.surface_high};
        border: 1px solid {p.border};
        border-radius: 3px;
        height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {p.warning}; border-radius: 3px; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p.border_strong}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_faint}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {p.border_strong}; border-radius: 5px; min-width: 30px; }}

    QStatusBar {{ background: {p.surface}; border-top: 1px solid {p.border}; color: {p.text_faint}; }}
    QSplitter::handle {{ background: {p.border}; }}
    QToolTip {{
        background: {p.surface_high};
        border: 1px solid {p.border_strong};
        color: {p.text};
        padding: 6px 8px;
    }}
    """
