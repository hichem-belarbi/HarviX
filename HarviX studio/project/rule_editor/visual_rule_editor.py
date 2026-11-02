"""
visual_rule_editor.py — Éditeur graphique de règles (blocs + fils)

Fixes & ajouts :
  ✓ Double-clic sur sous-bloc  → EditDialog fonctionnel (parent = QGraphicsView)
  ✓ EditDialog avec ComboBox   → devices / outputs / opérateurs préremplis
  ✓ Clic droit sur fil         → menu "Couper ce fil"
  ✓ Clic droit sur bloc        → menu "Supprimer"
  ✓ Snap à la grille (20 px)
  ✓ Port gauche déjà connecté  → refusé (évite les connexions multiples)
  ✓ Touche Suppr               → supprime la sélection
  ✓ Touche R                   → reset zoom
  ✓ Export to_rule_text()      → texte compatible rule_lang.py
  ✓ Status bar live            → affiche la règle générée en temps réel
  ✓ Toolbar "Exporter"         → dialog avec le texte de règle
  ✓ Blocs pré-peuplés          → devices / outputs de l'appareil
"""

import sys
import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsPathItem, QGraphicsProxyWidget,
    QPushButton, QLabel, QFrame, QMenu, QInputDialog,
    QComboBox, QApplication, QSizePolicy, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
)
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPainterPath, QColor, QBrush, QPen, QFont,
    QTransform,
)
from rule_editor.rule_lang import ACTIONS,COMPARE_OPS,PRIMITIVES

# ════════════════════════════════════════════════════
#  Palette de couleurs
# ════════════════════════════════════════════════════

C_BG          = QColor("#F8F9FA")
C_GRID        = QColor("#E8EBF0")
C_GRID_BOLD   = QColor("#D1D5DB")
C_COND        = QColor("#1E3A5F")
C_LOGIC       = QColor("#7C3AED")
C_START       = QColor("#10B981")   # vert émeraude — start node
C_START_LIGHT = QColor("#34D399")
C_ACTION      = QColor("#DC2626")
C_PWM         = QColor("#EA580C")
C_FUNC        = QColor("#6D28D9")
C_DEVICE      = QColor("#059669")
C_VALUE       = QColor("#D97706")
C_OPERATOR    = QColor("#B45309")
C_PORT        = QColor("#2563eb")
C_PORT_HOVER  = QColor("#93C5FD")
C_WIRE        = QColor("#6B7280")
C_WIRE_ACTIVE = QColor("#2563eb")
C_WIRE_HOVER  = QColor("#EF4444")
C_SELECT      = QColor("#2563eb")
C_TEXT        = QColor("#FFFFFF")

PORT_RADIUS = 6
BLOCK_RADIUS = 6
GRID_SIZE = 20


# ════════════════════════════════════════════════════
#  EDIT DIALOG
# ════════════════════════════════════════════════════

class EditDialog(QDialog):
    """Dialog d'édition d'un sous-bloc avec texte libre ou ComboBox."""

    def __init__(self, title: str, current: str, choices: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(300)
        self.setStyleSheet("""
            QDialog  { background: #FFFFFF; }
            QLabel   { color: #374151; font-size: 13px; }
            QLineEdit, QComboBox {
                border: 1px solid #D1D5DB; border-radius: 4px;
                padding: 7px; font-size: 13px; color: #1F2937; background: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #2563eb; }
            QPushButton {
                background: #2563eb; color: white; border: none;
                border-radius: 4px; padding: 8px 20px; font-weight: 600; font-size: 12px;
            }
            QPushButton:hover { background: #2563EB; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()
        form.setSpacing(8)

        if choices:
            self._w = QComboBox()
            self._w.setEditable(True)
            self._w.addItems(choices)
            self._w.setCurrentText(current)
        else:
            self._w = QLineEdit(current)
            self._w.selectAll()

        form.addRow("Valeur :", self._w)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._w.setFocus()
        if isinstance(self._w, QLineEdit):
            self._w.returnPressed.connect(self.accept)

    def value(self) -> str:
        if isinstance(self._w, QComboBox):
            return self._w.currentText().strip()
        return self._w.text().strip()


# ════════════════════════════════════════════════════
#  PORT
# ════════════════════════════════════════════════════

class Port(QGraphicsEllipseItem):
    def __init__(self, parent_block, side, index=0):
        r = PORT_RADIUS
        super().__init__(-r, -r, 2*r, 2*r, parent_block)
        self.parent_block = parent_block
        self.side  = side
        self.index = index
        self.wires: list = []

        self.setBrush(QBrush(C_PORT))
        self.setPen(QPen(Qt.white, 1.5))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)

    def center_scene(self) -> QPointF:
        return self.scenePos()

    def is_connected(self) -> bool:
        return len(self.wires) > 0

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(C_PORT_HOVER))
        self.setScale(1.4)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(C_PORT))
        self.setScale(1.0)
        super().hoverLeaveEvent(event)


# ════════════════════════════════════════════════════
#  WIRE
# ════════════════════════════════════════════════════

class Wire(QGraphicsPathItem):
    def __init__(self, source_port, dest_port=None):
        super().__init__()
        self.source   = source_port
        self.dest     = dest_port
        self.temp_end = None
        self._hovered = False

        self.setPen(QPen(C_WIRE, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        if source_port:
            source_port.wires.append(self)
        if dest_port:
            dest_port.wires.append(self)
            self.update_path()

    def set_dest(self, port):
        self.dest = port
        if port:
            port.wires.append(self)
        self.update_path()

    def update_path(self):
        if not self.source:
            return
        p1 = self.source.center_scene()

        if self.dest:
            p2 = self.dest.center_scene()
            color = C_WIRE_HOVER if self._hovered else C_WIRE_ACTIVE
            self.setPen(QPen(color, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        elif self.temp_end:
            p2 = self.temp_end
            self.setPen(QPen(C_WIRE, 2, Qt.DashLine, Qt.RoundCap))
        else:
            return

        path = QPainterPath()
        path.moveTo(p1)
        dx = max(abs(p2.x() - p1.x()) * 0.5, 40)
        path.cubicTo(QPointF(p1.x() + dx, p1.y()),
                     QPointF(p2.x() - dx, p2.y()), p2)

        # Pointe de flèche
        if self.dest:
            angle  = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            size   = 10
            path.lineTo(p2.x() - size * math.cos(angle - math.pi/6),
                        p2.y() - size * math.sin(angle - math.pi/6))
            path.moveTo(p2)
            path.lineTo(p2.x() - size * math.cos(angle + math.pi/6),
                        p2.y() - size * math.sin(angle + math.pi/6))

        self.setPath(path)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update_path()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update_path()
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu   = QMenu()
        del_a  = menu.addAction("✂  Couper ce fil")
        act    = menu.exec_(event.screenPos())
        if act == del_a:
            self.remove()

    def remove(self):
        if self.source and self in self.source.wires:
            self.source.wires.remove(self)
        if self.dest and self in self.dest.wires:
            self.dest.wires.remove(self)
        if self.scene():
            self.scene().removeItem(self)


# ════════════════════════════════════════════════════
#  SUB-BLOCK (ComboBox dans GraphicsProxyWidget)
# ════════════════════════════════════════════════════

class SubBlock(QGraphicsProxyWidget):
    """ComboBox éditable intégré dans un bloc."""

    def __init__(self, parent_block, x, y, w, h, color, text,
                 editable=False, choices: list = None, role: str = ""):
        super().__init__(parent_block)

        self.parent_block = parent_block
        self._color   = color
        self._initial = text
        self.editable = editable
        self.choices  = choices or []
        self.role     = role

        # Créer le ComboBox
        self._combo = QComboBox()
        self._combo.setEditable(editable)
        self._combo.setMaxVisibleItems(8)
        self._combo.setFixedSize(int(w), int(h))
        
        # Ajouter les suggestions
        if self.choices:
            self._combo.addItems([str(c) for c in self.choices])
        
        # Définir la valeur actuelle
        idx = -1
        if self.choices and text in [str(c) for c in self.choices]:
            idx = [str(c) for c in self.choices].index(text)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            self._combo.setCurrentText(text)
        
        # Style
        bg_color = color.name()
        fg_color = "#FFFFFF"
        self._combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {bg_color};
                color: {fg_color};
                border: 1px solid {color.darker(140).name()};
                border-radius: 3px;
                padding: 2px;
                font-weight: 600;
                font-size: 10px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: white;
                color: #1F2937;
                selection-background-color: {bg_color};
                border: 1px solid #D1D5DB;
            }}
        """)
        
        self.setWidget(self._combo)
        self.setPos(x, y)
        self.setZValue(6)
        
        # Connecter le signal de changement
        self._combo.currentTextChanged.connect(self._on_changed)

    def _on_changed(self, text):
        if hasattr(self.parent_block, "on_sub_changed"):
            self.parent_block.on_sub_changed(self)

    def set_text(self, text: str):
        self._combo.blockSignals(True)
        self._combo.setCurrentText(text)
        self._combo.blockSignals(False)

    def update_choices(self, choices: list):
        self.choices = choices or []
        current = self.text
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems([str(c) for c in self.choices])
        self._combo.setCurrentText(current)
        self._combo.blockSignals(False)

    @property
    def text(self) -> str:
        return self._combo.currentText().strip()


# ════════════════════════════════════════════════════
#  BASE BLOCK
# ════════════════════════════════════════════════════

class Block(QGraphicsRectItem):
    def __init__(self, width, height, color, label="", block_type="generic"):
        super().__init__(0, 0, width, height)
        self.block_type   = block_type
        self.color        = color
        self._label       = label
        self._ports_left : list[Port]     = []
        self._ports_right: list[Port]     = []
        self._sub_blocks : list[SubBlock] = []

        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(130), 1.5))
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)

    def add_port(self, side, index=0) -> Port:
        p = Port(self, side, index)
        (self._ports_left if side == "left" else self._ports_right).append(p)
        self._position_ports()
        return p

    def remove_port(self, side, index=0):
        ports = self._ports_left if side == "left" else self._ports_right
        if index < len(ports):
            port = ports.pop(index)
            # Supprimer les fils connectés
            for wire in list(port.wires):
                wire.remove()
            # Repositionner les ports restants
            self._position_ports()
            return True
        return False

    def add_input_port(self):
        """Ajoute un port d'entrée (pour blocs logiques)"""
        self.add_port("left", len(self._ports_left))

    def remove_input_port(self):
        """Supprime le dernier port d'entrée (minimum 2)"""
        if len(self._ports_left) > 2:
            self.remove_port("left", len(self._ports_left) - 1)

    def _position_ports(self):
        h, w = self.rect().height(), self.rect().width()
        for i, p in enumerate(self._ports_left):
            p.setPos(0, h * (i + 1) / (len(self._ports_left) + 1))
        for i, p in enumerate(self._ports_right):
            p.setPos(w, h * (i + 1) / (len(self._ports_right) + 1))

    def get_port(self, side, index=0) -> Port | None:
        ports = self._ports_left if side == "left" else self._ports_right
        return ports[index] if index < len(ports) else None

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.setBrush(self.brush())
        pen = QPen(self.color.darker(140), 2)
        if self.isSelected():
            pen = QPen(C_SELECT, 2.5)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, BLOCK_RADIUS, BLOCK_RADIUS)
        if self._label and not self._sub_blocks:
            painter.setPen(QPen(C_TEXT))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, self._label)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Snap à la grille
            return QPointF(round(value.x() / GRID_SIZE) * GRID_SIZE,
                           round(value.y() / GRID_SIZE) * GRID_SIZE)
        if change == QGraphicsItem.ItemPositionHasChanged:
            for p in self._ports_left + self._ports_right:
                for w in p.wires:
                    w.update_path()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        menu   = QMenu()
        del_a  = menu.addAction("🗑  Supprimer le bloc")
        info_a = menu.addAction(f"ℹ  {self.block_type}")
        info_a.setEnabled(False)
        
        # Options pour blocs logiques
        if self.block_type == "logic":
            menu.addSeparator()
            add_port_a = menu.addAction("➕ Ajouter entrée")
            if len(self._ports_left) > 2:
                rem_port_a = menu.addAction("➖ Supprimer entrée")
        
        act = menu.exec_(event.screenPos())
        if act == del_a:
            self._delete()
        elif self.block_type == "logic" and act == add_port_a:
            self.add_input_port()
        elif self.block_type == "logic" and 'rem_port_a' in locals() and act == rem_port_a:
            self.remove_input_port()

    def _delete(self):
        for p in self._ports_left + self._ports_right:
            for w in list(p.wires):
                w.remove()
        if self.scene():
            self.scene().removeItem(self)

    def on_sub_changed(self, sub: SubBlock):
        pass   # hook pour sous-classes

    def to_token(self) -> str:
        return ""


# ════════════════════════════════════════════════════
#  BLOCK FACTORIES
# ════════════════════════════════════════════════════

def create_condition_block(left="device1", op=">", right="10",
                           x=0, y=0, device_choices=None, op_choices=None) -> Block:
    
    w, h  = 300, 48
    block = Block(w, h, C_COND, "", "condition")
    block.setPos(x, y)

    pad = 4; sw = 80; ow = 48
    op_choices   = op_choices   or COMPARE_OPS
    dev_choices  = device_choices or []

    l = SubBlock(block, pad,            pad, sw, h-2*pad, C_DEVICE,   left,  True, dev_choices, "device")
    o = SubBlock(block, pad+sw+2,       pad, ow, h-2*pad, C_OPERATOR, op,    True, op_choices,  "opérateur")
    r = SubBlock(block, pad+sw+ow+4,    pad, sw, h-2*pad,
                 C_VALUE if right.replace(".","").replace("-","").isdigit() else C_DEVICE,
                 right, True, dev_choices, "valeur / device")
    block._sub_blocks = [l, o, r]
    block.add_port("left");  block.add_port("right")
    block.to_token = lambda: f"{l.text} {o.text} {r.text}"
    return block


def create_function_block(func="slope", device="device1", param="8",
                          x=0, y=0, device_choices=None) -> Block:
    
    w, h  = 300, 48
    block = Block(w, h, C_FUNC, "", "function")
    block.setPos(x, y)

    pad=4; fw=78; dw=80; pw=48
    fnames = list(PRIMITIVES.keys())
    devc   = device_choices or []

    f = SubBlock(block, pad,       pad, fw, h-2*pad, C_FUNC.lighter(130), func,   True, fnames, "fonction")
    d = SubBlock(block, pad+fw+2,  pad, dw, h-2*pad, C_DEVICE,            device, True, devc,   "device")
    p = SubBlock(block, pad+fw+dw+4, pad, pw, h-2*pad, C_VALUE,           param,  True, [],     "paramètre")
    block._sub_blocks = [f, d, p]
    block.add_port("left");  block.add_port("right")
    block.to_token = lambda: f"{f.text}({d.text}, {p.text})"
    return block


def create_logic_block(op="and", x=0, y=0) -> Block:
    w, h  = 80, 48
    block = Block(w, h, C_LOGIC, op.upper(), "logic")
    block.setPos(x, y)
    block.add_port("left", 0)
    block.add_port("left", 1)
    block.add_port("right")
    tok = "&" if op.lower() == "and" else "|"
    block.to_token = lambda: tok
    return block


def create_start_block(rule_name="nouvelle_regle", x=0, y=0) -> Block:
    """Crée un nœud de départ pour une règle"""
    w, h  = 160, 48
    block = Block(w, h, C_START, "", "start")
    block.setPos(x, y)

    pad = 4
    nw = w - 2*pad

    name_sub = SubBlock(block, pad, pad, nw, h-2*pad, C_START_LIGHT, rule_name, True, [], "nom_règle")
    block._sub_blocks = [name_sub]
    block.add_port("right")
    block.to_token = lambda: f"rule:{name_sub.text}"
    return block


def create_action_block(output="sortie1", value="on",
                        x=0, y=0, output_choices=None) -> Block:
    
    is_pwm = output.startswith("servo")
    color  = C_PWM if is_pwm else C_ACTION
    w, h   = 210, 48
    block  = Block(w, h, color, "", "action")
    block.setPos(x, y)

    pad=4; nw=90; vw=70
    out_c = output_choices or []
    val_c = (["0","45","90","135","180"] if is_pwm
             else [a for a, i in ACTIONS.items() if i["args"] == 1])

    n = SubBlock(block, pad,      pad, nw, h-2*pad, color.lighter(120), output, True, out_c, "sortie")
    v = SubBlock(block, pad+nw+2, pad, vw, h-2*pad, C_DEVICE,           value,  True, val_c, "action")
    block._sub_blocks = [n, v]
    block.add_port("left")
    block.to_token = lambda: (v.text if v.text in ("log","stream") else f"{v.text}({n.text})")
    return block


def create_log_block(x=0, y=0) -> Block:
    b = Block(80, 48, C_VALUE, "log", "log_action")
    b.setPos(x, y);  b.add_port("left")
    b.to_token = lambda: "log"
    return b


def create_stream_block(x=0, y=0) -> Block:
    b = Block(92, 48, C_PORT, "stream", "stream_action")
    b.setPos(x, y);  b.add_port("left")
    b.to_token = lambda: "stream"
    return b


# ════════════════════════════════════════════════════
#  GRAPH SCENE
# ════════════════════════════════════════════════════

class GraphScene(QGraphicsScene):
    wire_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setSceneRect(0, 0, 2400, 1600)
        self._dragging_wire: Wire | None = None
        self._source_port  : Port | None = None

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, C_BG)
        for grid, pen in [(GRID_SIZE, QPen(C_GRID, 0.5)),
                          (GRID_SIZE*5, QPen(C_GRID_BOLD, 0.8))]:
            x = int(rect.left())  - int(rect.left())  % grid
            y = int(rect.top())   - int(rect.top())   % grid
            painter.setPen(pen)
            while x < rect.right():
                painter.drawLine(x, int(rect.top()), x, int(rect.bottom()));  x += grid
            while y < rect.bottom():
                painter.drawLine(int(rect.left()), y, int(rect.right()), y);  y += grid

    def _view_transform(self) -> QTransform:
        return self.views()[0].transform() if self.views() else QTransform()

    def _item_at(self, pos):
        return self.itemAt(pos, self._view_transform())

    def mousePressEvent(self, event):
        item = self._item_at(event.scenePos())
        if isinstance(item, Port) and event.button() == Qt.LeftButton and item.side == "right":
            self._source_port   = item
            self._dragging_wire = Wire(item)
            self._dragging_wire.temp_end = event.scenePos()
            self._dragging_wire.update_path()
            self.addItem(self._dragging_wire)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging_wire:
            self._dragging_wire.temp_end = event.scenePos()
            self._dragging_wire.update_path()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging_wire:
            item = self._item_at(event.scenePos())
            ok   = (isinstance(item, Port)
                    and item.side == "left"
                    and item.parent_block is not self._source_port.parent_block
                    and not item.is_connected())
            if ok:
                self._dragging_wire.set_dest(item)
                self.wire_changed.emit()
            else:
                self._dragging_wire.remove()
            self._dragging_wire = None
            self._source_port   = None
            return
        super().mouseReleaseEvent(event)

    # ── Export texte ──────────────────────────────────

    def to_rule_text(self, rule_name: str = "regle") -> str:
        texts = self.to_rule_texts(rule_name)
        return "\n\n".join(texts) if texts else ""

    def to_rule_texts(self, base_name: str = "regle") -> list[str]:
        """Exporte toutes les règles définies par les nœuds Start"""
        blocks = [i for i in self.items() if isinstance(i, Block)]
        if not blocks:
            return []

        wires = [i for i in self.items() if isinstance(i, Wire) and i.dest]

        # Trouver tous les nœuds Start
        start_blocks = [b for b in blocks if b.block_type == "start"]
        if not start_blocks:
            # Mode compatibilité : une seule règle
            cond_blocks = [b for b in blocks if b.block_type not in {"action", "log_action", "stream_action"}]
            act_blocks = [b for b in blocks if b.block_type in {"action", "log_action", "stream_action"}]
            cond_str = self._linearize(cond_blocks)
            act_str = " & ".join(b.to_token() for b in act_blocks if b.to_token())
            if cond_str and act_str:
                return [f"{base_name}:\n{cond_str} => {act_str}"]
            return []

        # Pour chaque Start, trouver les blocs connectés
        rules = []
        for start in start_blocks:
            rule_name = start._sub_blocks[0].text if start._sub_blocks else f"regle_{len(rules)+1}"
            
            # Trouver tous les blocs connectés à ce Start (DFS)
            connected = set()
            stack = [start]
            while stack:
                current = stack.pop()
                if current in connected:
                    continue
                connected.add(current)
                for port in current._ports_right:
                    for wire in port.wires:
                        if wire.dest:
                            stack.append(wire.dest.parent_block)
            
            # Séparer conditions et actions
            cond_blocks = [b for b in connected if b != start and b.block_type not in {"action", "log_action", "stream_action"}]
            act_blocks = [b for b in connected if b != start and b.block_type in {"action", "log_action", "stream_action"}]
            
            cond_str = self._linearize(cond_blocks, connected)
            act_str = " & ".join(b.to_token() for b in act_blocks if b.to_token())
            
            if cond_str and act_str:
                rules.append(f"{rule_name}:\n{cond_str} => {act_str}")

        return rules

    def _linearize(self, blocks: list, component: set | None = None) -> str:
        if not blocks:
            return ""

        tokens, visited = [], set()
        component = set(component) if component is not None else None

        def visit(b):
            if b in visited:
                return
            visited.add(b)
            tok = b.to_token()
            if tok:
                tokens.append(tok)
            for p in b._ports_right:
                for w in p.wires:
                    if w.dest and (component is None or w.dest.parent_block in component):
                        visit(w.dest.parent_block)

        for block in blocks:
            visit(block)
        return " ".join(tokens)


# ════════════════════════════════════════════════════
#  GRAPH VIEW
# ════════════════════════════════════════════════════

class GraphView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pan = False; self._pan_start = QPointF()

    def wheelEvent(self, event):
        self.scale(1.15 if event.angleDelta().y() > 0 else 1/1.15, 
                   1.15 if event.angleDelta().y() > 0 else 1/1.15)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_R:
            self.resetTransform(); self.centerOn(400, 200)
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.scene().selectedItems():
                if isinstance(item, Block): item._delete()
                elif isinstance(item, Wire):  item.remove()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan = True; self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan:
            d = event.pos() - self._pan_start; self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y()); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan = False; self.setCursor(Qt.ArrowCursor); return
        super().mouseReleaseEvent(event)


# ════════════════════════════════════════════════════
#  TOOLBAR
# ════════════════════════════════════════════════════

class BlockToolbar(QFrame):
    block_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: white; border-bottom: 1px solid #E5E7EB; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        lbl = QLabel("Blocs :")
        lbl.setStyleSheet("font-weight:600; color:#374151; font-size:12px;")
        layout.addWidget(lbl)

        for label, block_type, color in [
            ("Start",     "start",     C_START),
            ("Condition", "condition", C_COND),
            ("Fonction",  "function",  C_FUNC),
            ("AND",       "and",       C_LOGIC),
            ("OR",        "or",        C_LOGIC),
            ("Action",    "action",    C_ACTION),
            ("Servo",     "servo",     C_PWM),
            ("Log",       "log",       C_VALUE),
            ("Stream",    "stream",    C_PORT),
        ]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background:{color.name()}; color:white; border:none;
                    border-radius:4px; padding:5px 12px; font-size:11px; font-weight:600; }}
                QPushButton:hover {{ background:{color.lighter(115).name()}; }}
            """)
            btn.clicked.connect(lambda _, t=block_type: self.block_requested.emit(t))
            layout.addWidget(btn)

        layout.addStretch()

        for label, sig, style in [
            ("📋  Exporter", "export",
             "background:#F0FDF4; border:1px solid #86EFAC; color:#166534;"),
            ("🗑  Effacer",  "clear",
             "background:white; border:1px solid #FECACA; color:#EF4444;"),
            ("⊙  Zoom [R]", "zoom_reset",
             "background:white; border:1px solid #D1D5DB; color:#374151;"),
        ]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ {style} border-radius:4px; padding:5px 12px;
                    font-size:11px; font-weight:500; }}
                QPushButton:hover {{ opacity:0.85; }}
            """)
            btn.clicked.connect(lambda _, s=sig: self.block_requested.emit(s))
            layout.addWidget(btn)


# ════════════════════════════════════════════════════
#  VISUAL RULE EDITOR
# ════════════════════════════════════════════════════

class VisualRuleEditor(QWidget):
    """
    Éditeur visuel de règles par blocs connectés.

    Usage :
        editor = VisualRuleEditor(appareil)
        layout.addWidget(editor)
    """

    rules_changed = pyqtSignal()

    def __init__(self, appareil=None, parent=None):
        super().__init__(parent)
        self.appareil     = appareil
        self._block_count = 0
        self._rule_name   = "regle_1"
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toolbar = BlockToolbar()
        self._toolbar.block_requested.connect(self._on_block_requested)
        layout.addWidget(self._toolbar)

        # Barre nom de règle + aide
        top = QFrame()
        top.setStyleSheet("QFrame { background:#F0F4FF; border-bottom:1px solid #DBEAFE; }")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 5, 12, 5)
        tl.setSpacing(10)
        tl.addWidget(QLabel("Nom :"))
        self._name_edit = QLineEdit(self._rule_name)
        self._name_edit.setFixedWidth(180)
        self._name_edit.setStyleSheet("""
            QLineEdit { border:1px solid #BFDBFE; border-radius:4px; padding:4px 8px;
                font-size:11px; font-weight:600; background:white; color:#1E3A5F; }
        """)
        self._name_edit.textChanged.connect(lambda t: setattr(self, "_rule_name", t))
        tl.addWidget(self._name_edit)
        tl.addStretch()
        help_lbl = QLabel(
            "💡  Tirer ● (droite) → ● (gauche)  ·  "
            "Double-clic sur sous-bloc = éditer  ·  "
            "Clic droit = supprimer  ·  Molette = zoom  ·  Milieu = pan  ·  Suppr = effacer"
        )
        help_lbl.setStyleSheet("color:#2563eb; font-size:10px;")
        tl.addWidget(help_lbl)
        layout.addWidget(top)

        self._scene = GraphScene()
        self._scene.wire_changed.connect(self._on_graph_changed)
        self._scene.changed.connect(self._on_graph_changed)
        self._view  = GraphView(self._scene)
        layout.addWidget(self._view, stretch=1)

        # Status bar
        sb = QFrame()
        sb.setFixedHeight(30)
        sb.setStyleSheet("QFrame { background:#F8FFF4; border-top:1px solid #BBF7D0; }")
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(12, 2, 12, 2)
        self._status_lbl = QLabel("Règle : (vide)")
        self._status_lbl.setStyleSheet("color:#166534; font-size:11px; font-family:monospace;")
        sl.addWidget(self._status_lbl)
        layout.addWidget(sb)

    # ── Handlers ──────────────────────────────────────

    def _on_block_requested(self, block_type: str):
        if block_type == "clear":
            self._scene.clear(); self._block_count = 0
            self._status_lbl.setText("Règle : (vide)"); return
        if block_type == "export":
            self._export(); return
        if block_type == "zoom_reset":
            self._view.resetTransform(); self._view.centerOn(400, 200); return

        center = self._view.mapToScene(self._view.viewport().rect().center())
        off    = self._block_count * 20
        x, y   = center.x() - 60 + off % 200, center.y() - 20 + (off // 200) * 60
        self._block_count += 1

        devs  = self._get_device_names()
        outs_d = self._get_output_names("digital")
        outs_p = self._get_output_names("pwm")

        block = {
            "start":     lambda: create_start_block(f"regle_{self._block_count}", x, y),
            "condition": lambda: create_condition_block(
                devs[0] if devs else "device1", ">", "10", x, y, devs),
            "function":  lambda: create_function_block(
                "slope", devs[0] if devs else "device1", "8", x, y, devs),
            "and":    lambda: create_logic_block("and", x, y),
            "or":     lambda: create_logic_block("or",  x, y),
            "action": lambda: create_action_block(
                outs_d[0] if outs_d else "sortie1", "on", x, y, outs_d),
            "servo":  lambda: create_action_block(
                outs_p[0] if outs_p else "servo5", "90", x, y, outs_p),
            "log":    lambda: create_log_block(x, y),
            "stream": lambda: create_stream_block(x, y),
        }.get(block_type)
        if block:
            self._scene.addItem(block())

    def _export(self):
        rules = self._scene.to_rule_texts("regle")
        if not rules:
            QMessageBox.warning(self, "Export", "Le graphe est vide ou incomplet.\n"
                                "(Il faut au moins une condition et une action connectées)")
            return
        text = "\n\n".join(rules)
        QMessageBox.information(self, f"Règles générées ({len(rules)})", f"<pre style='font-size:13px'>{text}</pre>")
        self.rules_changed.emit()

    def _on_graph_changed(self, *_):
        rules = self._scene.to_rule_texts("regle")
        if rules:
            if len(rules) == 1:
                short = rules[0].replace("\n", "  ")
                self._status_lbl.setText(f"→  {short[:110]}{'…' if len(short)>110 else ''}")
            else:
                self._status_lbl.setText(f"→  {len(rules)} règles définies")
        else:
            self._status_lbl.setText("Règle : (incomplète)")

    # ── Helpers appareil ─────────────────────────────

    def _get_device_names(self) -> list:
        if not self.appareil: return ["device1", "device2"]
        return [f"device{d['device'].uid}" for d in self.appareil.get_all_devices()]

    def _get_output_names(self, out_type=None) -> list:
        if not self.appareil:
            return ["sortie1"] if out_type != "pwm" else ["servo5"]
        return [("servo" if o.type == "pwm" else "sortie") + str(o.output_id)
                for o in self.appareil.get_active_outputs()
                if not out_type or o.type == out_type]

    def refresh_context(self):
        device_names = self._get_device_names()
        outputs = self._get_output_names()
        pwm_values = ["0", "45", "90", "135", "180"]
        action_values = [a for a, i in ACTIONS.items() if i["args"] == 1]

        for item in self._scene.items():
            if isinstance(item, Block):
                for sub in item._sub_blocks:
                    if sub.role in ("device", "valeur / device"):
                        sub.update_choices(device_names)
                    elif sub.role == "opérateur":
                        sub.update_choices(COMPARE_OPS)
                    elif sub.role == "fonction":
                        sub.update_choices(list(PRIMITIVES.keys()))
                    elif sub.role == "sortie":
                        sub.update_choices(outputs)
                    elif sub.role == "action":
                        output = item._sub_blocks[0].text if item._sub_blocks else ""
                        if output.startswith("servo"):
                            sub.update_choices(pwm_values)
                        else:
                            sub.update_choices(action_values)

    # ── Persistance ───────────────────────────────────

    def get_rule_text(self) -> str:
        return self._scene.to_rule_text(self._rule_name)

    def get_rules_texts(self) -> list[str]:
        return self._scene.to_rule_texts(self._rule_name)

    def save_to_appareil(self):
        if self.appareil:
            texts = self.get_rules_texts()
            self.appareil.rules = [
                {"rule_id": idx + 1, "enabled": True, "text": text}
                for idx, text in enumerate(texts)
            ]

    # ── Exemple initial ───────────────────────────────

    def _add_example(self):
        # Plus d'exemple initial - canvas vide au démarrage
        pass

        for item in [c1, and_b, c2, a1, a2]:
            self._scene.addItem(item)

        def wire(src, ss, dst, ds, di=0):
            sp = src.get_port(ss); dp = dst.get_port(ds, di)
            if sp and dp:
                w = Wire(sp, dp); self._scene.addItem(w)

        wire(c1, "right", and_b, "left", 0)
        wire(and_b, "right", c2, "left", 0)
        wire(c2, "right", a1, "left", 0)
        wire(c2, "right", a2, "left", 0)


# ════════════════════════════════════════════════════
#  TEST STANDALONE
# ════════════════════════════════════════════════════

if __name__ == "__main__":

    class _FakeDev:
        def __init__(self, u, m, q):
            self.uid=u; self.model=m; self.quantity=q; self.i2c_address=None
        def display_name(self): return f"{self.model} ({self.quantity})"

    class _FakeOut:
        def __init__(self, i, t, l):
            self.output_id=i; self.type=t; self.label=l; self.active=True

    class _FakeApp:
        rules = []
        def get_all_devices(self):
            return [{"device": _FakeDev(1,"LM75","temperature"), "slot":None},
                    {"device": _FakeDev(2,"BMP280","pressure"),  "slot":None},
                    {"device": _FakeDev(3,"DHT22","humidity"),   "slot":None}]
        def get_active_outputs(self):
            return [_FakeOut(1,"digital","Sortie 1"),
                    _FakeOut(3,"digital","Sortie 3"),
                    _FakeOut(5,"pwm","Servo 1")]

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ed = VisualRuleEditor(_FakeApp())
    ed.setWindowTitle("Éditeur visuel de règles")
    ed.setMinimumSize(980, 580)
    ed.show()
    sys.exit(app.exec_())
