"""
views/slot_dialog.py — Dialog de configuration d'un slot
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QPushButton, QLabel, QGroupBox, QMessageBox,
)
from views.palette import STYLE_DIALOG, STYLE_BTN_PRIMARY


class SlotDialog(QDialog):
    def __init__(self, appareil, slot, parent=None):
        super().__init__(parent)
        self.appareil = appareil
        self.slot     = slot
        self.setWindowTitle(f"{slot.label} — Configuration")
        self.setMinimumWidth(460)
        self.setStyleSheet(STYLE_DIALOG)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # En-tête
        header_text = f"{self.slot.label}  ·  {self.slot.bus_type}  ({self.slot.bus})"
        if self.slot.devices:
            devices_info = " • ".join([f"device{d.uid} {d.model}" for d in self.slot.devices])
            header_text += f"\n{devices_info}"
        header = QLabel(header_text)
        header.setStyleSheet(
            "font-size: 15px; font-weight: bold; padding: 10px;"
            "background-color: #F8F9FA; border-radius: 4px; color: #1F2937; line-height: 1.6;"
        )
        layout.addWidget(header)

        # Capteurs assignés
        if self.slot.devices:
            layout.addWidget(self._build_assigned_group())

        # Formulaire d'ajout
        if self.slot.can_add():
            layout.addWidget(self._build_add_group())
        else:
            lbl = QLabel(f"Slot plein ({self.slot.max_devices}/{self.slot.max_devices})")
            lbl.setStyleSheet("color: #9CA3AF; font-style: italic; padding: 4px;")
            layout.addWidget(lbl)

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _build_assigned_group(self) -> QGroupBox:
        group   = QGroupBox("Capteurs assignés")
        glayout = QVBoxLayout(group)
        for dev in list(self.slot.devices):
            row = QHBoxLayout()
            
            # Device ID and model
            device_label = QLabel(f"device{dev.uid}")
            device_label.setStyleSheet("color: #2563EB; font-weight: bold; font-size: 12px; min-width: 70px;")
            row.addWidget(device_label)
            
            model_label = QLabel(f"{dev.model}")
            model_label.setStyleSheet("color: #1F2937; font-weight: bold; font-size: 12px; min-width: 80px;")
            row.addWidget(model_label)
            
            # Quantity
            qty_label = QLabel(f"{self.appareil.get_qty_label(dev.quantity)}")
            qty_label.setStyleSheet("color: #6B7280; font-size: 11px;")
            row.addWidget(qty_label)
            
            # I2C address if applicable
            if dev.i2c_address:
                addr_label = QLabel(f"@ {dev.i2c_address}")
                addr_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
                row.addWidget(addr_label)
            
            row.addStretch()
            rm = QPushButton("Retirer")
            rm.setStyleSheet("color: #EF4444; font-size: 12px;")
            rm.setFixedWidth(70)
            rm.clicked.connect(lambda _, u=dev.uid: self._remove(u))
            row.addWidget(rm)
            glayout.addLayout(row)
        return group

    def _build_add_group(self) -> QGroupBox:
        group   = QGroupBox("Ajouter un capteur")
        glayout = QVBoxLayout(group)
        form    = QFormLayout()
        form.setSpacing(10)

        compatible = self.appareil.get_compatible_sensors(self.slot.slot_id)

        self.model_combo = QComboBox()
        for s in compatible:
            self.model_combo.addItem(s["model"], s["model"])
        form.addRow("Modèle :", self.model_combo)

        self.qty_combo = QComboBox()
        form.addRow("Grandeur :", self.qty_combo)

        self.addr_combo = QComboBox()
        if self.slot.bus_type == "I2C":
            form.addRow("Adresse I2C :", self.addr_combo)

        glayout.addLayout(form)

        add_btn = QPushButton("+ Ajouter")
        add_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        add_btn.clicked.connect(self._add)
        glayout.addWidget(add_btn)

        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self._on_model_changed()
        return group

    def _on_model_changed(self):
        model = self.model_combo.currentData()
        info  = self.appareil.sensor_lib.get(model, {})
        self.qty_combo.clear()
        for q in info.get("quantities", []):
            self.qty_combo.addItem(self.appareil.get_qty_label(q), q)
        if self.slot.bus_type == "I2C":
            self.addr_combo.clear()
            used = set(self.slot.used_addresses())
            for a in info.get("addresses", []):
                if a not in used:
                    self.addr_combo.addItem(a)

    def _add(self):
        model = self.model_combo.currentData()
        qty   = self.qty_combo.currentData()
        addr  = self.addr_combo.currentText() if self.slot.bus_type == "I2C" else None
        if not model or not qty:
            return
        if self.slot.bus_type == "I2C" and not addr:
            QMessageBox.warning(self, "Erreur", "Sélectionner une adresse I2C.")
            return
        uid = self.appareil.assign_sensor(self.slot.slot_id, model, qty, addr)
        if uid is not None:
            self._rebuild()
        else:
            QMessageBox.warning(self, "Erreur", "Impossible d'assigner ce capteur.")

    def _remove(self, uid: int):
        self.appareil.remove_device(uid)
        self._rebuild()

    def _rebuild(self):
        self.close()
        SlotDialog(self.appareil, self.slot, self.parent()).exec_()
