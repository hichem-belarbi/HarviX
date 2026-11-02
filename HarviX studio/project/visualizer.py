import sys
import os
import json
import struct
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QGridLayout, QScrollArea, QFrame, QSizePolicy
)

from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QSize, QTimer

# Intégration Matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Constantes du protocole (alignées sur uart_tx_task.c et serial_manager.py)
FRAME_STX = 0xAA
FRAME_ETX = 0x55
CMD_LIVE_DATA = 0x33 # Commande pour les trames de données temps réel (TX_LIVE_DATA)

class UARTFrameDecoder(QObject):
    """
    Décodeur qui reçoit les octets bruts lus par le SerialManager,
    extrait les trames TX_LIVE_DATA et émet un signal exploitable.
    """
    # Signal émis : (rule_id, timestamp_ms, { 'device_name': valeur, ... })
    live_data_received = pyqtSignal(int, int, dict)

    def __init__(self):
        super().__init__()
        self.buffer = bytearray()

    def process_bytes(self, raw_bytes):
        """ Encaisser les octets arrivant de la liaison série """
        print("\n--------\n debut d'un process \n")
        self.buffer.extend(raw_bytes)
        print(f"[UARTFrameDecoder] Buffer actuel: {self.buffer.hex()} (len={len(self.buffer)})")
        while len(self.buffer) >= 5:  # Taille minimale d'une trame valide
            # Chercher le début de trame
            if self.buffer[0] != FRAME_STX:
                self.buffer.pop(0)
                print("[UARTFrameDecoder] STX non trouvé, octet supprimé. Nouveau buffer:", self.buffer.hex())
                continue
            
            cmd = self.buffer[1]
            length = self.buffer[2]
            print(f"[UARTFrameDecoder] STX trouvé. CMD={cmd}, LEN={length}")
            # Vérifier si la trame entière est arrivée (STX + CMD + LEN + PAYLOAD + ETX)
            total_frame_len = 3 + length + 1
            if len(self.buffer) < total_frame_len:
                print("[UARTFrameDecoder] Trame incomplète, en attente de plus d'octets...")
                break # En attente du reste des octets
                
            # Vérifier l'ETX
            if self.buffer[total_frame_len - 1] != FRAME_ETX:
                # Mauvaise trame, on supprime le STX corrompu et on cherche le suivant
                print("[UARTFrameDecoder] ETX non trouvé à la position attendue, trame corrompue. Octet supprimé.")
                self.buffer.pop(0)
                continue
            print("[UARTFrameDecoder] Trame complète reçue, ETX vérifié.")
            # Extraction du Payload
            payload = self.buffer[3 : 3 + length]
            
            # Traitement si c'est de la donnée temps réel (TX_LIVE_DATA)
            if cmd == CMD_LIVE_DATA:
                print(f"[UARTFrameDecoder] Trame TX_LIVE_DATA reçue avec payload: {payload.hex()}")
                self._decode_live_data(payload)
                
            # Supprimer la trame traitée du buffer
            del self.buffer[:total_frame_len]
        print("\n--------\n fin d'un process \n")

    def _decode_live_data(self, payload):
            """
            Décodeur officiel basé sur la sérialisation manuelle du STM32.
            En-tête = 6 octets. Chaque canal = 7 octets (uid, quantity, value, status).
            """
            if len(payload) < 6:
                return
                
            # 1. Extraction de l'en-tête (6 octets)
            rule_id = payload[0]
            ts_ms = struct.unpack('<I', payload[1:5])[0]
            num_channels = payload[5]
            
            data_dict = {}
            
            # 2. Le tableau de canaux commence à l'index 6
            start_index = 6 
            
            for i in range(num_channels):
                # Chaque bloc de canal fait strictement 7 octets dans le buf sérialisé
                offset = start_index + (i * 7)
                
                # Définition des index à l'intérieur du bloc de 7 octets
                uid_index = offset + 0
                quantity_index = offset + 1
                float_start = offset + 2
                float_end = float_start + 4
                status_index = offset + 6
                
                # Sécurité anti-débordement de trame
                if status_index < len(payload):
                    uid = payload[uid_index]
                    quantity = payload[quantity_index]
                    val_bytes = payload[float_start:float_end]
                    status = payload[status_index]
                    
                    try:
                        # Décodage du float Little-Endian
                        val = struct.unpack('<f', val_bytes)[0]
                        
                        # Stockage au format requis par ton IHM (clé "value" indispensable)
                        data_dict[f"device{uid}"] = {
                            "value": val,
                            "status": status,
                            "quantity": quantity  # Optionnel : conservé au cas où
                        }
                    except struct.error:
                        print(f"[Decoder] Erreur unpack float pour le canal {i}")
                        continue
                else:
                    print(f"[Decoder] Trame coupée avant la fin du canal {i}")
                    break
                    
            if data_dict:
                # Soumission des données à l'interface graphique
                print(f"[UARTFrameDecoder] Décodage réussi - Règle {rule_id} ({ts_ms} ms): {data_dict}")
                self.live_data_received.emit(rule_id, ts_ms, data_dict)

class PlotWindow(QWidget):
    """ Fenêtre séparée pour un graphique détaché """
    def __init__(self, plot_card, parent=None):
        super().__init__(parent, Qt.Window)
        self.plot_card = plot_card
        self.setWindowTitle(f"Graphique Détaché - Règle : {self.plot_card.rule_name}")
        self.resize(600, 400)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.addWidget(self.plot_card.container)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

    def closeEvent(self, event):
        self.plot_card.dock_back()
        event.accept()



class RulePlotCard(QFrame):
    """ Carte graphique associée à une Règle spécifique """
    def __init__(self, rule_id, rule_name, rule_text, quantities, on_dock_callback, legend_items=None, parent=None):
        super().__init__(parent)
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.rule_text = rule_text
        self.quantities = quantities  # Liste des devices suivis, ex: ['device1']
        self.on_dock_callback = on_dock_callback
        self.legend_items = legend_items or []  # list of (label, model, color)

        self.is_floating = False
        self.window_container = None

        # Historiques des données
        self.data_history = {q: [] for q in self.quantities}
        self.time_history = []

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("RulePlotCard { background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(6, 6, 6, 6)

        # --- Barre supérieure ---
        self.top_bar = QHBoxLayout()
        title_lbl = QLabel(f"  <b>{self.rule_name}</b> ")
        title_lbl.setWordWrap(True)

        tooltip_text = f"{self.rule_text}\n\nGrandeurs suivies: {', '.join(self.quantities)}"
        info_icon = QLabel("")
        info_icon.setPixmap(QPixmap("project/icons/info.png").scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        info_icon.setToolTip(tooltip_text)
        self.top_bar.addWidget(title_lbl)
        self.top_bar.addWidget(info_icon)

        # --- Legend (color key) ---
        # Expect legend_items entries as (label, model, color, device, unit)
        display_map = {}
        if self.legend_items:
            legend_container = QWidget()
            legend_layout = QHBoxLayout(legend_container)
            legend_layout.setContentsMargins(6, 0, 6, 0)
            legend_layout.setSpacing(8)
            for q_label, model, color, device, unit in self.legend_items:
                sw = QLabel()
                sw.setFixedSize(12, 12)
                sw.setStyleSheet(f"background-color: {color}; border-radius: 2px; border: 1px solid #ddd;")
                # Format: temperature °C [device1:ntc]
                model_str = model.lower() if model else ""
                unit_str = f" {unit}" if unit else ""
                txt = QLabel(f"{q_label}{unit_str} [{device}:{model_str}]")
                txt.setStyleSheet("font-size: 11px; color: #374151;")
                legend_layout.addWidget(sw)
                legend_layout.addWidget(txt)
                # store display mapping for combo
                display_map[device] = f"{q_label}{unit_str} [{device}:{model_str}]"
            self.top_bar.addWidget(legend_container, stretch=1)
        else:
            self.top_bar.addStretch()

        self.top_bar.addWidget(QLabel("X :"))
        self.combo_x = QComboBox()
        self.combo_x.addItem("Temps (ms)", "time")
        for q in self.quantities:
            display = display_map.get(q, q)
            self.combo_x.addItem(display, q)
        self.combo_x.currentIndexChanged.connect(self._on_combo_changed)
        self.top_bar.addWidget(self.combo_x)

        icons_dir = os.path.join(os.path.dirname(__file__), "icons")    
        self.detach_icon = QIcon(os.path.join(icons_dir, "visualizer_detach.png"))
        self.reattach_icon = QIcon(os.path.join(icons_dir, "visualizer_reattach.png"))
        
        self.btn_pop = QPushButton(self.detach_icon,"")
        self.btn_pop.setStyleSheet("QPushButton { background-color: transparent; border: none; border-radius: 10px; } QPushButton:hover { background-color: rgba(0, 0, 0, 0.05); }")
        self.btn_pop.clicked.connect(self.toggle_floating)
        self.top_bar.addWidget(self.btn_pop)

        self.container_layout.addLayout(self.top_bar)

        # --- Canvas Matplotlib (créé une seule fois) ---
        self.fig = Figure(figsize=(4, 2.5), dpi=80)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        # subplots_adjust remplace tight_layout() (appelé une seule fois ici, jamais après)
        self.fig.subplots_adjust(left=0.13, right=0.97, top=0.95, bottom=0.17)

        # Créer les Line2D une seule fois — on les mettra à jour avec set_data()
        self._lines = {}
        for q in self.quantities:
            line, = self.ax.plot([], [], label=q, marker='o', markersize=2, linewidth=1.5)
            self._lines[q] = line

        self.ax.set_xlabel("Temps (ms)")
        self.ax.grid(True, linestyle=':', alpha=0.6)
        if len(self.quantities) > 1:
            self.ax.legend(loc="upper left", fontsize='small')

        self.container_layout.addWidget(self.canvas, stretch=1)
        self.main_layout.addWidget(self.container)

        # --- Timer de throttle : redraw max toutes les 100ms (10 FPS) ---
        self._needs_redraw = False
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(100)
        self._render_timer.timeout.connect(self._do_render)
        self._render_timer.start()

    # ------------------------------------------------------------------
    #  Réception des données
    # ------------------------------------------------------------------

    def add_new_data(self, ts_ms, values_dict):
            """ Ajoute les mesures reçues de l'UART dans l'historique """
            has_update = any(q in values_dict for q in self.quantities)
            if not has_update:
                return

            self.time_history.append(ts_ms)
            for q in self.quantities:
                if q in values_dict:
                    # CORRECTION : Extraire la valeur numérique pure depuis le sous-dictionnaire
                    float_value = values_dict[q]["value"]
                    self.data_history[q].append(float_value)
                else:
                    # Maintenir la continuité graphique si la quantité n'est pas dans cette trame
                    prev = self.data_history[q][-1] if self.data_history[q] else 0.0
                    self.data_history[q].append(prev)

            # Garder les 150 derniers points max
            if len(self.time_history) > 150:
                self.time_history.pop(0)
                for q in self.quantities:
                    self.data_history[q].pop(0)

            # Marquer qu'un redraw est nécessaire
            self._needs_redraw = True
    # ------------------------------------------------------------------
    #  Rendu Matplotlib (throttlé)
    # ------------------------------------------------------------------

    def _do_render(self):
        """ Slot du timer — seul endroit où canvas.draw() est appelé """
        if not self._needs_redraw:
            return
        self._needs_redraw = False
        self._update_plot()

    def _on_combo_changed(self):
        """ Changement de l'axe X par l'utilisateur → redraw immédiat """
        self._needs_redraw = True
        self._do_render()

    def _update_plot(self):
        """ Met à jour les données des Line2D existantes sans recréer les axes """
        x_mode = self.combo_x.currentData()

        if x_mode == "time":
            x_data = self.time_history
            x_label = "Temps (ms)"
        else:
            x_data = self.data_history.get(x_mode, [])
            x_label = x_mode

        # Mettre à jour le label X seulement si changé
        if self.ax.get_xlabel() != x_label:
            self.ax.set_xlabel(x_label)

        if not x_data:
            self.canvas.draw_idle()
            return

        for q, line in self._lines.items():
            if q == x_mode:
                # Cette grandeur est sur l'axe X → on ne la trace pas en Y
                line.set_data([], [])
                continue
            y_data = self.data_history[q]
            if len(x_data) == len(y_data):
                line.set_data(x_data, y_data)

        # Recalculer les limites des axes (nécessaire après set_data)
        self.ax.relim()
        self.ax.autoscale_view()

        # draw_idle() : Qt planifie le rendu au prochain cycle d'événements (non bloquant)
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    #  Floating / Dock
    # ------------------------------------------------------------------

    def toggle_floating(self):
        if not self.is_floating:
            self.is_floating = True
            self.btn_pop.setIcon(self.reattach_icon)
            
            self.window_container = PlotWindow(self)
            self.window_container.show()
        else:
            if self.window_container:
                self.window_container.close()

    def dock_back(self):
        if self.is_floating:
            self.is_floating = False
            self.btn_pop.setIcon(self.detach_icon)
            
            self.main_layout.addWidget(self.container)
            self.window_container = None
            self.on_dock_callback()
            

class Visualizer(QWidget):
    """
    Composant Visualisateur principal connecté au fichier de configuration 
    et mis à jour par les trames du SerialManager.
    """
    def __init__(self, appareil, parent=None):
        super().__init__(parent)
        self.appareil = appareil  # Instance du modèle Appareil pour lire le dossier de config
        self.plots = {}
        self.is_frozen = False
        
        # Instance unique du décodeur binaire
        self.decoder = UARTFrameDecoder()
        self.decoder.live_data_received.connect(self.dispatch_live_data)
        
        # Layout global
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Barre d'actions supérieure
        top_bar = QHBoxLayout()
        title = QLabel("Visualisateur Temps Réel")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2937;")
        top_bar.addWidget(title)
        top_bar.addStretch()
        
        #icons
        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        self.freeze_icon = QIcon(os.path.join(icons_dir, "visualizer_freeze.png"))
        self.refresh_icon = QIcon(os.path.join(icons_dir, "visualizer_refresh.png"))
        self.resume_icon = QIcon(os.path.join(icons_dir, "visualizer_resume.png"))
        
        self.btn_refresh = QPushButton(self.refresh_icon, "")
        self.btn_refresh.setIconSize(QSize(25, 25))
        self.btn_refresh.setFixedSize(38, 38)
        self.btn_refresh.setStyleSheet("QPushButton { background-color: transparent; border: none; border-radius: 10px; } QPushButton:hover { background-color: rgba(0, 0, 0, 0.05); }")
        self.btn_refresh.clicked.connect(self.refresh_configuration)
        top_bar.addWidget(self.btn_refresh)
        
        self.btn_freeze = QPushButton(self.freeze_icon, "")
        self.btn_freeze.setCheckable(True)
        self.btn_freeze.setIconSize(QSize(25, 25))
        self.btn_freeze.setFixedSize(38, 38)
        self.btn_freeze.setStyleSheet("QPushButton { background-color: transparent; border: none; border-radius: 10px; } QPushButton:hover { background-color: rgba(0, 0, 0, 0.05); }")
        self.btn_freeze.clicked.connect(self.toggle_freeze)
        top_bar.addWidget(self.btn_freeze)
        
        layout.addLayout(top_bar)
        
        # Zone scrollable pour accueillir la grille de plots
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        scroll.setWidget(self.grid_widget)
        
        layout.addWidget(scroll)
        
        # Chargement initial des plots au démarrage
        self.refresh_configuration()

    def refresh_configuration(self):
        """ Relit le fichier de configuration JSON actuel et synchronise les graphiques """
        # On ferme proprement les fenêtres volantes existantes pour éviter des fuites de mémoire
        for card in self.plots.values():
            if card.window_container:
                card.window_container.close()
                
        # Nettoyage complet de la grille PyQt
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        self.plots.clear()
        
        # Charger le fichier JSON (current_config.json) depuis le dossier de l'appareil
        config_path = os.path.join(self.appareil.config_dir, "current_config.json")
        if not os.path.exists(config_path):
            return
            
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception:
            return
            
        # Création d'une carte de plot par règle configurée et activée
        rules = config_data.get("rules", [])
        for rule in rules:
            if not rule.get("enabled", True):
                continue
                
            rule_id = rule.get("rule_id")
            
            rule_text = rule.get("text", f"Règle #{rule_id}")
            
            # Analyser les conditions pour extraire automatiquement les périphériques cibles (ex: device1)
            quantities = []
            legend_items = []  # (quantity_label, model, color)
            structured = rule.get("structured", {})
            rule_name = structured.get("name", f"Règle #{rule_id}")

            # Build a map of available devices from the appareil for fast lookup
            device_map = {}
            for d in self.appareil.get_all_devices():
                dev = d["device"]
                device_map[f"device{dev.uid}"] = {
                    "uid": dev.uid,
                    "model": getattr(dev, "model", ""),
                    "quantity": getattr(dev, "quantity", ""),
                    "color": self.appareil.sensor_lib.get(getattr(dev, "model", ""), {}).get("color", "#999999")
                }

            for condition in structured.get("conditions", []):
                device = condition.get("device")
                if device:
                    quantities.append(device)
                    info = device_map.get(device)
                    if info:
                        q = info.get("quantity") or device
                        # human-friendly label and unit if available
                        q_label = self.appareil.choices.get("quantities", {}).get(q, {}).get("label", q)
                        unit = self.appareil.choices.get("quantities", {}).get(q, {}).get("unit", "")
                        legend_items.append((q_label, info.get("model", ""), info.get("color", "#999999"), device, unit))

            # Si aucune grandeur n'est trouvée (ex: action pure), on ignore ou on met par défaut
            if not quantities:
                continue

            # Supprimer les doublons dans la liste des grandeurs suivies
            quantities = list(dict.fromkeys(quantities))
            # Supprimer doublons dans legend_items en conservant premier
            seen = set()
            unique_legend = []
            for lbl, mdl, col, dev, unit in legend_items:
                key = (dev, lbl)
                if key in seen:
                    continue
                seen.add(key)
                unique_legend.append((lbl, mdl, col, dev, unit))

            card = RulePlotCard(rule_id, rule_name, rule_text, quantities, on_dock_callback=self.reorganize_grid, legend_items=unique_legend, parent=self)
            self.plots[rule_id] = card
            
        self.reorganize_grid()

    def get_rule_list(self):
        return [
            (rule_id, card.rule_name or f"Règle {rule_id}")
            for rule_id, card in self.plots.items()
        ]

    def _sanitize_filename(self, text: str) -> str:
        safe = "".join(c for c in text if c.isalnum() or c in " _-()").rstrip()
        return safe.replace(" ", "_") or "export"

    def export_graphs(self, rule_ids=None, separate=True, output_path=None):
        if rule_ids is None:
            rule_ids = list(self.plots.keys())

        cards = [self.plots[rid] for rid in rule_ids if rid in self.plots]
        if not cards:
            return []

        if separate:
            if not output_path:
                raise ValueError("output_path must be a directory for separate export")
            os.makedirs(output_path, exist_ok=True)
            paths = []
            for card in cards:
                filename = self._sanitize_filename(f"{card.rule_name}_{card.rule_id}") + ".png"
                path = os.path.join(output_path, filename)
                card.fig.savefig(path, bbox_inches='tight', dpi=150)
                paths.append(path)
            return paths

        if not output_path:
            raise ValueError("output_path must be a filename for combined export")

        combined_fig = Figure(figsize=(10, 3 * len(cards)), dpi=150)
        for idx, card in enumerate(cards, start=1):
            ax = combined_fig.add_subplot(len(cards), 1, idx)
            for q, line in card._lines.items():
                x_data = line.get_xdata()
                y_data = line.get_ydata()
                if len(x_data) and len(y_data):
                    ax.plot(x_data, y_data, label=q, marker='o', markersize=2, linewidth=1.5)
            ax.set_title(card.rule_name)
            ax.grid(True, linestyle=':', alpha=0.6)
            ax.set_xlabel('Temps (ms)')
            if len(card.quantities) > 1:
                ax.legend(loc='upper left', fontsize='small')

        combined_fig.tight_layout()
        combined_fig.savefig(output_path, bbox_inches='tight', dpi=150)
        return [output_path]

    def reorganize_grid(self):
        """ Replace intelligemment sur 2 colonnes les graphiques restants (non détachés) """
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget() # Libérer l'emplacement dans la grille
            
        idx = 0
        for card in self.plots.values():
            if not card.is_floating:
                row = idx // 2
                col = idx % 2
                self.grid_layout.addWidget(card, row, col)
                card.setVisible(True)
                idx += 1
            else:
                card.setVisible(False)

    def toggle_freeze(self):
        self.is_frozen = self.btn_freeze.isChecked()
        if self.is_frozen:
            self.btn_freeze.setIcon(self.resume_icon)
            
        else:
            self.btn_freeze.setIcon(self.freeze_icon)
            

    def dispatch_live_data(self, rule_id, ts_ms, data_dict):
        """ Achemine les données décodées vers la règle concernée si le tracé n'est pas gelé """
        if self.is_frozen:
            return
            
        if rule_id in self.plots:
            self.plots[rule_id].add_new_data(ts_ms, data_dict)