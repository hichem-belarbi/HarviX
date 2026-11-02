import os
import json

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QMessageBox, QSplitter, QTabWidget, QFrame,
    QSizePolicy,QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

from models.appareil import Appareil
from rule_editor.rule_editor import RuleEditor
from rule_editor.visual_rule_editor import VisualRuleEditor
from rule_editor.chatbot import ChatbotDialog

from utils.styles import (
    STYLE_LEFT_PANEL, STYLE_HEADER, STYLE_BOTTOM_CONTROLS, STYLE_CONFIG_BAR,
    STYLE_RIGHT_FRAME, STYLE_BTN, STYLE_BTN_PRIMARY, STYLE_BTN_DANGER,  STYLE_BTN_AI, STYLE_BTN_TOGGLE_TO_AI, STYLE_BTN_TOGGLE_TO_MANUAL
    )

class LeftPanel(QFrame):
    def __init__(
        self,
        appareil: Appareil,
        open_chatbot_callback,
        config_mode_changed_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.appareil = appareil
        self._active_config = "manual"
        self._chatbot_dlg = None
        self._open_chatbot_callback = open_chatbot_callback
        self._config_mode_changed_callback = config_mode_changed_callback
        self.setObjectName("left_panel")
        self.setStyleSheet(STYLE_LEFT_PANEL)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(STYLE_HEADER)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel(" Configurateur ")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1F2937;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        h_layout.addWidget(self._summary_label)

        layout.addWidget(header)
        layout.addWidget(self.appareil, stretch=1)

        controls = QFrame()
        controls.setStyleSheet(STYLE_BOTTOM_CONTROLS)
        c_layout = QHBoxLayout(controls)
        c_layout.setContentsMargins(12, 8, 12, 8)
        c_layout.setSpacing(8)
        label = QLabel("Période :")
        label.setStyleSheet("border: none;")
        c_layout.addWidget(label)
        self.period_spin = QSpinBox()
        self.period_spin.setRange(10, 60_000)
        self.period_spin.setSuffix(" ms")
        self.period_spin.setValue(self.appareil.period_ms)
        
        self.period_spin.valueChanged.connect(
            lambda v: setattr(self.appareil, "period_ms", v)
        )
        c_layout.addWidget(self.period_spin)
        c_layout.addStretch()

        layout.addWidget(controls)

        self._toggle_btn = QPushButton()
        self._toggle_btn.clicked.connect(self._on_toggle_config)
        self._toggle_btn.setVisible(False)

        self._ai_button = QPushButton()
        self._ai_button.clicked.connect(self._open_chatbot_callback)
        self._ai_button.setVisible(False)

        self._active_config = "manual"
        self._config_badge = QLabel()
        self._config_badge.setVisible(False)

        self.refresh_summary()
        self.appareil.config_changed.connect(self.refresh_summary)

    def refresh_summary(self):
        devs = len(self.appareil.get_all_devices())
        outs = len(self.appareil.get_active_outputs())
        self._summary_label.setText(f"{devs} capteur(s) · {outs} sortie(s)")

    def _update_config_bar(self):
        chat_path = os.path.join(self.appareil.config_dir, "chat_current_config.json")
        has_ai = os.path.exists(chat_path)
        if self._active_config == "manual":
            self._config_badge.setText("Manuelle")
            self._config_badge.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #1D4ED8;"
            )
            self._toggle_btn.setText("Passer config IA")
            self._toggle_btn.setStyleSheet(STYLE_BTN_TOGGLE_TO_AI)
            self._toggle_btn.setEnabled(has_ai)
            self._toggle_btn.setToolTip(
                "" if has_ai else "Aucune config IA — utilisez l'assistant IA d'abord"
            )
        else:
            self._config_badge.setText("Config IA active")
            self._config_badge.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #7C3AED;"
            )
            self._toggle_btn.setText("Revenir config manuelle")
            self._toggle_btn.setStyleSheet(STYLE_BTN_TOGGLE_TO_MANUAL)
            self._toggle_btn.setEnabled(True)
            self._toggle_btn.setToolTip("")

    def _on_save(self):
        self.appareil.save()
        QMessageBox.information(self, "Succès", "Configuration enregistrée.")

    def _on_reload(self):
        reply = QMessageBox.question(
            self, "Recharger",
            "Recharger la dernière configuration sauvegardée ?\n"
            "Les modifications non enregistrées seront perdues.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            QMessageBox.information(
                self, "Info",
                "Redémarrez l'application pour recharger la configuration."
            )

    def _on_clear(self):
        reply = QMessageBox.warning(
            self, "Réinitialiser",
            "Effacer toute la configuration ?\n"
            "Tous les capteurs et sorties seront désassignés.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for sid in self.appareil.slot_order:
                self.appareil.slots[sid].clear()
                self.appareil._next_uid = 1
            for oid in self.appareil.output_order:
                self.appareil.outputs[oid].active = False
            self.appareil.log_enabled = False
            self.appareil.stream_enabled = False
            self.appareil._create_pins()
            self.appareil._do_layout()
            self.appareil.update()
            self.appareil.config_changed.emit()

    def _on_toggle_config(self):
        config_dir = self.appareil.config_dir
        if self._active_config == "manual":
            path = os.path.join(config_dir, "chat_current_config.json")
            if not os.path.exists(path):
                QMessageBox.warning(
                    self, "Config IA introuvable",
                    "Aucune configuration IA n'a encore été générée.\n"
                    "Utilisez l'assistant IA et cliquez sur Appliquer."
                )
                return
            self.appareil.load_from_file(path)
            self._active_config = "ai"
        else:
            path = os.path.join(config_dir, "current_config.json")
            self.appareil.load_from_file(path)
            self._active_config = "manual"
        self._update_config_bar()
        if self._config_mode_changed_callback is not None:
            self._config_mode_changed_callback(self._active_config)

    def open_chatbot_dialog(self):
        if self._chatbot_dlg is not None and self._chatbot_dlg.isVisible():
            self._chatbot_dlg.raise_()
            self._chatbot_dlg.activateWindow()
            return

        config_dir = self.appareil.config_dir

        def _load_json(name):
            try:
                with open(os.path.join(config_dir, name), encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

        device_names = {f"device{d['device'].uid}" for d in self.appareil.get_all_devices()}
        output_names = set()
        for oid in self.appareil.output_order:
            out = self.appareil.outputs[oid]
            name = f"sortie{out.output_id}" if out.type == "digital" else f"servo{out.output_id}"
            output_names.add(name)

        def _device_label(device):
            device_id = f"device{device.uid}"
            q_label = self.appareil.get_qty_label(device.quantity)
            unit = self.appareil.get_qty_unit(device.quantity)
            unit_str = f" {unit}" if unit else ""
            model_str = device.model.lower() if getattr(device, 'model', None) else ""
            return device_id, f"{q_label}{unit_str} [{device_id}:{model_str}]"

        labels = dict(_device_label(d['device']) for d in self.appareil.get_all_devices())

        self._chatbot_dlg = ChatbotDialog(
            parent=self,
            device_names=device_names,
            output_names=output_names,
            device_labels=labels,
            appareil_config=_load_json("appareil_config.json"),
            choices_config=_load_json("choices_config.json"),
            config_dir=config_dir,
        )
        self._chatbot_dlg.config_applied.connect(self._on_ai_config_applied)
        self._chatbot_dlg.show()

    def _on_ai_config_applied(self, path: str):
        self._update_config_bar()
        reply = QMessageBox.question(
            self, "Config IA prête",
            "La configuration générée par l'IA a été sauvegardée.\n\n"
            "Voulez-vous l'activer maintenant ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.appareil.load_from_file(path)
            self._active_config = "ai"
            self._update_config_bar()
            if self._config_mode_changed_callback is not None:
                self._config_mode_changed_callback(self._active_config)


class Configurator(QWidget):
    config_mode_changed = pyqtSignal(str)

    def __init__(self, appareil: Appareil, parent=None):
        super().__init__(parent)
        self.appareil = appareil

        self.rule_editor = RuleEditor(self.appareil)
        self.visual_rule_editor = VisualRuleEditor(self.appareil)
        self.left_panel = LeftPanel(
            self.appareil,
            open_chatbot_callback=self.open_chatbot_dialog,
            config_mode_changed_callback=self.config_mode_changed.emit,
            parent=self,
        )

        self._build()
        self.appareil.config_changed.connect(self._on_config_changed)
        self.rule_editor.rules_changed.connect(
            lambda: self._on_rules_changed(self.rule_editor)
        )
        self.visual_rule_editor.rules_changed.connect(
            lambda: self._on_rules_changed(self.visual_rule_editor)
        )
        QTimer.singleShot(200, lambda: self._on_rules_changed(self.rule_editor))

    def open_chatbot_dialog(self):
        self.left_panel.open_chatbot_dialog()

    def _build(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        v_splitter = QSplitter(Qt.Vertical)
        h_splitter = QSplitter(Qt.Horizontal)

        h_splitter.addWidget(self.left_panel)

        right_frame = QFrame()
        right_frame.setStyleSheet(STYLE_RIGHT_FRAME)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(False) 
        self.tabs.setStyleSheet("""
    QTabBar::tab {
        padding: 6px 16px;   
        min-width: 0px;       
        width: 100px;          
    }
""")
        self.tabs.addTab(self.rule_editor, "Editeur - Text")
        self.tabs.addTab(self.visual_rule_editor, "Éditeur - visuel")

        right_layout.addWidget(self.tabs)
        h_splitter.addWidget(right_frame)

        h_splitter.setStretchFactor(0, 35)
        h_splitter.setStretchFactor(1, 65)
        h_splitter.setSizes([420, 780])

        v_splitter.addWidget(h_splitter)
        root_layout.addWidget(v_splitter)

    def _on_config_changed(self):
        print("Configuration changed, reloading editors...")
        self.rule_editor.reload_rules()
        self.visual_rule_editor.refresh_context()
        self._on_rules_changed(None)
        print("Editors reloaded.")

    def _on_rules_changed(self, sender):
        if sender is not None:
            print("Rules changed in editor, saving to appareil...")
            sender.save_to_appareil()

    def save_config(self):
        self.left_panel._on_save()

    def reload_config(self):
        self.left_panel._on_reload()

    def clear_config(self):
        self.left_panel._on_clear()

    def toggle_config_mode(self):
        self.left_panel._on_toggle_config()

    def get_active_config_mode(self) -> str:
        return self.left_panel._active_config

    def has_ai_config(self) -> bool:
        chat_path = os.path.join(self.appareil.config_dir, "chat_current_config.json")
        return os.path.exists(chat_path)

    def export_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter la configuration", "", "Fichiers JSON (*.json)"
        )
        if path:
            try:
                self.appareil._save_to(path)
                QMessageBox.information(self, "Succès", f"Configuration exportée vers {path}")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Échec de l'exportation : {str(e)}")
    def import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer une configuration", "", "Fichiers JSON (*.json)"
        )
        if path:
            try:
                self.appareil.load_from_file(path)
                QMessageBox.information(self, "Succès", f"Configuration importée depuis {path}")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Échec de l'importation : {str(e)}")