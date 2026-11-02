# styles.py - Version Professionnelle

# ============= PALETTE COULEURS MODERNE =============
COLORS = {
    # Couleurs principales (tons plus sophistiqués)
    "primary": "#2563EB",      # Bleu professionnel
    "primary_dark": "#1D4ED8",
    "primary_light": "#DBEAFE",
    "secondary": "#64748B",     # Gris ardoise
    "secondary_dark": "#475569",
    "accent": "#0EA5E9",        # Cyan pour accents
    "bg_cell_focus": "#FAFBFF",
    "bg_gutter": "#F9FAFB",
    "danger_bg": "#FEF2F2",
    "error_text": "#991B1B",
    "warning_bg": "#FFFBEB",
    "warning_text": "#92400E",
    "success_bg": "#F0FDF4",
    "success_text": "#166534",
    
    # Neutres (échelle Tailwind moderne)
    "bg_main": "#F8FAFC",       # Fond principal - très clair
    "bg_panel": "#FFFFFF",      # Panneaux blancs
    "bg_sidebar": "#FFFFFF",
    "bg_hover": "#F1F5F9",      # Hover subtil
    
    "border_light": "#E2E8F0",  # Bordures légères
    "border_focus": "#94A3B8",  # Bordure focus
    
    "text_primary": "#0F172A",  # Texte principal (très foncé)
    "text_secondary": "#475569", # Texte secondaire
    "text_muted": "#94A3B8",     # Texte désactivé
    "text_on_primary": "#FFFFFF", # Texte sur fond primaire
    
    # États
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    
    # Ombres (pour effet de profondeur)
    "shadow_sm": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    "shadow": "0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)",
    "shadow_md": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1)",
    "shadow_lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)",
}

# ============= STYLES GÉNÉRAUX =============

STYLE_MAIN = f"""
QMainWindow, QWidget {{
    background-color: {COLORS["bg_main"]};
    font-family: 'Segoe UI', 'Inter', 'Roboto', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 13px;
    color: {COLORS["text_primary"]};
}}

/* Scrollbars modernes */
QScrollBar:vertical {{
    background: {COLORS["bg_main"]};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS["secondary"]};
    min-height: 30px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["secondary_dark"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    border: none;
    background: none;
}}

QScrollBar:horizontal {{
    background: {COLORS["bg_main"]};
    height: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS["secondary"]};
    min-width: 30px;
    border-radius: 5px;
}}

/* Splitter amélioré */
QSplitter::handle {{
    background-color: {COLORS["border_light"]};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}
QSplitter::handle:hover {{
    background-color: {COLORS["primary"]};
}}
"""

# ============= PANELS & FRAMES =============

STYLE_LEFT_PANEL = f"""
QFrame#left_panel {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 12px;
    {COLORS["shadow_sm"]}
}}
"""

STYLE_RIGHT_FRAME = f"""
QFrame {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 12px;
    {COLORS["shadow_sm"]}
}}
"""

STYLE_CONFIG_BAR = f"""
QFrame {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {COLORS["primary_light"]},
        stop:1 {COLORS["bg_panel"]});
    border-top: 1px solid {COLORS["border_light"]};
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
    padding: 8px;
}}
"""

STYLE_HEADER = f"""
QFrame {{
    background-color: {COLORS["bg_panel"]};
    border-bottom: 1px solid {COLORS["border_light"]};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}}
"""

STYLE_BOTTOM_CONTROLS = f"""
QFrame {{
    background-color: {COLORS["bg_panel"]};
    border-top: 1px solid {COLORS["border_light"]};
    padding: 8px;
}}
"""

# ============= BOUTONS (unifiés et modernes) =============

# Style de base pour tous les boutons
_BASE_BTN = f"""
    border-radius: 8px;
    padding: 2px 8px;
    font-weight: 500;
    font-size: 13px;
    min-height: 32px;
    
"""

STYLE_BTN = f"""
QPushButton {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border_light"]};
    color: {COLORS["text_secondary"]};
    {_BASE_BTN}
}}
QPushButton:hover {{
    background-color: {COLORS["bg_hover"]};
    border-color: {COLORS["border_focus"]};
    color: {COLORS["text_primary"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["primary_light"]};
}}
QPushButton:disabled {{
    background-color: {COLORS["bg_main"]};
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_light"]};
}}
"""

STYLE_BTN_PRIMARY = f"""
QPushButton {{
    background-color: {COLORS["primary"]};
    color: {COLORS["text_on_primary"]};
    border: none;
    {_BASE_BTN}
}}
QPushButton:hover {{
    background-color: {COLORS["primary_dark"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["primary_dark"]};
    padding-top: 9px;
    padding-bottom: 7px;
}}
QPushButton:disabled {{
    background-color: {COLORS["border_focus"]};
    color: {COLORS["bg_main"]};
}}
"""

STYLE_BTN_SECONDARY = f"""
QPushButton {{
    background-color: {COLORS["secondary"]};
    color: {COLORS["text_on_primary"]};
    border: none;
    {_BASE_BTN}
}}
QPushButton:hover {{
    background-color: {COLORS["secondary_dark"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["secondary_dark"]};
}}
"""

STYLE_BTN_DANGER = f"""
QPushButton {{
    background-color: transparent;
    color: {COLORS["danger"]};
    border: 1px solid {COLORS["danger"]};
    {_BASE_BTN}
}}
QPushButton:hover {{
    background-color: {COLORS["danger"]};
    color: {COLORS["text_on_primary"]};
    border-color: {COLORS["danger"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["danger_hover"]};
}}
"""

STYLE_BTN_AI = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #8B5CF6,
        stop:1 #6D28D9);
    color: {COLORS["text_on_primary"]};
    border: none;
    font-weight: 600;
    {_BASE_BTN}
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7C3AED,
        stop:1 #5B21B6);
}}
"""

STYLE_BTN_TOGGLE_TO_AI = f"""
QPushButton {{
    background-color: transparent;
    color: #7C3AED;
    border: 2px solid #8B5CF6;
    border-radius: 20px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: #F5F3FF;
}}
QPushButton:disabled {{
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_light"]};
}}
"""

STYLE_BTN_TOGGLE_TO_MANUAL = f"""
QPushButton {{
    background-color: transparent;
    color: {COLORS["primary"]};
    border: 2px solid {COLORS["primary"]};
    border-radius: 20px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {COLORS["primary_light"]};
}}
"""

CONNECT_BTN_STYLE = f"""
QPushButton {{
    background-color: transparent;
    color: {COLORS["primary"]};
    border: 2px solid {COLORS["primary"]};
    border-radius: 1px;
    padding: 6px 14px;
    min-height: 28px;
    font-weight: 500;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {COLORS["primary_light"]};
    border-width: 2px;
}}
QPushButton:disabled {{
    background-color: {COLORS["bg_main"]};
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_light"]};
}}
"""

# ============= FORMULAIRES & CONTROLES =============

STYLE_FORM_CONTROLS = f"""
QSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 8px;
    padding: 8px 12px;
    color: {COLORS["text_primary"]};
    font-size: 13px;
    selection-background-color: {COLORS["primary_light"]};
}}
QSpinBox:hover, QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover {{
    border-color: {COLORS["border_focus"]};
}}
QSpinBox:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {COLORS["primary"]};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 20px;
    border-radius: 4px;
}}
QComboBox::drop-down {{
    border: none;
    width: 30px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {COLORS["secondary"]};
    margin-right: 8px;
}}
"""

# ============= MENU & TOOLBAR =============

STYLE_MENU_BAR = f"""
QMenuBar {{
    background-color: {COLORS["bg_panel"]};
    border-bottom: 1px solid {COLORS["border_light"]};
    padding: 4px 8px;
}}
QMenuBar::item {{
    spacing: 8px;
    padding: 6px 14px;
    background: transparent;
    color: {COLORS["text_secondary"]};
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background-color: {COLORS["primary_light"]};
    color: {COLORS["primary"]};
}}
QMenuBar::item:pressed {{
    background-color: {COLORS["primary"]};
    color: white;
}}
QMenu {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 10px;
    padding: 6px;
    {COLORS["shadow_md"]}
}}
QMenu::item {{
    padding: 8px 28px 8px 20px;
    color: {COLORS["text_secondary"]};
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {COLORS["primary_light"]};
    color: {COLORS["primary"]};
}}
QMenu::separator {{
    height: 1px;
    background-color: {COLORS["border_light"]};
    margin: 4px 8px;
}}
"""

STYLE_TOOLBAR = f"""
QToolBar {{
    background-color: {COLORS["bg_panel"]};
    border-bottom: 1px solid {COLORS["border_light"]};
    padding: 4px;
    spacing: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    color: {COLORS["text_secondary"]};
    font-weight: 500;
}}
QToolBar QToolButton:hover {{
    background-color: {COLORS["bg_hover"]};
    color: {COLORS["text_primary"]};
}}
QToolBar QToolButton:checked {{
    background-color: {COLORS["primary_light"]};
    color: {COLORS["primary"]};
}}
"""

# ============= TAB WIDGET =============

STYLE_TABS = f"""
QTabWidget::pane {{
    border: 1px solid {COLORS["border_light"]};
    border-radius: 10px;
    background-color: {COLORS["bg_panel"]};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {COLORS["bg_main"]};
    border: 1px solid {COLORS["border_light"]};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 20px;
    margin-right: 2px;
    color: {COLORS["text_secondary"]};
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background-color: {COLORS["bg_panel"]};
    color: {COLORS["primary"]};
    border-bottom: 2px solid {COLORS["primary"]};
}}
QTabBar::tab:hover:!selected {{
    background-color: {COLORS["bg_hover"]};
    color: {COLORS["text_primary"]};
}}
"""

# ============= GROUP BOX =============

STYLE_GROUP_BOX = f"""
QGroupBox {{
    font-weight: 600;
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 12px;
    background-color: {COLORS["bg_panel"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {COLORS["primary"]};
}}
"""

# ============= STATUS BAR =============

STYLE_STATUS_BAR = f"""
QStatusBar {{
    background-color: {COLORS["bg_panel"]};
    border-top: 1px solid {COLORS["border_light"]};
    color: {COLORS["text_secondary"]};
    padding: 4px 8px;
}}
QStatusBar::item {{
    border: none;
}}
"""

# ============= ASSEMBLAGE FINAL =============

STYLE_APP = (
    STYLE_MAIN + 
    STYLE_TABS + 
    STYLE_MENU_BAR + 
    STYLE_FORM_CONTROLS + 
    STYLE_BTN + 
    STYLE_GROUP_BOX + 
    STYLE_STATUS_BAR
)