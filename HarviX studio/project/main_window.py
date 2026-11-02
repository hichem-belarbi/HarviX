import os

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QAction, QToolBar,
    QPushButton, QSizePolicy, QStatusBar, QStackedWidget, QMessageBox,
    QDialog, QGroupBox, QLabel, QListWidget, QListWidgetItem,
    QRadioButton, QButtonGroup, QFileDialog, QDialogButtonBox,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon

from models.appareil import Appareil
from configurator import Configurator
from serial_manager import SerialManager, ComPortDialog, ConfigSyncDialog
from visualizer import Visualizer

from utils.styles import (
    STYLE_MENU_BAR, STYLE_TOOLBAR, CONNECT_BTN_STYLE
) 


class VisualizerExportDialog(QDialog):
    def __init__(self, visualizer, parent=None):
        super().__init__(parent)
        self.visualizer = visualizer
        self.setWindowTitle("Exporter les graphiques")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        info = QLabel(
            "Sélectionnez les règles à exporter et le format de sortie."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.rule_list = QListWidget()
        self.rule_list.setSelectionMode(QListWidget.MultiSelection)
        for rule_id, rule_name in self.visualizer.get_rule_list():
            item = QListWidgetItem(rule_name)
            item.setData(Qt.UserRole, rule_id)
            item.setSelected(True)
            self.rule_list.addItem(item)
        layout.addWidget(self.rule_list)

        buttons = QHBoxLayout()
        select_all_btn = QPushButton("Tout sélectionner")
        select_all_btn.clicked.connect(self._select_all)
        buttons.addWidget(select_all_btn)
        clear_btn = QPushButton("Tout désélectionner")
        clear_btn.clicked.connect(self._clear_selection)
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        export_group = QGroupBox("Format d'export")
        export_layout = QVBoxLayout(export_group)
        self.radio_separate = QRadioButton("Exporter chaque règle dans un fichier PNG séparé")
        self.radio_combined = QRadioButton("Exporter plusieurs règles dans un seul PNG")
        self.radio_separate.setChecked(True)
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.radio_separate)
        self.button_group.addButton(self.radio_combined)
        export_layout.addWidget(self.radio_separate)
        export_layout.addWidget(self.radio_combined)
        layout.addWidget(export_group)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _select_all(self):
        for i in range(self.rule_list.count()):
            self.rule_list.item(i).setSelected(True)

    def _clear_selection(self):
        for i in range(self.rule_list.count()):
            self.rule_list.item(i).setSelected(False)

    def get_selected_rule_ids(self) -> list[int]:
        return [
            self.rule_list.item(i).data(Qt.UserRole)
            for i in range(self.rule_list.count())
            if self.rule_list.item(i).isSelected()
        ]

    def export_separate(self) -> bool:
        return self.radio_separate.isChecked()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HarviX studio")
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "logo.png")))
        self.setMinimumSize(1200, 700)

        config_dir = os.path.join(os.path.dirname(__file__), "config")
        self.appareil = Appareil(config_dir)
        self.serial_manager = SerialManager()

        self.configurator = Configurator(self.appareil)
        self.visualizer = Visualizer(self.appareil)
        self.serial_manager.raw_data_received.connect(self.visualizer.decoder.process_bytes)
        self._create_menu_bar()
        self._create_status_bar()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.main_stack = QStackedWidget()
        self.main_stack.setContentsMargins(0, 0, 0, 0)
        self.main_stack.addWidget(self.configurator)
        self.main_stack.addWidget(self.visualizer)
        root.addWidget(self.main_stack)

        self._create_toolbar()
        self._switch_mode("configurator")

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet(STYLE_MENU_BAR)

        # Charger les icônes
        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        icon_configurator = QIcon(os.path.join(icons_dir, "configurator.png"))
        icon_visualizer = QIcon(os.path.join(icons_dir, "visualizer.png"))

        file_menu = menu_bar.addMenu("Fichier")
        exit_action = QAction("Quitter", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        configurator_menu = file_menu.addMenu("Configuration")
        export_config_action = QAction("Exporter la configuration", self)
        export_config_action.triggered.connect(self.configurator.export_config)
        configurator_menu.addAction(export_config_action)
        
        import_config_action = QAction("Importer une configuration", self)
        import_config_action.triggered.connect(self.configurator.import_config)
        configurator_menu.addAction(import_config_action)

        visualizer_menu = file_menu.addMenu("Visualiseur")
        export_visualizer_menu_action = QAction("Exporter les graphiques", self)
        export_visualizer_menu_action.triggered.connect(self._export_visualizer)
        visualizer_menu.addAction(export_visualizer_menu_action)

        view_menu = menu_bar.addMenu("Affichage")
        self.action_configurator = QAction(icon_configurator, None, self, checkable=True)
        self.action_visualizer = QAction(icon_visualizer, None, self, checkable=True)
        self.action_configurator.triggered.connect(
            lambda: self._switch_mode("configurator")
        )
        self.action_visualizer.triggered.connect(
            lambda: self._switch_mode("visualizer")
        )
        view_menu.addAction(self.action_configurator)
        view_menu.addAction(self.action_visualizer)

        tools_menu = menu_bar.addMenu("Outils")
        assistant_action = QAction("Assistant IA", self)
        assistant_action.triggered.connect(self.configurator.open_chatbot_dialog)
        tools_menu.addAction(assistant_action)

    def _create_toolbar(self):
        toolbar = QToolBar("Navigation", self)
        toolbar.setOrientation(Qt.Horizontal)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setStyleSheet(STYLE_TOOLBAR)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)

        toolbar.addAction(self.action_configurator)
        toolbar.addAction(self.action_visualizer)
        toolbar.addSeparator()

        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        clear_icon = QIcon(os.path.join(icons_dir, "clear.png"))
        reload_icon = QIcon(os.path.join(icons_dir, "reload.png"))
        save_icon = QIcon(os.path.join(icons_dir, "save.png"))
        ai_icon = QIcon(os.path.join(icons_dir, "ai_assitent.png"))
        ai_config_icon = QIcon(os.path.join(icons_dir, "ai_config.png"))
        manual_icon = QIcon(os.path.join(icons_dir, "manual_config.png"))
        sync_icon = QIcon(os.path.join(icons_dir, "sync.png"))
        start_icon = QIcon(os.path.join(icons_dir, "start_acq.png"))
        stop_icon = QIcon(os.path.join(icons_dir, "stop_acq.png"))
        exporter_icon = QIcon(os.path.join(icons_dir, "export.png"))

        self.action_clear = QAction(clear_icon, "Réinitialiser", self)
        self.action_clear.triggered.connect(self._clear_config)
        toolbar.addAction(self.action_clear)

        self.action_reload = QAction(reload_icon, "Recharger", self)
        self.action_reload.triggered.connect(self._reload_config)
        toolbar.addAction(self.action_reload)

        self.action_save = QAction(save_icon, "Enregistrer", self)
        self.action_save.triggered.connect(self._save_config)
        toolbar.addAction(self.action_save)

        self.action_toggle_config = QAction(manual_icon, "Passer config IA", self)
        self.action_toggle_config.triggered.connect(self._toggle_config_mode)
        toolbar.addAction(self.action_toggle_config)

        self.action_open_ai = QAction(ai_icon, "Assistant IA", self)
        self.action_open_ai.triggered.connect(self.configurator.open_chatbot_dialog)
        toolbar.addAction(self.action_open_ai)

        self.action_export_visualizer = QAction(exporter_icon, "Exporter graphiques", self)
        self.action_export_visualizer.triggered.connect(self._export_visualizer)
        toolbar.addAction(self.action_export_visualizer)

        self.configurator_toolbar_actions = [
            self.action_clear,
            self.action_reload,
            self.action_save,
            self.action_toggle_config,
            self.action_open_ai,
        ]

        self.visualizer_toolbar_actions = [
            self.action_export_visualizer,
        ]

        self._manual_config_icon = manual_icon
        self._ai_config_icon = ai_config_icon

        toolbar.addSeparator()

        com_icon = QIcon(os.path.join(icons_dir, "com_port.png"))
        upload_icon = QIcon(os.path.join(icons_dir, "upload.png"))
        
        self.btn_connect_com = QPushButton("Connexion")
        self.btn_connect_com.setIcon(com_icon)
        self.btn_connect_com.setStyleSheet(CONNECT_BTN_STYLE)
        self.btn_connect_com.setToolTip("Gérer la connexion COM")
        self.btn_connect_com.clicked.connect(self._on_connect_com)
        toolbar.addWidget(self.btn_connect_com)

        self.btn_send_config = QPushButton()
        self.btn_send_config.setIcon(upload_icon)
        self.btn_send_config.setStyleSheet("QPushButton { background-color: transparent; border: none; margin-left: 8px;margin-right: 8px; }")
        self.btn_send_config.setToolTip("Envoyer la configuration")
        self.btn_send_config.clicked.connect(self._on_send_current_config)
        toolbar.addWidget(self.btn_send_config)
        
        toolbar.addSeparator()
        self.action_sync = QAction(sync_icon, "Synchroniser", self)
        self.action_sync.triggered.connect(self._send_sync_request)
        toolbar.addAction(self.action_sync)

        self.action_acq = QAction(start_icon, "Acquisition", self)
        self.action_acq.triggered.connect(self._toggle_acquisition)
        toolbar.addAction(self.action_acq)

        self._start_icon = start_icon
        self._stop_icon = stop_icon
        self._is_acquiring = False

        self.addToolBar(Qt.TopToolBarArea, toolbar)
        self.configurator.config_mode_changed.connect(self._on_config_mode_changed)
        self._update_connection_state()
        self._update_toolbar_actions()

    def _create_status_bar(self):
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage("Mode configurateur")

    def _on_connect_com(self):
        if self.serial_manager.is_connected:
            self.serial_manager.close()
            self._update_connection_state()
            QMessageBox.information(self, "Déconnecté", "Connexion COM fermée.")
            return

        dialog = ComPortDialog(self.serial_manager, self)
        if dialog.exec_() == dialog.Accepted:
            self._update_connection_state()

    def _send_sync_request(self):
        if not self._ensure_connected("synchroniser"):
            return
        actual_path = os.path.join(self.appareil.config_dir, "actual_config.json")
        ok, actual = self.serial_manager.sync_from_device(actual_path, timeout=5.0)
        if ok:
            QMessageBox.information(self, "Synchronisation", "État récupéré et sauvegardé.")
        else:
            QMessageBox.warning(self, "Synchronisation", "Impossible de récupérer l'état de la carte.")

    def _on_send_current_config(self):
        if not self._ensure_connected("envoyer la configuration"):
            return
        config_path = os.path.join(self.appareil.config_dir, "current_config.json")
        actual_path = os.path.join(self.appareil.config_dir, "actual_config.json")
        dialog = ConfigSyncDialog(self.serial_manager, config_path, actual_path, self)
        dialog.exec_()

    def _toggle_acquisition(self):
        if not self._ensure_connected("gérer l'acquisition"):
            return

        if self._is_acquiring:
            ok, cmd_id, _ = self.serial_manager.stop_acquisition()
            if ok:
                QMessageBox.information(self, "Acquisition", "Commande d'arrêt envoyée.")
                self._is_acquiring = False
                self.action_acq.setIcon(self._start_icon)
            else:
                QMessageBox.warning(self, "Acquisition", "Aucune réponse reçue du périphérique.")
        else:
            ok, cmd_id, _ = self.serial_manager.start_acquisition()
            if ok:
                QMessageBox.information(self, "Acquisition", "Commande de démarrage envoyée.")
                self._is_acquiring = True
                self.action_acq.setIcon(self._stop_icon)
            else:
                QMessageBox.warning(self, "Acquisition", "Aucune réponse reçue du périphérique.")

    def _clear_config(self):
        self.configurator.clear_config()

    def _reload_config(self):
        self.configurator.reload_config()

    def _save_config(self):
        self.configurator.save_config()

    def _toggle_config_mode(self):
        self.configurator.toggle_config_mode()

    def _update_toggle_config_action(self):
        active_mode = self.configurator.get_active_config_mode()
        if active_mode == "manual":
            self.action_toggle_config.setText("Passer config IA")
            self.action_toggle_config.setIcon(self._manual_config_icon)
            self.action_toggle_config.setToolTip(
                "Passer à la configuration IA"
            )
            self.action_toggle_config.setEnabled(self.configurator.has_ai_config())
        else:
            self.action_toggle_config.setText("Config manuelle")
            self.action_toggle_config.setIcon(self._ai_config_icon)
            self.action_toggle_config.setToolTip("Revenir à la configuration manuelle")
            self.action_toggle_config.setEnabled(True)

    def _update_toolbar_actions(self):
        if not hasattr(self, "main_stack"):
            return

        visible_config = self.main_stack.currentWidget() is self.configurator
        visible_visualizer = self.main_stack.currentWidget() is self.visualizer

        for action in self.configurator_toolbar_actions:
            action.setVisible(visible_config)
        for action in self.visualizer_toolbar_actions:
            action.setVisible(visible_visualizer)

        self._update_toggle_config_action()

    def _update_configurator_toolbar(self):
        self._update_toolbar_actions()

    def _on_config_mode_changed(self, mode: str):
        self._update_toggle_config_action()

    def _export_visualizer(self):
        rules = self.visualizer.get_rule_list()
        if not rules:
            QMessageBox.warning(self, "Export", "Aucune règle disponible à exporter.")
            return

        dialog = VisualizerExportDialog(self.visualizer, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        selected = dialog.get_selected_rule_ids()
        if not selected:
            selected = [rule_id for rule_id, _ in rules]

        try:
            if dialog.export_separate():
                target_dir = QFileDialog.getExistingDirectory(
                    self, "Choisir un dossier", os.path.expanduser("~")
                )
                if not target_dir:
                    return
                saved_paths = self.visualizer.export_graphs(
                    rule_ids=selected,
                    separate=True,
                    output_path=target_dir,
                )
            else:
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Enregistrer le PNG combiné",
                    os.path.join(os.path.expanduser("~"), "visualizer_export.png"),
                    "Image PNG (*.png)",
                )
                if not path:
                    return
                saved_paths = self.visualizer.export_graphs(
                    rule_ids=selected,
                    separate=False,
                    output_path=path,
                )

            if saved_paths:
                QMessageBox.information(
                    self,
                    "Export réussi",
                    "Export terminé :\n" + "\n".join(saved_paths)
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export échoué",
                f"Impossible d'exporter les graphiques : {exc}"
            )

    def _ensure_connected(self, action_name: str) -> bool:
        if not self.serial_manager.is_connected:
            QMessageBox.warning(
                self,
                "Connexion COM requise",
                f"Connectez d'abord un port COM pour {action_name}."
            )
            return False
        return True

    def _update_connection_state(self):
        connected = self.serial_manager.is_connected
        self.action_sync.setEnabled(connected)
        self.action_acq.setEnabled(connected)
        self.btn_send_config.setEnabled(connected)
        if not connected and self._is_acquiring:
            self._is_acquiring = False
            self.action_acq.setIcon(self._start_icon)

        self.btn_connect_com.setText(
            f"{self.serial_manager.port_name}" if connected else "Connexion"
        )
        status_text = (
            f"Connecté à {self.serial_manager.port_name}" if connected
            else "Connexion COM inactive"
        )
        self.statusBar().showMessage(status_text)

    def _switch_mode(self, mode: str):
        if mode == "visualizer":
            self.main_stack.setCurrentWidget(self.visualizer)
            self.action_visualizer.setChecked(True)
            self.action_configurator.setChecked(False)
            self.statusBar().showMessage("Mode visualisateur")
        else:
            self.main_stack.setCurrentWidget(self.configurator)
            self.action_configurator.setChecked(True)
            self.action_visualizer.setChecked(False)
            self.statusBar().showMessage("Mode configurateur")
        self._update_toolbar_actions()
