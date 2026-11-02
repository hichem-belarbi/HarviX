"""
rule_editor.py — Éditeur de règles visuel, moderne et structuré

Chaque règle est affichée sous forme de blocs (chips) sur deux compartiments (Si... => ...),
avec retour à la ligne automatique (Wrap), coloration et suivi du contexte matériel.
"""

import sys
import os
import re

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QPushButton, QLabel, QCheckBox, QComboBox, QSpinBox, 
    QLineEdit, QDialogButtonBox, QDialog, QMessageBox, QToolButton,
    QSizePolicy, QApplication, QLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer, QPoint, QRect
import html as _html_module

from PyQt5.QtGui import (
    QColor, QFont, QTextCharFormat, QSyntaxHighlighter,
    QIcon, QTextDocument
)

from rule_editor.rule_lang import (
    PRIMITIVES, ACTIONS, COMPARE_OPS, TOKEN_COLORS, validate_rule_text
)

from rule_editor.chatbot import ChatbotDialog
from utils.styles import COLORS


# ════════════════════════════════════════════════════
#  Palette de Couleurs
# ════════════════════════════════════════════════════

_BG_PAGE       = COLORS["bg_main"]
_BG_CELL       = COLORS["bg_panel"]
_BG_GUTTER     = COLORS["bg_gutter"]
_BORDER        = COLORS["border_light"]
_BORDER_ERROR  = COLORS["danger"]
_BORDER_OK     = COLORS["success"]
_TEXT          = COLORS["text_primary"]
_TEXT_DIM      = COLORS["text_muted"]
_ERROR_BG      = COLORS["danger_bg"]
_ERROR_TEXT    = COLORS["error_text"]
_WARN_BG       = COLORS["warning_bg"]
_WARN_TEXT     = COLORS["warning_text"]
_SUCCESS_TEXT  = COLORS["success_text"]


# ════════════════════════════════════════════════════
#  FLOW LAYOUT (Pour l'effet Wrap / Retour à la ligne)
# ════════════════════════════════════════════════════

class FlowLayout(QLayout):
    """Layout personnalisé permettant le retour à la ligne automatique (Wrap) des puces."""
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing if spacing >= 0 else 6)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self) -> int:
        return len(self.itemList)

    def itemAt(self, index: int):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Horizontal)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(+left, +top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self.itemList:
            wid = item.widget()
            space_x = self.spacing()
            space_y = self.spacing()
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom


# ════════════════════════════════════════════════════
#  SYNTAX HIGHLIGHTER (Coloration riche des Chips)
# ════════════════════════════════════════════════════

class RuleHighlighter(QSyntaxHighlighter):
    def __init__(self, parent, device_names, output_names):
        super().__init__(parent)
        self.device_names = device_names
        self.output_names = output_names
        self._build_formats()

    def _build_formats(self):
        self._formats = {}
        for token_type, color in TOKEN_COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if token_type in ("device", "output", "primitive", "action"):
                fmt.setFontWeight(QFont.Bold)
            if token_type == "error":
                fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                fmt.setUnderlineColor(QColor(_BORDER_ERROR))
            self._formats[token_type] = fmt

    def highlightBlock(self, text):
        for m in re.finditer(r'\bdevice\d+\b', text):
            t = "device" if m.group() in self.device_names else "error"
            self.setFormat(m.start(), m.end() - m.start(), self._formats[t])

        for m in re.finditer(r'\b(?:sortie|servo)\d+\b', text):
            t = "output" if m.group() in self.output_names else "error"
            self.setFormat(m.start(), m.end() - m.start(), self._formats[t])

        for name in PRIMITIVES:
            for m in re.finditer(rf'\b{name}\b', text):
                self.setFormat(m.start(), m.end() - m.start(), self._formats["primitive"])

        for name in ACTIONS:
            for m in re.finditer(rf'\b{name}\b', text):
                self.setFormat(m.start(), m.end() - m.start(), self._formats["action"])

        for m in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(m.start(), m.end() - m.start(), self._formats["number"])

        for m in re.finditer(r'>=|<=|==|!=|~=|>|<', text):
            self.setFormat(m.start(), m.end() - m.start(), self._formats["operator"])


# ════════════════════════════════════════════════════
#  FORMULAIRE DE CONFIGURATION GRAPHIQUE
# ════════════════════════════════════════════════════

class ConditionRow(QWidget):
    def __init__(self, device_choices: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.device_choices = device_choices
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._operand_combo = QComboBox()
        for name in PRIMITIVES:
            self._operand_combo.addItem(name)
        self._operand_combo.currentTextChanged.connect(self._update_operand_fields)
        layout.addWidget(self._operand_combo)

        self._device_combo = QComboBox()
        for device_id, label in self.device_choices:
            self._device_combo.addItem(label, device_id)
        layout.addWidget(self._device_combo)

        self._window_spin = QSpinBox()
        self._window_spin.setRange(1, 999)
        self._window_spin.setValue(8)
        self._window_spin.setVisible(False)
        layout.addWidget(self._window_spin)

        self._operator_combo = QComboBox()
        for op in COMPARE_OPS:
            self._operator_combo.addItem(op)
        layout.addWidget(self._operator_combo)

        self._rhs_edit = QLineEdit()
        self._rhs_edit.setPlaceholderText("valeur")
        layout.addWidget(self._rhs_edit)

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedWidth(26)
        layout.addWidget(self._remove_btn)

        self._update_operand_fields(self._operand_combo.currentText())

    def _update_operand_fields(self, operand: str):
        if operand == "device":
            self._window_spin.setVisible(False)
        else:
            args = PRIMITIVES.get(operand, {}).get("args", 1)
            self._window_spin.setVisible(args == 2)

    def is_valid(self) -> bool:
        if not self._device_combo.currentData():
            return False
        if not self._rhs_edit.text().strip():
            return False
        return True

    def set_data(self, data: dict):
        primitive = data.get("primitive") or "device"
        self._operand_combo.setCurrentText(primitive)
        device_id = data.get("device", "")
        idx = self._device_combo.findData(device_id)
        if idx != -1:
            self._device_combo.setCurrentIndex(idx)
        else:
            self._device_combo.setCurrentText(device_id)
        if data.get("window") is not None:
            self._window_spin.setValue(data["window"])
        self._operator_combo.setCurrentText(data.get("operator", ">="))
        if data.get("rhs") is not None:
            self._rhs_edit.setText(str(data["rhs"]))

    def to_dict(self) -> dict:
        operand = self._operand_combo.currentText()
        try:
            rhs_val = float(self._rhs_edit.text())
        except ValueError:
            rhs_val = 0.0
        device = self._device_combo.currentData() or self._device_combo.currentText()
        return {
            "primitive": None if operand == "device" else operand,
            "device": device,
            "window": self._window_spin.value() if self._window_spin.isVisible() else None,
            "operator": self._operator_combo.currentText(),
            "rhs": rhs_val,
        }

    def to_text(self) -> str:
        operand = self._operand_combo.currentText()
        device = self._device_combo.currentData() or self._device_combo.currentText()
        if operand == "device":
            left = device
        else:
            args = PRIMITIVES.get(operand, {}).get("args", 1)
            if args == 1:
                left = f"{operand}({device})"
            else:
                left = f"{operand}({device}, {self._window_spin.value()})"
        rhs = self._rhs_edit.text().strip() or "0"
        return f"{left} {self._operator_combo.currentText()} {rhs}"


class ActionRow(QWidget):
    def __init__(self, output_names: list[str], parent=None):
        super().__init__(parent)
        self.output_names = output_names
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._action_combo = QComboBox()
        for name in ACTIONS:
            self._action_combo.addItem(name)
        self._action_combo.currentTextChanged.connect(self._update_action_fields)
        layout.addWidget(self._action_combo)

        self._output_combo = QComboBox()
        for name in self.output_names:
            self._output_combo.addItem(name)
        layout.addWidget(self._output_combo)

        self._param_edit = QSpinBox()
        self._param_edit.setRange(0, 10000)
        self._param_edit.setVisible(False)
        layout.addWidget(self._param_edit)

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedWidth(26)
        layout.addWidget(self._remove_btn)

        self._update_action_fields(self._action_combo.currentText())

    def _update_action_fields(self, action: str):
        args = ACTIONS.get(action, {}).get("args", 0)
        self._output_combo.setVisible(args >= 1)
        self._param_edit.setVisible(args == 2)

    def is_valid(self) -> bool:
        action = self._action_combo.currentText()
        args = ACTIONS.get(action, {}).get("args", 0)
        if args >= 1 and self._output_combo.currentText() == "":
            return False
        return True

    def set_data(self, data: dict):
        self._action_combo.setCurrentText(data.get("action", ""))
        if data.get("output"):
            self._output_combo.setCurrentText(data["output"])
        if data.get("param") is not None:
            self._param_edit.setValue(data["param"])

    def to_dict(self) -> dict:
        action = self._action_combo.currentText()
        return {
            "action": action,
            "output": self._output_combo.currentText() if action not in ("log", "stream") else None,
            "param": self._param_edit.value() if action in ("rotation", "pwm", "pulse") else None,
        }

    def to_text(self) -> str:
        action = self._action_combo.currentText()
        if ACTIONS.get(action, {}).get("args", 0) == 0:
            return action
        output = self._output_combo.currentText()
        if ACTIONS[action]["args"] == 1:
            return f"{action}({output})"
        return f"{action}({output}, {self._param_edit.value()})"


class RuleFormDialog(QDialog):
    def __init__(self, device_choices: list[tuple[str, str]], output_names: list[str], rule_data: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modifier la règle" if rule_data else "Nouvelle règle")
        icon_name = "edit.png" if rule_data else "add_rulle.png"
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "..", "icons", icon_name)))
        self.setModal(True)
        self.device_choices = device_choices
        self.output_names = output_names
        self.rule_data = rule_data
        self._condition_rows: list[ConditionRow] = []
        self._action_rows: list[ActionRow] = []
        self._build()
        
        if self.rule_data:
            self._load_rule_data()
        else:
            self._add_condition_row()
            self._add_action_row()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QLabel("Configuration de la règle")
        header.setStyleSheet("font-weight: bold; font-size: 14px; border:none;")
        root.addWidget(header)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nom de règle:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("ex: gestion_temperature")
        name_layout.addWidget(self._name_edit, stretch=1)
        root.addLayout(name_layout)

        self._conditions_box = QVBoxLayout()
        root.addWidget(QLabel("Conditions (ET)"))
        root.addLayout(self._conditions_box)

        button_style = "QPushButton { background-color: transparent; border: 1px dashed grey; color: grey; margin-top: 4px; padding: 6px; border-radius: 6px; } QPushButton:hover { border-color: #2563eb; color: #2563eb; }"

        add_cond_btn = QPushButton("+ Ajouter une condition")
        add_cond_btn.setStyleSheet(button_style)
        add_cond_btn.clicked.connect(self._add_condition_row)
        root.addWidget(add_cond_btn)

        self._actions_box = QVBoxLayout()
        root.addWidget(QLabel("Actions"))
        root.addLayout(self._actions_box)

        add_act_btn = QPushButton("+ Ajouter une action")
        add_act_btn.setStyleSheet(button_style)
        add_act_btn.clicked.connect(self._add_action_row)
        root.addWidget(add_act_btn)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        root.addWidget(button_box)

    def _load_rule_data(self):
        self._name_edit.setText(self.rule_data.get("structured", {}).get("name", ""))
        structured = self.rule_data.get("structured", {})
        
        for cond in structured.get("conditions", []):
            row = self._add_condition_row()
            row.set_data(cond)
            
        for act in structured.get("actions", []):
            row = self._add_action_row()
            row.set_data(act)

    def _add_condition_row(self) -> ConditionRow:
        row = ConditionRow(self.device_choices)
        row._remove_btn.clicked.connect(lambda: self._remove_condition_row(row))
        self._condition_rows.append(row)
        self._conditions_box.addWidget(row)
        return row

    def _remove_condition_row(self, row: ConditionRow):
        if len(self._condition_rows) > 1:
            self._condition_rows.remove(row)
            self._conditions_box.removeWidget(row)
            row.deleteLater()

    def _add_action_row(self) -> ActionRow:
        row = ActionRow(self.output_names)
        row._remove_btn.clicked.connect(lambda: self._remove_action_row(row))
        self._action_rows.append(row)
        self._actions_box.addWidget(row)
        return row

    def _remove_action_row(self, row: ActionRow):
        if len(self._action_rows) > 1:
            self._action_rows.remove(row)
            self._actions_box.removeWidget(row)
            row.deleteLater()

    def _validate(self) -> bool:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Le nom de la règle est requis.")
            return False
        return True

    def _on_accept(self):
        if not self._validate():
            return
        self.accept()

    def get_rule_data(self) -> dict:
        conditions = [row.to_dict() for row in self._condition_rows]
        actions = [row.to_dict() for row in self._action_rows]
        
        cond_text = " & ".join(row.to_text() for row in self._condition_rows)
        act_text = " & ".join(row.to_text() for row in self._action_rows)
        full_text = f"{self._name_edit.text().strip()}:\n{cond_text} => {act_text}"

        return {
            "name": self._name_edit.text().strip(),
            "text": full_text,
            "structured": {
                "name": self._name_edit.text().strip(),
                "conditions": conditions,
                "actions": actions,
            },
        }


# ════════════════════════════════════════════════════
#  CELLULE VISUELLE : DEUX COMPARTIMENTS ET WRAP EFFECT
# ════════════════════════════════════════════════════

class RuleCell(QFrame):
    changed = pyqtSignal()
    edit_requested = pyqtSignal(int)
    deleted = pyqtSignal(int)

    def __init__(self, rule_id: int, enabled: bool = True,
                 device_names: set = None, output_names: set = None,
                 structured: dict = None, parent=None):
        super().__init__(parent)
        self.rule_id = rule_id
        self._device_names = device_names or set()
        self._output_names = output_names or set()
        self._errors = []
        self._structured = structured or {"name": f"regle_{rule_id}", "conditions": [], "actions": []}
        
        self._build(enabled)

    def _build(self, enabled):
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet(f"RuleCell {{ background-color: {_BG_CELL}; border: 1.5px solid {_BORDER}; border-radius: 8px; margin: 4px 0px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Entête (Header) ──────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(f"background-color: {_BG_GUTTER}; border-bottom: 1px solid {_BORDER}; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        header.setFixedHeight(34)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 4, 10, 4)

        self._enabled_cb = QCheckBox()
        self._enabled_cb.setChecked(enabled)
        self._enabled_cb.stateChanged.connect(lambda: self.changed.emit())
        h_layout.addWidget(self._enabled_cb)

        self._title_label = QLabel(self._structured.get("name", ""))
        self._title_label.setStyleSheet(f"color: {_TEXT}; font-weight: bold; font-size: 12px; border: none;")
        h_layout.addWidget(self._title_label)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-size: 11px; border: none; margin-left: 8px;")
        h_layout.addWidget(self._status_label)

        h_layout.addStretch()

        icons_dir = os.path.join(os.path.dirname(__file__), "..", "icons")

        edit_btn = QToolButton()
        edit_btn.setIcon(QIcon(os.path.join(icons_dir, "edit.png")))
        edit_btn.setIconSize(QSize(18, 18))
        edit_btn.setFixedSize(30, 30)
        edit_btn.setToolTip("Modifier la règle")
        edit_btn.setStyleSheet(f"QToolButton {{ background-color: transparent; border: none; padding: 4px; border-radius: 6px; }} QToolButton:hover {{ background-color: rgba(0, 0, 0, 0.05); }}")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.rule_id))
        h_layout.addWidget(edit_btn)

        del_btn = QToolButton()
        del_btn.setIcon(QIcon(os.path.join(icons_dir, "delete.png")))
        del_btn.setIconSize(QSize(18, 18))
        del_btn.setFixedSize(30, 30)
        del_btn.setToolTip("Supprimer la règle")
        del_btn.setStyleSheet(f"QToolButton {{ background-color: transparent; border: none; padding: 4px; border-radius: 6px; }} QToolButton:hover {{ background-color: rgba(0, 0, 0, 0.05); }}")
        del_btn.clicked.connect(lambda: self.deleted.emit(self.rule_id))
        h_layout.addWidget(del_btn)

        layout.addWidget(header)

        # ── Zone Visuelle Structurée à 2 compartiments (Vertical) ─────────
        body = QWidget()
        body.setStyleSheet("background-color: white; border: none;border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(10)

        # Compartiment supérieur : SI (Conditions)
        cond_row_wrapper = QHBoxLayout()
        si_lbl = QLabel("SI")
        si_lbl.setStyleSheet("color: #9CA3AF; font-size: 16px; font-weight: bold; min-width: 20px;")
        cond_row_wrapper.addWidget(si_lbl, alignment=Qt.AlignTop)
        
        self._cond_container = QWidget()
        self._cond_layout = FlowLayout(self._cond_container) # Gestion automatique du Wrap
        cond_row_wrapper.addWidget(self._cond_container, stretch=1)
        body_layout.addLayout(cond_row_wrapper)

        # Compartiment inférieur : ALORS (Actions)
        act_row_wrapper = QHBoxLayout()
        alors_lbl = QLabel("=>")
        alors_lbl.setStyleSheet("color: #9CA3AF; font-size: 16px; font-weight: bold; min-width: 20px;")
        act_row_wrapper.addWidget(alors_lbl, alignment=Qt.AlignTop)

        self._act_container = QWidget()
        self._act_layout = FlowLayout(self._act_container) # Gestion automatique du Wrap
        act_row_wrapper.addWidget(self._act_container, stretch=1)
        body_layout.addLayout(act_row_wrapper)

        layout.addWidget(body)

        # ── Bandeau d'erreurs ────────────────────────────────────────────
        self._error_bar = QLabel()
        self._error_bar.setWordWrap(True)
        self._error_bar.hide()
        layout.addWidget(self._error_bar)

        self.rebuild_chips()

    def update_rule(self, name: str, structured: dict):
        self._structured = structured
        self._title_label.setText(name)
        self.rebuild_chips()
        self.changed.emit()

    def update_context(self, device_names: set, output_names: set):
        self._device_names = device_names
        self._output_names = output_names
        self.rebuild_chips()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def rebuild_chips(self):
        self._clear_layout(self._cond_layout)
        self._clear_layout(self._act_layout)

        # Reconstruction du compartiment "Si" (Conditions)
        conds = self._structured.get("conditions", [])
        for i, c in enumerate(conds):
            if i > 0:
                lbl = QLabel("&")
                lbl.setStyleSheet("color: #9CA3AF; font-weight: bold;")
                self._cond_layout.addWidget(lbl)
            
            primitive = c.get("primitive")
            device = c.get("device", "")
            op = c.get("operator", "==")
            rhs = c.get("rhs", "0")
            
            if not primitive:
                text = f"{device} {op} {rhs}"
            else:
                window = c.get("window")
                text = f"{primitive}({device}, {window}) {op} {rhs}" if window else f"{primitive}({device}) {op} {rhs}"
            
            self._cond_layout.addWidget(self._create_chip(text))

        # Reconstruction du compartiment "=>" (Actions)
        acts = self._structured.get("actions", [])
        for i, a in enumerate(acts):
            if i > 0:
                lbl = QLabel("&")
                lbl.setStyleSheet("color: #9CA3AF; font-weight: bold;")
                self._act_layout.addWidget(lbl)
                
            action = a.get("action", "")
            output = a.get("output")
            param = a.get("param")
            
            if not output:
                text = f"{action}"
            else:
                text = f"{action}({output}, {param})" if param is not None else f"{action}({output})"
                
            self._act_layout.addWidget(self._create_chip(text))

        QTimer.singleShot(30, self._validate_context)

    def _colorize_text(self, text: str) -> str:
        """Return an HTML string with token colours applied directly."""
        length = len(text)
        colors = [None] * length
        bold   = [False] * length

        def apply(start, end, color, is_bold=False):
            for i in range(start, end):
                colors[i] = color
                if is_bold:
                    bold[i] = True

        for m in re.finditer(r'\bdevice\d+\b', text):
            t = "device" if m.group() in self._device_names else "error"
            apply(m.start(), m.end(), TOKEN_COLORS[t], t == "device")

        for m in re.finditer(r'\b(?:sortie|servo)\d+\b', text):
            t = "output" if m.group() in self._output_names else "error"
            apply(m.start(), m.end(), TOKEN_COLORS[t], t == "output")

        for name in PRIMITIVES:
            for m in re.finditer(rf'\b{re.escape(name)}\b', text):
                apply(m.start(), m.end(), TOKEN_COLORS["primitive"], True)

        for name in ACTIONS:
            for m in re.finditer(rf'\b{re.escape(name)}\b', text):
                apply(m.start(), m.end(), TOKEN_COLORS["action"], True)

        for m in re.finditer(r'\b\d+\.?\d*\b', text):
            apply(m.start(), m.end(), TOKEN_COLORS["number"])

        for m in re.finditer(r'>=|<=|==|!=|~=|>|<', text):
            apply(m.start(), m.end(), TOKEN_COLORS["operator"])

        # Build HTML by grouping consecutive chars with the same style
        result = []
        i = 0
        while i < length:
            c, b = colors[i], bold[i]
            j = i + 1
            while j < length and colors[j] == c and bold[j] == b:
                j += 1
            chunk = _html_module.escape(text[i:j])
            if c or b:
                style = f"color:{c};" if c else ""
                if b:
                    style += "font-weight:bold;"
                chunk = f'<span style="{style}">{chunk}</span>'
            result.append(chunk)
            i = j

        return "".join(result)

    def _create_chip(self, text: str) -> QLabel:
        chip = QLabel()
        chip.setTextFormat(Qt.RichText)
        chip.setText(self._colorize_text(text))
        chip.setStyleSheet("""
            QLabel {
                background-color: #F3F4F6;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 3px 8px;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)
        return chip

    def _validate_context(self):
        cond_text = " & ".join(self._create_chip_text(c, is_cond=True) for c in self._structured.get("conditions", []))
        act_text = " & ".join(self._create_chip_text(a, is_cond=False) for a in self._structured.get("actions", []))
        full_text = f"{self._structured.get('name')}:\n{cond_text} => {act_text}"

        self._errors = validate_rule_text(full_text, self._device_names, self._output_names)

        if not self._errors:
            self._status_label.setText("✓ valide")
            self._status_label.setStyleSheet(f"color: {_SUCCESS_TEXT}; font-weight: bold;")
            self.setStyleSheet(f"RuleCell {{ background-color: {_BG_CELL}; border: 1.5px solid {_BORDER_OK}; border-radius: 8px; margin: 4px 0px; }}")
            self._error_bar.hide()
        else:
            has_error = any(e["severity"] == "error" for e in self._errors)
            self._status_label.setText(f"✕ {len(self._errors)} erreur(s)" if has_error else f"⚠ {len(self._errors)} alerte(s)")
            self._status_label.setStyleSheet(f"color: {_ERROR_TEXT if has_error else _WARN_TEXT}; font-weight: bold;")
            self.setStyleSheet(f"RuleCell {{ background-color: {_BG_CELL}; border: 1.5px solid {_BORDER_ERROR if has_error else _BORDER}; border-radius: 8px; margin: 4px 0px; }}")
            
            msgs = "\n".join(f"• {e['message']}" for e in self._errors)
            self._error_bar.setText(msgs)
            self._error_bar.setStyleSheet(f"QLabel {{ background-color: {_ERROR_BG if has_error else _WARN_BG}; color: {_ERROR_TEXT if has_error else _WARN_TEXT}; padding: 6px 12px; font-size: 11px; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; border-top: 1px solid {_BORDER}; }}")
            self._error_bar.show()

    def _create_chip_text(self, data: dict, is_cond: bool) -> str:
        if is_cond:
            primitive = data.get("primitive")
            device = data.get("device", "")
            op = data.get("operator", "==")
            rhs = data.get("rhs", "0")
            if not primitive: return f"{device} {op} {rhs}"
            w = data.get("window")
            return f"{primitive}({device}, {w}) {op} {rhs}" if w else f"{primitive}({device}) {op} {rhs}"
        else:
            action = data.get("action", "")
            output = data.get("output")
            param = data.get("param")
            if not output: return action
            return f"{action}({output}, {param})" if param is not None else f"{action}({output})"

    def get_rule_dict(self) -> dict:
        cond_text = " & ".join(self._create_chip_text(c, is_cond=True) for c in self._structured.get("conditions", []))
        act_text = " & ".join(self._create_chip_text(a, is_cond=False) for a in self._structured.get("actions", []))
        full_text = f"{self._structured.get('name')}:\n{cond_text} => {act_text}"

        return {
            "rule_id": self.rule_id,
            "priority": 0,
            "enabled": self._enabled_cb.isChecked(),
            "text": full_text,
            "structured": self._structured
        }


# ════════════════════════════════════════════════════
#  PANNEAU PRINCIPAL ET COMPATIBILITÉ RESTAURÉE
# ════════════════════════════════════════════════════

class RuleEditor(QWidget):
    rules_changed = pyqtSignal()

    def __init__(self, appareil, parent=None):
        super().__init__(parent)
        self.appareil = appareil
        self._next_rule_id = 1
        self._cells: list[RuleCell] = []
        self._chatbot_dialog = None

        self._build()
        self._load_existing_rules()

    def _build(self):
        self.setStyleSheet(f"background-color: {_BG_PAGE};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(f"background-color: white; border-bottom: 1px solid {_BORDER}; padding: 4px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 10, 16, 10)
        h_layout.addStretch()

        self._count_label = QLabel()
        self._count_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 12px;")
        h_layout.addWidget(self._count_label)
        
        icons_dir = os.path.join(os.path.dirname(__file__), "..", "icons")

        chatbot_btn = QPushButton()
        chatbot_btn.setIcon(QIcon(os.path.join(icons_dir, "rules_chatbot.png")))
        chatbot_btn.setIconSize(QSize(25, 25))
        chatbot_btn.setFixedSize(38, 38)
        chatbot_btn.setStyleSheet("QPushButton { background-color: transparent; border: none; border-radius: 10px; } QPushButton:hover { background-color: rgba(0, 0, 0, 0.05); }")
        chatbot_btn.clicked.connect(self._open_chatbot)
        h_layout.addWidget(chatbot_btn)

        add_btn = QPushButton()
        add_btn.setIcon(QIcon(os.path.join(icons_dir, "add_rulle.png")))
        add_btn.setIconSize(QSize(25, 25))
        add_btn.setFixedSize(38, 38)
        add_btn.setStyleSheet("QPushButton { background-color: transparent; border: none; border-radius: 10px; } QPushButton:hover { background-color: rgba(0, 0, 0, 0.05); }")
        add_btn.clicked.connect(self._open_new_rule_form)
        h_layout.addWidget(add_btn)

        root.addWidget(header)

        ref_bar = QFrame()
        ref_bar.setStyleSheet(f"background-color: #F9FAFB; border-bottom: 1px solid {_BORDER};")
        ref_layout = QHBoxLayout(ref_bar)
        ref_layout.setContentsMargins(16, 6, 16, 6)
        
        catalogue_label = QLabel()
        catalogue_label.setPixmap(QIcon(os.path.join(icons_dir, "catalogue.png")).pixmap(QSize(20, 20)))
        ref_layout.addWidget(catalogue_label)

        self._ref_label = QLabel()
        self._ref_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 11px; border: none;")
        ref_layout.addWidget(self._ref_label, stretch=1)
        self._device_labels = {}
        root.addWidget(ref_bar)
        self._update_ref_label()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {_BG_PAGE}; }}")

        self._cells_container = QWidget()
        self._cells_layout = QVBoxLayout(self._cells_container)
        self._cells_layout.setContentsMargins(16, 12, 16, 12)
        self._cells_layout.setSpacing(8)
        self._cells_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self._cells_container)
        root.addWidget(scroll, stretch=1)
        self._update_count()

    def reload_rules(self):
        """Méthode requise par configurator.py pour recharger dynamiquement l'interface."""
        self.refresh_context()

    def refresh_context(self):
        """Met à jour les références matérielles globales et revérifie la validité contextuelle."""
        device_names, output_names, device_labels = self._get_known_names()
        self._device_labels = device_labels
        self._update_ref_label()
        for cell in self._cells:
            cell.update_context(device_names, output_names)
        self._update_count()

    def _open_new_rule_form(self):
        device_names, output_names, device_labels = self._get_known_names()
        device_choices = sorted(device_labels.items(), key=lambda item: item[0])
        dialog = RuleFormDialog(device_choices, sorted(output_names), parent=self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_rule_data()
            self._add_cell(enabled=True, structured=data["structured"])

    def _open_edit_rule_form(self, rule_id: int):
        cell = next((c for c in self._cells if c.rule_id == rule_id), None)
        if not cell: return
        
        device_names, output_names, device_labels = self._get_known_names()
        current_data = cell.get_rule_dict()
        
        dialog = RuleFormDialog(sorted(device_labels.items(), key=lambda item: item[0]), sorted(output_names), rule_data=current_data, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_rule_data()
            cell.update_rule(name=new_data["name"], structured=new_data["structured"])

    def _add_cell(self, enabled: bool = True, structured: dict = None, emit: bool = True) -> RuleCell:
        rid = self._next_rule_id
        self._next_rule_id += 1

        device_names, output_names, _ = self._get_known_names()
        cell = RuleCell(rule_id=rid, enabled=enabled, device_names=device_names, output_names=output_names, structured=structured)
        
        cell.changed.connect(self._on_cell_changed)
        cell.edit_requested.connect(self._open_edit_rule_form)
        cell.deleted.connect(self._delete_cell)

        self._cells_layout.addWidget(cell)
        self._cells.append(cell)
        self._update_count()
        if emit: self.rules_changed.emit()
        return cell

    def _delete_cell(self, rule_id: int):
        for cell in self._cells:
            if cell.rule_id == rule_id:
                self._cells.remove(cell)
                self._cells_layout.removeWidget(cell)
                cell.deleteLater()
                break
        self._update_count()
        self.rules_changed.emit()

    def _on_cell_changed(self):
        self._update_count()
        self.rules_changed.emit()

    def _open_chatbot(self):
        if self._chatbot_dialog is None or not self._chatbot_dialog.isVisible():
            device_names, output_names, device_labels = self._get_known_names()
            self._chatbot_dialog = ChatbotDialog(self, device_names, output_names, device_labels)
            self._chatbot_dialog.rule_generated.connect(
                lambda txt: self._add_cell(structured={"name": "ChatbotRule", "conditions": [], "actions": []})
            )
        self._chatbot_dialog.show()

    def _format_device_display(self, device) -> str:
        device_id = f"device{device.uid}"
        q_label = self.appareil.get_qty_label(device.quantity)
        unit = self.appareil.get_qty_unit(device.quantity)
        unit_str = f" {unit}" if unit else ""
        model_str = device.model.lower() if getattr(device, 'model', None) else ""
        return f"{q_label}{unit_str} [{device_id}:{model_str}]"

    def _get_known_names(self) -> tuple[set, set, dict[str, str]]:
        devices = self.appareil.get_all_devices()
        device_names = set()
        device_labels = {}
        for d in devices:
            dev = d['device']
            name = f"device{dev.uid}"
            device_names.add(name)
            device_labels[name] = self._format_device_display(dev)
        outputs = self.appareil.get_active_outputs()
        output_names = set()
        for o in outputs:
            prefix = "servo" if o.type == "pwm" else "sortie"
            output_names.add(f"{prefix}{o.output_id}")
        return device_names, output_names, device_labels

    def _update_ref_label(self):
        devices = self.appareil.get_all_devices()
        outputs = self.appareil.get_active_outputs()
        parts = []
        if devices:
            labels = []
            for d in devices:
                key = f"device{d['device'].uid}"
                labels.append(self._device_labels.get(key, key) if hasattr(self, '_device_labels') else key)
            parts.append("Capteurs: " + ", ".join(labels))
        if outputs:
            parts.append("Sorties: " + ", ".join([f"{'servo' if o.type == 'pwm' else 'sortie'}{o.output_id}" for o in outputs]))
        self._ref_label.setText("  |  ".join(parts) if parts else "Aucun matériel configuré.")

    def _update_count(self):
        n = len(self._cells)
        valid = sum(1 for c in self._cells if not any(e["severity"] == "error" for e in c._errors))
        self._count_label.setText(f"{valid}/{n} valide(s)")

    def get_all_rules(self) -> list[dict]:
        return [cell.get_rule_dict() for cell in self._cells]

    def _load_existing_rules(self):
        for r in self.appareil.rules:
            if isinstance(r, dict) and "structured" in r:
                self._add_cell(enabled=r.get("enabled", True), structured=r.get("structured"), emit=False)
                if r.get("rule_id", 0) >= self._next_rule_id:
                    self._next_rule_id = r["rule_id"] + 1

    def clear_rules(self):
        for cell in list(self._cells):
            self._cells_layout.removeWidget(cell)
            cell.deleteLater()
        self._cells.clear()
        self._next_rule_id = 1
        self._update_count()

    def save_to_appareil(self):
        self.appareil.rules = self.get_all_rules()