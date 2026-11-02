"""
views/palette.py — Palette monochrome + couleurs de bus
"""
from PyQt5.QtGui import QColor

# Gris
C_WHITE      = "#FFFFFF"
C_OFF_WHITE  = "#F8F9FA"
C_LIGHT_GRAY = "#E5E7EB"
C_MID_GRAY   = "#9CA3AF"
C_DARK_GRAY  = "#4B5563"
C_CHARCOAL   = "#374151"
C_NEAR_BLACK = "#1F2937"

# Accent
C_BLUE       = "#2563eb"
C_BLUE_DARK  = "#2563EB"
C_BORDER     = "#D1D5DB"
C_SUCCESS    = "#10B981"

# Couleurs par type de bus (slot assigné)
BUS_COLORS: dict[str, str] = {
    "SPI":     "#2563EB",   # bleu foncé
    "I2C":     "#7C3AED",   # violet
    "ADC":     "#0891B2",   # cyan
    "Digital": "#059669",   # vert
}

# Style de base des boutons de slot/output vide
STYLE_SLOT_EMPTY = """
    QPushButton {{
        background-color: {bg};
        border: 1.5px solid {border};
        border-radius: 4px;
        color: {fg};
        font-family: 'Segoe UI', sans-serif;
        font-size: {fs}px;
        text-align: center;
        padding: 2px;
    }}
    QPushButton:hover {{
        background-color: #E5E7EB;
        border-color: #9CA3AF;
    }}
"""

STYLE_SLOT_ASSIGNED = """
    QPushButton {{
        background-color: {bg};
        border: 1.5px solid {border};
        border-radius: 4px;
        color: #FFFFFF;
        font-family: 'Segoe UI', sans-serif;
        font-size: {fs}px;
        font-weight: bold;
        text-align: center;
        padding: 2px;
    }}
    QPushButton:hover {{
        background-color: {bg_hover};
        border-color: {border};
    }}
"""

STYLE_OUTPUT_OFF = """
    QPushButton {
        background-color: #FFFFFF;
        border: 1.5px solid #D1D5DB;
        border-radius: 4px;
        color: #9CA3AF;
        font-family: 'Segoe UI', sans-serif;
        font-size: 10px;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #E5E7EB;
        border-color: #9CA3AF;
    }
"""

STYLE_OUTPUT_ON = """
    QPushButton {
        background-color: #2563eb;
        border: 1.5px solid #2563EB;
        border-radius: 4px;
        color: #FFFFFF;
        font-family: 'Segoe UI', sans-serif;
        font-size: 10px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #2563EB;
    }
"""

STYLE_DIALOG = """
    QDialog {
        background-color: #FFFFFF;
    }
    QLabel {
        color: #374151;
        font-size: 13px;
    }
    QPushButton {
        background-color: #F8F9FA;
        border: 1px solid #D1D5DB;
        border-radius: 4px;
        padding: 8px 16px;
        color: #374151;
        font-size: 13px;
    }
    QPushButton:hover {
        background-color: #E5E7EB;
        border-color: #9CA3AF;
    }
    QComboBox {
        background-color: #FFFFFF;
        border: 1px solid #D1D5DB;
        border-radius: 4px;
        padding: 6px;
        color: #1F2937;
        font-size: 13px;
    }
    QGroupBox {
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 8px;
        font-weight: bold;
        color: #374151;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }
"""

STYLE_BTN_PRIMARY = """
    QPushButton {
        background-color: #2563eb;
        color: white;
        font-weight: bold;
        border: none;
        padding: 10px;
        border-radius: 4px;
        font-size: 13px;
    }
    QPushButton:hover { background-color: #2563EB; }
"""
