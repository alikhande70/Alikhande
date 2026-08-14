#pragma once

// Panel styling.
//
// One deliberate choice worth stating: the row font is monospaced. v1.1.0 built
// its rows with printf-style column padding (`%-12s | %7.1f`) and rendered them
// in the default proportional font, so the columns never actually lined up. Any
// column layout built from padded text needs a fixed-width face or the padding
// is decorative.

#define AS_UI_FONT_MONO       "Consolas"
#define AS_UI_FONT_UI         "Segoe UI"
#define AS_UI_FONT_SIZE_ROW   9
#define AS_UI_FONT_SIZE_HEAD  9
#define AS_UI_FONT_SIZE_TITLE 10

// Dark palette with an opaque backing panel, so the dashboard stays legible on
// any chart background rather than inheriting whatever is behind it.
#define AS_UI_COLOR_PANEL     C'22,24,29'
#define AS_UI_COLOR_HEADER    C'32,35,42'
#define AS_UI_COLOR_BORDER    C'52,56,66'
#define AS_UI_COLOR_TEXT      C'226,229,235'
#define AS_UI_COLOR_MUTED     C'138,144,156'
#define AS_UI_COLOR_ACCENT    C'82,156,255'
#define AS_UI_COLOR_LONG      C'64,196,124'
#define AS_UI_COLOR_SHORT     C'232,92,92'
#define AS_UI_COLOR_WARN      C'236,178,64'
#define AS_UI_COLOR_TAB_OFF   C'38,41,49'

#define AS_UI_ROW_HEIGHT      18
#define AS_UI_HEADER_HEIGHT   26
#define AS_UI_TAB_HEIGHT      24
#define AS_UI_PADDING         8
