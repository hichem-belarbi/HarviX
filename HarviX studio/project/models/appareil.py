"""
models/appareil.py — Appareil : données + widget visuel autonome

Rendu style schéma électronique :
  • Bloc central = rectangle QFrame
  • Pins gauche  = QPushButton positionnés en absolu, débordant à gauche
  • Pins droite  = QPushButton positionnés en absolu, débordant à droite
  • Lignes de connexion dessinées via paintEvent

Usage :
    a = Appareil("config/")
    layout.addWidget(a)
    a.config_changed.connect(callback)
"""
from __future__ import annotations
import json
import os
from typing import Optional

from PyQt5.QtWidgets import QWidget, QPushButton, QSizePolicy, QToolTip
from PyQt5.QtCore    import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui     import QPainter, QPen, QColor, QFont, QBrush, QPixmap

from models.device import Device, Slot, Output


# ════════════════════════════════════════════════
#  PALETTE
# ════════════════════════════════════════════════

_C_BODY      = "grey"   # bloc central (bleu-gris foncé comme l'image)
_C_BODY_BDR  = "transparent"   # bord du bloc (invisible, on utilise une ligne dessinée à la place)
_C_BG        = "#F0F0F0"   # fond du widget

# Couleurs par bus (pin assigné)
_BUS_COLOR: dict[str, str] = {
    "SPI":     "#F5A623",   # orange-jaune (comme l'image)
    "ADC":     "#E67E22",   # orange
    "I2C":     "#27AE60",   # vert
    "Digital": "#2980B9",   # bleu
}
_PIN_EMPTY   = "#D0D0D0"   # gris clair
_PIN_EMPTY_T = "#888888"

# Outputs (rouge comme l'image)
_OUT_EMPTY   = "#817D7D"
_OUT_ACTIVE  = "#C0392B"

# LOG / STREAM
_FEAT_OFF    = "#817D7D"
_FEAT_ON     = "#E5A800"

# Dimensions
_PIN_W       = 70    # largeur pin gauche/droite
_PIN_H       = 28    # hauteur pin standard
_PIN_I2C_H   = 110   # hauteur pin I2C (multi-device)
_PIN_GAP     = 6     # espacement entre pins
_GROUP_GAP   = 14    # espacement entre groupes de bus
_BLOCK_X     = 120   # x du bloc central
_BLOCK_W     = 320   # largeur bloc
_MARGIN_TOP  = 10
_FEAT_W      = 90    # largeur boutons LOG/STREAM
_FEAT_H      = 40
_OUT_W       = 60    # largeur pins sortie
_OUT_H       = 28


def _pin_style(color: str, text_color: str = "#FFFFFF",
               font_size: int = 9, bold: bool = True) -> str:
    weight = "bold" if bold else "normal"
    return f"""
        QPushButton {{
            background-color: {color};
            border: none;
            border-radius: 0px;
            margin: 0px;
            min-height: 0px;
            color: {text_color};
            font-family: 'Segoe UI', sans-serif;
            font-size: {font_size}px;
            font-weight: {weight};
            text-align: center;
            padding: 2px 4px;
        }}
        QPushButton:hover {{
            background-color: {_darken(color)};
        }}
        QPushButton:pressed {{
            background-color: {_darken(color, 30)};
        }}
    """


def _darken(hex_color: str, amount: int = 20) -> str:
    c = QColor(hex_color)
    return QColor(
        max(0, c.red()   - amount),
        max(0, c.green() - amount),
        max(0, c.blue()  - amount),
    ).name()


# ════════════════════════════════════════════════
#  PIN BUTTON
# ════════════════════════════════════════════════

class PinButton(QPushButton):
    """QPushButton positionné en absolu, représentant un slot ou une sortie."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)


# ════════════════════════════════════════════════
#  APPAREIL WIDGET
# ════════════════════════════════════════════════

class Appareil(QWidget):
    """
    Composant autonome (données + rendu pin-style).
    Posable dans n'importe quel layout ou canvas.
    """

    config_changed = pyqtSignal()

    def __init__(self, config_dir: str = "config/", parent=None):
        super().__init__(parent)
        self.config_dir = config_dir
        self._next_uid  = 1

        # ── Chargement des données ────────────────
        board   = self._load("appareil_config.json")
        choices = self._load("choices_config.json")
        current = self._load("current_config.json")

        self.choices    = choices
        self.board_name = board.get("board_name", "Appareil")

        self.slots:      dict[int, Slot]   = {}
        self.slot_order: list[int]         = []
        for s in board["slots"]:
            slot = Slot(s["id"], s["type"], s["bus"],
                        s["label"], s.get("max_devices", 1))
            self.slots[slot.slot_id] = slot
            self.slot_order.append(slot.slot_id)

        self.outputs:      dict[int, Output] = {}
        self.output_order: list[int]         = []
        for o in board["outputs"]:
            out = Output(o["id"], o["type"], o["label"])
            self.outputs[out.output_id] = out
            self.output_order.append(out.output_id)

        self.sensor_lib: dict[str, dict] = {
            s["model"]: s for s in choices["sensors"]
        }

        self.log_enabled    = current.get("log_enabled",    False)
        self.stream_enabled = current.get("stream_enabled", False)
        self.period_ms      = current.get("period_ms",      1000)
        self.rules          = current.get("rules",          [])

        for a in current.get("assignments", []):
            slot = self.slots.get(a["slot_id"])
            if not slot:
                continue
            for dd in a.get("devices", []):
                dev = Device.from_dict(dd)
                slot.add_device(dev)
                if dev.uid >= self._next_uid:
                    self._next_uid = dev.uid + 1

        for oid in current.get("outputs_active", []):
            if oid in self.outputs:
                self.outputs[oid].active = True

        # ── State pour le layout ─────────────────
        self._slot_pins:   dict[int, PinButton] = {}   # slot_id → button
        self._out_pins:    dict[int, PinButton] = {}   # output_id → button
        self._log_btn:     PinButton | None = None
        self._stream_btn:  PinButton | None = None

        # Géométries calculées (remplies par _layout)
        self._block_rect   = QRect()
        self._slot_mid_y:  dict[int, int] = {}   # slot_id → y centre du pin
        self._out_mid_y:   dict[int, int] = {}   # output_id → y centre du pin
        self._log_mid_y    = 0
        self._stream_mid_y = 0

        self.setMinimumSize(520, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"background-color: {_C_BG};")

        self._create_pins()

    # ════════════════════════════════════════════
    #  Création initiale des boutons
    # ════════════════════════════════════════════

    def _create_pins(self):
        """Crée tous les QPushButton (sans les positionner encore)."""

        # Slots (pins gauche)
        for sid in self.slot_order:
            slot = self.slots[sid]
            btn  = PinButton(self)
            btn.clicked.connect(lambda _, s=slot: self._on_slot_clicked(s))
            self._slot_pins[sid] = btn
            self._refresh_slot_pin(slot)

        # Outputs (pins droite)
        for oid in self.output_order:
            out = self.outputs[oid]
            btn = PinButton(self)
            btn.clicked.connect(lambda _, o=out: self._on_output_clicked(o))
            self._out_pins[oid] = btn
            self._refresh_out_pin(out)

        # LOG
        self._log_btn = PinButton(self)
        self._log_btn.clicked.connect(self._on_log_clicked)
        self._refresh_log_btn()

        # STREAM
        self._stream_btn = PinButton(self)
        self._stream_btn.clicked.connect(self._on_stream_clicked)
        self._refresh_stream_btn()

    # ════════════════════════════════════════════
    #  Refresh d'un pin
    # ════════════════════════════════════════════

    def _refresh_slot_pin(self, slot: Slot):
        btn = self._slot_pins[slot.slot_id]
        if slot.is_empty():
            btn.setText(slot.label)
            btn.setStyleSheet(_pin_style(_PIN_EMPTY, _PIN_EMPTY_T, bold=False))
            btn.setToolTip(f"{slot.label}  [{slot.bus_type} · {slot.bus}]\nCliquer pour assigner")
        else:
            color = _BUS_COLOR.get(slot.bus_type, "#555")
            if slot.bus_type == "I2C":
                lines = [f"device{d.uid} {d.model}" for d in slot.devices]
                lines.append(f"({len(slot.devices)}/{slot.max_devices})")
                btn.setText("\n".join(lines))
            else:
                dev = slot.devices[0]
                btn.setText(f"device{dev.uid}\n{dev.model}")
            btn.setStyleSheet(_pin_style(color, font_size=8 if slot.bus_type == "I2C" else 9))
            
            # Build detailed tooltip with all device information
            tooltip_lines = [f"{slot.label}  [{slot.bus_type}]"]
            for d in slot.devices:
                device_line = f"  • device{d.uid} ({d.model})"
                details = [f"    Quantité: {d.quantity}"]
                if d.i2c_address:
                    details.append(f"    Adresse I2C: {d.i2c_address}")
                if d.params:
                    details.append(f"    Params: {d.params}")
                tooltip_lines.append(device_line)
                tooltip_lines.extend(details)
            btn.setToolTip("\n".join(tooltip_lines))

    def _refresh_out_pin(self, out: Output):
        btn = self._out_pins[out.output_id]
        if out.active:
            btn.setText(f"{out.label}\nON")
            btn.setStyleSheet(_pin_style(_OUT_ACTIVE))
        else:
            btn.setText(f"{out.label}\nOFF")
            btn.setStyleSheet(_pin_style(_OUT_EMPTY))
        btn.setToolTip(f"{out.label} ({out.type})\nCliquer pour basculer")

    def _refresh_log_btn(self):
        if self.log_enabled:
            self._log_btn.setText("LOG\nON")
            self._log_btn.setStyleSheet(_pin_style(_FEAT_ON, "#1F2937"))
        else:
            self._log_btn.setText("LOG\nOFF")
            self._log_btn.setStyleSheet(_pin_style(_FEAT_OFF, "#1F2937"))

    def _refresh_stream_btn(self):
        if self.stream_enabled:
            self._stream_btn.setText("STREAM\nON")
            self._stream_btn.setStyleSheet(_pin_style(_FEAT_ON, "#1F2937"))
        else:
            self._stream_btn.setText("STREAM\nOFF")
            self._stream_btn.setStyleSheet(_pin_style(_FEAT_OFF, "#1F2937"))

    # ════════════════════════════════════════════
    #  Layout (positionnement absolu)
    # ════════════════════════════════════════════

    def _do_layout(self):
        """
        Calcule et applique les positions de tous les boutons.
        Appelé dans resizeEvent et après chaque changement de config.
        """
        w = self.width()
        h = self.height()

        # ── Hauteur totale des pins gauche ────────
        bus_order = ["SPI", "ADC", "I2C", "Digital"]
        total_h = _MARGIN_TOP
        bus_slots: dict[str, list[Slot]] = {}
        for bus in bus_order:
            slots = self.get_slots_by_type(bus)
            if not slots:
                continue
            bus_slots[bus] = slots
            for slot in slots:
                total_h += self._pin_height(slot) + _PIN_GAP
            total_h += _GROUP_GAP

        # ── Bloc central ─────────────────────────
        block_h = max(total_h + _MARGIN_TOP, h - 40)
        block_y = (h - block_h) // 2
        self._block_rect = QRect(_BLOCK_X, block_y, _BLOCK_W, block_h)

        # ── Placement pins gauche ─────────────────
        y = block_y + _MARGIN_TOP
        for bus in bus_order:
            slots = bus_slots.get(bus)
            if not slots:
                continue
            for slot in slots:
                ph = self._pin_height(slot)
                btn = self._slot_pins[slot.slot_id]
                # Pin déborde à gauche du bloc
                btn.setGeometry(_BLOCK_X - _PIN_W, y, _PIN_W, ph)
                btn.show()
                self._slot_mid_y[slot.slot_id] = y + ph // 2
                y += ph + _PIN_GAP
            y += _GROUP_GAP

        # ── Placement pins droite (outputs) ───────
        right_x   = _BLOCK_X + _BLOCK_W   # bord droit du bloc
        out_total = len(self.output_order) * (_OUT_H + _PIN_GAP)
        y_out     = block_y + block_h - out_total - _MARGIN_TOP

        for oid in self.output_order:
            out = self.outputs[oid]
            btn = self._out_pins[oid]
            btn.setGeometry(right_x, y_out, _OUT_W, _OUT_H)
            btn.show()
            self._out_mid_y[oid] = y_out + _OUT_H // 2
            y_out += _OUT_H + _PIN_GAP

        # ── LOG / STREAM (droite, haut) ───────────
        feat_x = right_x + _OUT_W + 30
        feat_y = block_y + _MARGIN_TOP

        self._log_btn.setGeometry(feat_x, feat_y, _FEAT_W, _FEAT_H)
        self._log_btn.show()
        self._log_mid_y = feat_y + _FEAT_H // 2

        feat_y2 = feat_y + _FEAT_H + 20
        self._stream_btn.setGeometry(feat_x, feat_y2, _FEAT_W, _FEAT_H)
        self._stream_btn.show()
        self._stream_mid_y = feat_y2 + _FEAT_H // 2

    @staticmethod
    def _pin_height(slot: Slot) -> int:
        return _PIN_I2C_H if slot.bus_type == "I2C" else _PIN_H

    # ════════════════════════════════════════════
    #  Paint — bloc + lignes de connexion
    # ════════════════════════════════════════════

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        br = self._block_rect
        if br.isNull():
            return

        # ── Bloc central (image body.png) ────────
        icons_dir = os.path.join(os.path.dirname(__file__), "..", "icons")
        body_image = QPixmap(os.path.join(icons_dir, "body.png"))
        if not body_image.isNull():
            # Scaler l'image à la taille du rectangle
            scaled_image = body_image.scaled(br.width(), br.height(),Qt.KeepAspectRatioByExpanding, 
                                             Qt.SmoothTransformation)
            p.drawPixmap(br.topLeft(), scaled_image)
        else:
            # Fallback : rectangle gris si l'image ne charge pas
            p.setPen(QPen(QColor(_C_BODY_BDR), 2))
            p.setBrush(QBrush(QColor(_C_BODY)))
            p.drawRect(br)

        # ── Lignes : slots → bloc ─────────────────
        for sid, my in self._slot_mid_y.items():
            slot = self.slots[sid]
            color = QColor(_BUS_COLOR.get(slot.bus_type, "#999"))
            p.setPen(QPen(color, 1.5))
            # ligne du bord droit du pin jusqu'au bord gauche du bloc
            p.drawLine(br.left(), my, br.left(), my)   # point de contact
            p.drawLine(_BLOCK_X - _PIN_W - 0, my, br.left(), my)

        # ── Lignes : bloc → outputs ───────────────
        right_x = br.right()
        p.setPen(QPen(QColor(_OUT_EMPTY), 1.5))
        for oid, my in self._out_mid_y.items():
            p.drawLine(right_x, my, right_x + _OUT_W, my)

        # ── Lignes : bloc → LOG / STREAM ─────────
        feat_x_start = right_x
        feat_x_end   = right_x + _OUT_W + 30

        p.setPen(QPen(QColor(_FEAT_OFF), 1.5, Qt.DashLine))
        p.drawLine(feat_x_start, self._log_mid_y,    feat_x_end, self._log_mid_y)
        p.drawLine(feat_x_start, self._stream_mid_y, feat_x_end, self._stream_mid_y)

        # ── Séparateurs de groupes (gauche du bloc) ──
        p.setPen(QPen(QColor("#AAAAAA"), 1, Qt.DotLine))
        bus_order = ["SPI", "ADC", "I2C", "Digital"]
        prev_bus  = None
        for sid in self.slot_order:
            slot = self.slots[sid]
            if prev_bus and slot.bus_type != prev_bus:
                my = self._slot_mid_y.get(sid, 0)
                sep_y = my - self._pin_height(slot) // 2 - _GROUP_GAP // 2
                p.drawLine(0, sep_y, br.left(), sep_y)
            prev_bus = slot.bus_type

        p.end()

    # ════════════════════════════════════════════
    #  Events Qt
    # ════════════════════════════════════════════

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._do_layout()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._do_layout()

    # ════════════════════════════════════════════
    #  Interactions
    # ════════════════════════════════════════════

    def _on_slot_clicked(self, slot: Slot):
        from views.slot_dialog import SlotDialog
        dlg = SlotDialog(self, slot, self)
        dlg.exec_()
        self._refresh_slot_pin(slot)
        self._do_layout()
        self.update()
        self.config_changed.emit()

    def _on_output_clicked(self, out: Output):
        out.toggle()
        self._refresh_out_pin(out)
        self.config_changed.emit()

    def _on_log_clicked(self):
        self.log_enabled = not self.log_enabled
        self._refresh_log_btn()
        self.config_changed.emit()

    def _on_stream_clicked(self):
        self.stream_enabled = not self.stream_enabled
        self._refresh_stream_btn()
        self.config_changed.emit()

    # ════════════════════════════════════════════
    #  API données
    # ════════════════════════════════════════════

    def _load(self, name: str) -> dict:
        with open(os.path.join(self.config_dir, name), "r", encoding="utf-8") as f:
            return json.load(f)

    def get_compatible_sensors(self, slot_id: int) -> list[dict]:
        slot = self.slots.get(slot_id)
        if not slot:
            return []
        return [s for s in self.choices["sensors"]
                if slot.bus_type in s["bus_compatible"]]

    def assign_sensor(self, slot_id: int, model: str, quantity: str,
                      i2c_address: Optional[str] = None) -> Optional[int]:
        slot = self.slots.get(slot_id)
        if not slot or not slot.can_add():
            return None
        info = self.sensor_lib.get(model)
        if not info or slot.bus_type not in info["bus_compatible"]:
            return None
        if quantity not in info["quantities"]:
            return None
        uid = self._next_uid
        self._next_uid += 1
        dev = Device(uid, model, quantity, i2c_address)
        return uid if slot.add_device(dev) else None

    def remove_device(self, uid: int) -> bool:
        for slot in self.slots.values():
            if slot.remove_device(uid):
                self._next_uid -=1
                return True
                
        return False

    def get_all_devices(self) -> list[dict]:
        result = []
        for sid in self.slot_order:
            slot = self.slots[sid]
            for dev in slot.devices:
                result.append({"slot": slot, "device": dev})
        return result

    def get_slots_by_type(self, bus_type: str) -> list[Slot]:
        return [self.slots[sid] for sid in self.slot_order
                if self.slots[sid].bus_type == bus_type]

    def get_active_outputs(self) -> list[Output]:
        return [self.outputs[oid] for oid in self.output_order
                if self.outputs[oid].active]

    def toggle_output(self, oid: int):
        if oid in self.outputs:
            self.outputs[oid].toggle()
            self._refresh_out_pin(self.outputs[oid])

    def get_qty_label(self, qty: str) -> str:
        return self.choices.get("quantities", {}).get(qty, {}).get("label", qty)

    def get_qty_unit(self, qty: str) -> str:
        return self.choices.get("quantities", {}).get(qty, {}).get("unit", "")

    def save(self):
        self._save_to(os.path.join(self.config_dir, "current_config.json"))

    def save_chat(self):
        self._save_to(os.path.join(self.config_dir, "chat_current_config.json"))

    def _save_to(self, path: str):
        assignments = []
        for sid in self.slot_order:
            slot = self.slots[sid]
            if slot.devices:
                assignments.append({
                    "slot_id": slot.slot_id,
                    "type":    slot.bus_type,
                    "devices": [d.to_dict() for d in slot.devices],
                })
        config = {
            "assignments":    assignments,
            "outputs_active": [oid for oid in self.output_order
                               if self.outputs[oid].active],
            "rules":          self.rules,
            "period_ms":      self.period_ms,
            "stream_enabled": self.stream_enabled,
            "log_enabled":    self.log_enabled,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def load_from_file(self, path: str):
        """Charge une config depuis un fichier JSON et rafraîchit le widget."""
        with open(path, "r", encoding="utf-8") as f:
            current = json.load(f)

        # Vider tous les slots et outputs
        for slot in self.slots.values():
            slot.clear()
        for out in self.outputs.values():
            out.active = False

        self._next_uid      = 1
        self.log_enabled    = current.get("log_enabled",    False)
        self.stream_enabled = current.get("stream_enabled", False)
        self.period_ms      = current.get("period_ms",      1000)
        self.rules          = current.get("rules",          [])

        for a in current.get("assignments", []):
            slot = self.slots.get(a["slot_id"])
            if not slot:
                continue
            for dd in a.get("devices", []):
                dev = Device.from_dict(dd)
                slot.add_device(dev)
                if dev.uid >= self._next_uid:
                    self._next_uid = dev.uid + 1

        for oid in current.get("outputs_active", []):
            if oid in self.outputs:
                self.outputs[oid].active = True

        # Rafraîchir tous les pins
        for sid in self.slot_order:
            self._refresh_slot_pin(self.slots[sid])
        for oid in self.output_order:
            self._refresh_out_pin(self.outputs[oid])
        self._refresh_log_btn()
        self._refresh_stream_btn()
        self._do_layout()
        self.update()
        self.config_changed.emit()

    def summary(self) -> str:
        return (f"{self.board_name} | {len(self.get_all_devices())} capteur(s) | "
                f"{len(self.get_active_outputs())} sortie(s) | {self.period_ms} ms")