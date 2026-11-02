"""
chatbot.py — Interface de chat IA pour le Datalogger STM32F429I-DISC1
Provider par défaut : OpenRouter (gratuit, jamais bloqué)
Clé sur : https://openrouter.ai/keys  → commence par sk-or-v1-
"""

import sys
import json
import base64
import re
import os
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QPushButton, QLabel, QTextEdit, QDialog, QLineEdit,
    QMessageBox, QButtonGroup, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt5.QtGui import QFont

# ─── Couleurs ─────────────────────────────────────────────────────────────────
_BG_PAGE    = "#F3F4F6"
_BORDER     = "#E5E7EB"
_TEXT       = "#1F2937"
_TEXT_DIM   = "#9CA3AF"
_ACCENT     = "#2563eb"
_BG_USER    = "#DBEAFE"
_BG_BOT     = "#F3F4F6"
_ERROR_BG   = "#FEE2E2"
_ERROR_TEXT = "#DC2626"

# ─── Providers gratuits ───────────────────────────────────────────────────────
PROVIDERS = {
    "OpenRouter": {
        "url"   : "https://openrouter.ai/api/v1/chat/completions",
        "model" : "openrouter/free",
        "prefix": "sk-or-",
        "fmt"   : "openai",
        "label" : "OpenRouter  (recommande)",
        "hint"  : "Cle gratuite sur openrouter.ai — commence par sk-or-",
        "link"  : "https://openrouter.ai/keys",
    },
    "Groq": {
        "url"   : "https://api.groq.com/openai/v1/chat/completions",
        "model" : "llama-3.3-70b-versatile",
        "prefix": "gsk_",
        "fmt"   : "openai",
        "label" : "Groq",
        "hint"  : "Cle gratuite sur console.groq.com — commence par gsk_",
        "link"  : "https://console.groq.com",
    },
    "Gemini": {
        "url"   : "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model" : "gemini-2.0-flash",
        "prefix": "AIza",
        "fmt"   : "gemini",
        "label" : "Google Gemini",
        "hint"  : "Cle gratuite sur aistudio.google.com — commence par AIza",
        "link"  : "https://aistudio.google.com/app/apikey",
    },
}

# ─── Persistance ──────────────────────────────────────────────────────────────
_DIR           = Path.home() / ".datalogger_assistant"
_PROVIDER_FILE = _DIR / "provider.txt"
_KEY_FILES     = {n: _DIR / f"key_{n.lower()}.dat" for n in PROVIDERS}
_XOR_SEED      = b"DataloggerSTM32F429"


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def load_provider() -> str:
    try:
        v = _PROVIDER_FILE.read_text("utf-8").strip()
        return v if v in PROVIDERS else "OpenRouter"
    except Exception:
        return "OpenRouter"


def save_provider(name: str) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _PROVIDER_FILE.write_text(name, "utf-8")


def load_key(provider: str) -> str:
    try:
        raw = _KEY_FILES[provider].read_bytes()
        return _xor(base64.b64decode(raw), _XOR_SEED).decode()
    except Exception:
        return ""


def save_key(provider: str, key: str) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _KEY_FILES[provider].write_bytes(base64.b64encode(_xor(key.encode(), _XOR_SEED)))


def delete_key(provider: str) -> None:
    try:
        _KEY_FILES[provider].unlink()
    except Exception:
        pass


# ─── Worker ───────────────────────────────────────────────────────────────────

class AIWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, provider: str, api_key: str, messages: list, system_prompt: str):
        super().__init__()
        self.provider      = provider
        self.api_key       = api_key
        self.messages      = messages
        self.system_prompt = system_prompt

    def run(self):
        cfg = PROVIDERS[self.provider]
        try:
            if cfg["fmt"] == "openai":
                self._call_openai(cfg)
            else:
                self._call_gemini(cfg)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("error", {}).get("message", body)
            except Exception:
                detail = body
            self.error.emit(f"HTTP {e.code}: {detail}")
        except Exception as e:
            self.error.emit(str(e))

    def _call_openai(self, cfg: dict):
        messages = [{"role": "system", "content": self.system_prompt}] + self.messages
        payload  = json.dumps({
            "model"      : cfg["model"],
            "max_tokens" : 2048,
            "temperature": 0.3,
            "messages"   : messages,
        }).encode()
        headers = {
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.provider == "OpenRouter":
            headers["HTTP-Referer"] = "https://datalogger-app"
            headers["X-Title"]      = "Datalogger Assistant"

        req = urllib.request.Request(cfg["url"], data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            self.finished.emit(data["choices"][0]["message"]["content"])

    def _call_gemini(self, cfg: dict):
        contents, injected = [], False
        for msg in self.messages:
            role = "user" if msg["role"] == "user" else "model"
            text = msg["content"]
            if role == "user" and not injected:
                text     = f"{self.system_prompt}\n\n---\n\n{text}"
                injected = True
            contents.append({"role": role, "parts": [{"text": text}]})

        if not injected:
            contents = [{"role": "user", "parts": [{"text": self.system_prompt}]}]

        payload = json.dumps({
            "contents"        : contents,
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.3},
        }).encode()
        req = urllib.request.Request(
            f"{cfg['url']}?key={self.api_key}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            self.finished.emit(data["candidates"][0]["content"]["parts"][0]["text"])


# ─── Dialogue principal ───────────────────────────────────────────────────────

class ChatbotDialog(QDialog):
    """
    Chat IA pour generer des current_config.json a partir
    d'une description en langage naturel.
    Provider par defaut : OpenRouter (gratuit, sans blocage reseau).
    """

    rule_generated  = pyqtSignal(str)   # JSON brut (legacy)
    config_applied  = pyqtSignal(str)   # chemin vers chat_current_config.json

    def __init__(
        self,
        parent=None,
        device_names=None,
        output_names=None,
        device_labels=None,
        appareil_config: dict = None,
        choices_config: dict  = None,
        api_key: str          = "",
        config_dir: str       = "config",   # dossier où sauvegarder
    ):
        super().__init__(parent)
        self.device_names    = device_names    or set()
        self.output_names    = output_names    or set()
        self.device_labels   = device_labels   or {}
        self.appareil_config = appareil_config or {}
        self.choices_config  = choices_config or {}
        self.config_dir      = config_dir

        self.provider = load_provider()
        self.api_key  = api_key or load_key(self.provider)

        self.history: list = []
        self._worker = None

        self.setWindowTitle("Assistant IA - HarviX")
        self.setMinimumSize(520, 640)
        self.setModal(False)
        self._build_ui()
        self._add_bot_message(self._welcome_text())

    # ── System prompt ─────────────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        return f"""Tu es un expert en systemes embarques et en physique, assistant l'utilisateur
a configurer un datalogger STM32F429I-DISC1.

=== HARDWARE ===
{json.dumps(self.appareil_config, indent=2, ensure_ascii=False)}

=== CAPTEURS DISPONIBLES ===
{json.dumps(self.choices_config, indent=2, ensure_ascii=False)}

=== CAPTEURS ACTIFS ===
{', '.join(sorted(self.device_names)) or '(aucun)'}

=== SORTIES ACTIVES ===
{', '.join(sorted(self.output_names)) or '(aucune)'}

=== FORMAT EXACT DU current_config.json ===
Voici le schema REEL que tu dois respecter — ne l'invente pas :

{{
  "assignments": [
    {{
      "slot_id": <int>,           // id du slot dans appareil_config
      "type": <"SPI"|"I2C"|"ADC"|"Digital">,  // type du slot
      "devices": [
        {{
          "uid": <int>,           // identifiant unique incremental global
          "model": <str>,         // modele exact de choices_config
          "quantity": <str>,      // UNE quantite parmi quantities du capteur
          "i2c_address": <str>    // SEULEMENT si type == "I2C", ex: "0x76"
        }}
      ]
    }}
  ],
  "outputs_active": [<int>, ...],  // ids des sorties activees
  "rules": [
    {{
      "rule_id": <int>,
      "enabled": true,
      "text": "<nom>:\\n<expression>"  // voir syntaxe ci-dessous
    }}
  ],
  "period_ms": <int>,
  "stream_enabled": <bool>,
  "log_enabled": <bool>
}}

=== SYNTAXE DES REGLES ===
Format : "<nom_regle>:\\n<condition> => <action>"
- Devices references par deviceUID (ex: device5, device8)
- Operateurs condition : >, <, >=, <=, ==, != et combinaisons avec & (ET) | (OU)
- Expressions arithmetiques : device5 * 2, device5 + device6, etc.
- Actions disponibles :
    on(sortieN)          allumer la sortie N
    off(sortieN)         eteindre la sortie N
    rotation(servoN, angle)  positionner servo N a l'angle (sorties pwm)
    log                  enregistrer dans le journal
- Plusieurs actions separees par &

Exemples de regles valides :
  "regle_1:\\ndevice5>5=>on(sortie1)"
  "regle_2:\\ndevice5*2>device6&device9>10=>on(sortie1)"
  "regle_3:\\ndevice5>5=>rotation(servo5,20)"
  "alarme_temp:\\ndevice8>80=>on(sortie3)&log"
  "regulation:\\ndevice10<20|device11>90=>off(sortie2)&on(sortie1)"

=== EXEMPLES COMPLETS (few-shot) ===

--- Exemple 1 : Etude Gay-Lussac (pression vs temperature gaz) ---
Demande : "Je veux mesurer pression et temperature pour etudier la loi de Gay-Lussac"
CONFIG_JSON_START
{{
  "assignments": [
    {{
      "slot_id": 1,
      "type": "SPI",
      "devices": [
        {{
          "uid": 1,
          "model": "BMP280",
          "quantity": "pressure"
        }}
      ]
    }},
    {{
      "slot_id": 2,
      "type": "SPI",
      "devices": [
        {{
          "uid": 2,
          "model": "BMP280",
          "quantity": "temperature"
        }}
      ]
    }}
  ],
  "outputs_active": [],
  "rules": [],
  "period_ms": 500,
  "stream_enabled": true,
  "log_enabled": true
}}
CONFIG_JSON_END

--- Exemple 2 : Surveillance temperature avec alarme ---
Demande : "Surveiller la temperature d'un four, allumer sortie1 si > 80 degres"
CONFIG_JSON_START
{{
  "assignments": [
    {{
      "slot_id": 4,
      "type": "SPI",
      "devices": [
        {{
          "uid": 1,
          "model": "MAX31865",
          "quantity": "temperature"
        }}
      ]
    }}
  ],
  "outputs_active": [1],
  "rules": [
    {{
      "rule_id": 1,
      "enabled": true,
      "text": "alarme_four:\\ndevice1>80=>on(sortie1)&log"
    }}
  ],
  "period_ms": 1000,
  "stream_enabled": false,
  "log_enabled": true
}}
CONFIG_JSON_END

--- Exemple 3 : Station meteo complete ---
Demande : "Station meteo : temperature, humidite, pression, luminosite"
CONFIG_JSON_START
{{
  "assignments": [
    {{
      "slot_id": 6,
      "type": "I2C",
      "devices": [
        {{
          "uid": 1,
          "model": "AHT20",
          "quantity": "temperature",
          "i2c_address": "0x38"
        }},
        {{
          "uid": 2,
          "model": "AHT20",
          "quantity": "humidity",
          "i2c_address": "0x38"
        }},
        {{
          "uid": 3,
          "model": "BH1750",
          "quantity": "light_lux",
          "i2c_address": "0x23"
        }}
      ]
    }},
    {{
      "slot_id": 1,
      "type": "SPI",
      "devices": [
        {{
          "uid": 4,
          "model": "BMP280",
          "quantity": "pressure"
        }}
      ]
    }}
  ],
  "outputs_active": [],
  "rules": [],
  "period_ms": 2000,
  "stream_enabled": true,
  "log_enabled": true
}}
CONFIG_JSON_END

--- Exemple 4 : Mesure courant + tension avec regulation servo ---
Demande : "Mesurer courant et tension d'une batterie, controler servo si tension trop basse"
CONFIG_JSON_START
{{
  "assignments": [
    {{
      "slot_id": 6,
      "type": "I2C",
      "devices": [
        {{
          "uid": 1,
          "model": "INA219",
          "quantity": "current",
          "i2c_address": "0x40"
        }},
        {{
          "uid": 2,
          "model": "INA219",
          "quantity": "voltage",
          "i2c_address": "0x40"
        }}
      ]
    }}
  ],
  "outputs_active": [5],
  "rules": [
    {{
      "rule_id": 1,
      "enabled": true,
      "text": "batt_faible:\\ndevice2<11.5=>rotation(servo5,90)&log"
    }}
  ],
  "period_ms": 500,
  "stream_enabled": true,
  "log_enabled": true
}}
CONFIG_JSON_END

--- Exemple 5 : Comparaison deux capteurs temperature + regle differentielle ---
Demande : "Comparer deux sondes temperature, alerter si difference > 5 degres"
CONFIG_JSON_START
{{
  "assignments": [
    {{
      "slot_id": 1,
      "type": "SPI",
      "devices": [
        {{
          "uid": 1,
          "model": "BMP280",
          "quantity": "temperature"
        }}
      ]
    }},
    {{
      "slot_id": 6,
      "type": "I2C",
      "devices": [
        {{
          "uid": 2,
          "model": "LM75",
          "quantity": "temperature",
          "i2c_address": "0x48"
        }}
      ]
    }}
  ],
  "outputs_active": [1],
  "rules": [
    {{
      "rule_id": 1,
      "enabled": true,
      "text": "diff_temp:\\ndevice1-device2>5=>on(sortie1)&log"
    }},
    {{
      "rule_id": 2,
      "enabled": true,
      "text": "diff_inv:\\ndevice2-device1>5=>on(sortie1)&log"
    }}
  ],
  "period_ms": 1000,
  "stream_enabled": false,
  "log_enabled": true
}}
CONFIG_JSON_END

=== TA MISSION ===
1. Comprendre la demande en langage naturel.
2. Expliquer brievement le raisonnement physique/technique.
3. Generer OBLIGATOIREMENT a la fin un bloc config entre :
   CONFIG_JSON_START
   {{ ... }}
   CONFIG_JSON_END

REGLES IMPORTANTES :
- uid doit etre unique et incremental sur tous les devices (1, 2, 3, ...)
- Un capteur avec plusieurs quantities = plusieurs devices dans le meme slot avec le meme uid si meme adresse (voir AHT20 exemple 3)
- i2c_address UNIQUEMENT pour les slots I2C, jamais pour SPI/ADC/Digital
- Utilise les adresses de la liste choices_config
- Ne mets jamais un capteur dans un slot incompatible avec son bus_compatible
- Reponds en francais, de facon concise et pedagogique."""

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(f"QDialog {{ background: {_BG_PAGE}; font-family: 'Segoe UI', Arial, sans-serif; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet("QFrame { background: white; border-radius: 10px; }")
        hl  = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 8, 12, 8)
        t = QLabel("Assistant IA")
        t.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {_ACCENT}; border: none;")
        hl.addWidget(t)
        hl.addStretch()
        ctx = QLabel(f"  {len(self.device_names)} capteur(s)    {len(self.output_names)} sortie(s)")
        ctx.setStyleSheet(f"font-size: 10px; color: {_TEXT_DIM}; border: none;")
        hl.addWidget(ctx)
        x = QPushButton("x")
        x.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: {_TEXT_DIM}; font-size: 14px; }} QPushButton:hover {{ color: #EF4444; }}")
        x.clicked.connect(self.close)
        hl.addWidget(x)
        root.addWidget(hdr)

        # Barre provider/cle
        self.api_bar = QFrame()
        self._refresh_api_bar()
        root.addWidget(self.api_bar)

        # Zone messages
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.msg_container = QWidget()
        self.msg_layout    = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(8, 8, 8, 8)
        self.msg_layout.setSpacing(10)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self.msg_container)
        root.addWidget(self.scroll, stretch=1)

        # Zone saisie
        inp_frame = QFrame()
        inp_frame.setStyleSheet(f"QFrame {{ background: white; border-radius: 12px; border: 1px solid {_BORDER}; }}")
        il = QHBoxLayout(inp_frame)
        il.setContentsMargins(12, 8, 12, 8)

        self.input_field = QTextEdit()
        self.input_field.setPlaceholderText(
            "Decrivez votre experience...\n"
            "Ex : etudier la loi de Gay-Lussac avec pression et temperature\n"
            "Entree = envoyer  |  Maj+Entree = nouvelle ligne"
        )
        self.input_field.setMaximumHeight(90)
        self.input_field.setStyleSheet(f"QTextEdit {{ border: none; background: transparent; font-size: 12px; color: {_TEXT}; }}")
        self.input_field.installEventFilter(self)
        il.addWidget(self.input_field, stretch=1)

        btns = QVBoxLayout()
        btns.setSpacing(6)
        self.send_btn = QPushButton("Envoyer")
        self.send_btn.setStyleSheet(f"""
            QPushButton {{ background: {_ACCENT}; color: white; border: none;
                border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover    {{ background: #2563EB; }}
            QPushButton:disabled {{ background: #93C5FD; }}
        """)
        self.send_btn.clicked.connect(self._send)
        self.clear_btn = QPushButton("Effacer")
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{ background: #F3F4F6; color: {_TEXT_DIM}; border: 1px solid {_BORDER};
                border-radius: 8px; padding: 8px 14px; font-size: 12px; }}
            QPushButton:hover {{ background: #E5E7EB; }}
        """)
        self.clear_btn.clicked.connect(self._clear)
        btns.addWidget(self.send_btn)
        btns.addWidget(self.clear_btn)
        il.addLayout(btns)
        root.addWidget(inp_frame)

    def eventFilter(self, obj, event):
        if obj == self.input_field and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                self._send()
                return True
            if event.key() == Qt.Key_Return and (event.modifiers() & Qt.ShiftModifier):
                self.input_field.insertPlainText("\n")
                return True
        return super().eventFilter(obj, event)

    # ── Messages ──────────────────────────────────────────────────────────────

    def _welcome_text(self) -> str:
        if self.device_names:
            sorted_names = sorted(self.device_names)
            label_map = self.device_labels or {}
            sensors = [label_map.get(name, name) for name in sorted_names]
            s = f"Capteurs : {', '.join(sensors)}"
        else:
            s = "Aucun capteur configure."
        o = (f"Sorties : {', '.join(sorted(self.output_names))}"
             if self.output_names else "Aucune sortie configuree.")
        return (
            "Bonjour ! Decrivez votre experience en langage naturel "
            "et je genererai la configuration appropriee.\n\n"
            f"{s}\n{o}\n\n"
            "Exemple : Je veux etudier la loi de Gay-Lussac, "
            "mesurer pression et temperature d'un gaz."
        )

    def _add_bot_message(self, text: str):
        self._add_bubble("assistant", text)

    def _add_bubble(self, role: str, text: str):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_BG_BOT if role == 'assistant' else _BG_USER}; border-radius: 12px; }}")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(3)

        hdr = QHBoxLayout()
        who = QLabel("Assistant" if role == "assistant" else "Vous")
        who.setStyleSheet(f"font-weight: bold; font-size: 10px; color: {_TEXT_DIM}; border: none;")
        ts  = QLabel(datetime.now().strftime("%H:%M"))
        ts.setStyleSheet(f"font-size: 9px; color: {_TEXT_DIM}; border: none;")
        hdr.addWidget(who)
        hdr.addStretch()
        hdr.addWidget(ts)
        fl.addLayout(hdr)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px; border: none; background: transparent;")
        fl.addWidget(lbl)

        self.msg_layout.insertWidget(self.msg_layout.count() - 1, f)
        QTimer.singleShot(50, self._scroll_bottom)

    def _add_config_block(self, json_text: str):
        f = QFrame()
        f.setStyleSheet("QFrame { background: #0D1117; border-radius: 10px; }")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(6)

        hdr = QHBoxLayout()
        lbl = QLabel("current_config.json")
        lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #58A6FF; border: none;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        cp = QPushButton("Copier")
        cp.setStyleSheet("QPushButton { font-size:10px; padding:2px 8px; border:1px solid #58A6FF; border-radius:4px; background:transparent; color:#58A6FF; } QPushButton:hover { background:#1C2128; }")
        cp.clicked.connect(lambda: (
            QApplication.clipboard().setText(json_text),
            cp.setText("Copie !"),
            QTimer.singleShot(1500, lambda: cp.setText("Copier"))
        ))

        ap = QPushButton("Appliquer")
        ap.setStyleSheet("QPushButton { font-size:10px; padding:2px 8px; border:1px solid #3FB950; border-radius:4px; background:transparent; color:#3FB950; font-weight:bold; } QPushButton:hover { background:#1C2128; }")
        ap.clicked.connect(lambda: self._apply_config(json_text, ap))

        hdr.addWidget(cp)
        hdr.addWidget(ap)
        fl.addLayout(hdr)

        code = QLabel(json_text)
        code.setWordWrap(True)
        code.setTextFormat(Qt.PlainText)
        code.setStyleSheet("font-family: 'Consolas','Courier New',monospace; font-size: 11px; color: #E6EDF3; border: none; background: transparent;")
        fl.addWidget(code)

        self.msg_layout.insertWidget(self.msg_layout.count() - 1, f)
        QTimer.singleShot(50, self._scroll_bottom)

    def _apply_config(self, json_text: str, btn: QPushButton):
        """Sauvegarde dans chat_current_config.json et émet config_applied."""
        try:
            parsed = json.loads(json_text)
            path   = os.path.join(self.config_dir, "chat_current_config.json")
            os.makedirs(self.config_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(parsed, fh, indent=2, ensure_ascii=False)

            btn.setText("Applique !")
            btn.setStyleSheet("QPushButton { font-size:10px; padding:2px 8px; border:1px solid #16A34A; border-radius:4px; background:#16A34A; color:white; font-weight:bold; }")
            QTimer.singleShot(2000, lambda: (
                btn.setText("Appliquer"),
                btn.setStyleSheet("QPushButton { font-size:10px; padding:2px 8px; border:1px solid #3FB950; border-radius:4px; background:transparent; color:#3FB950; font-weight:bold; } QPushButton:hover { background:#1C2128; }")
            ))

            self.rule_generated.emit(json_text)   # legacy
            self.config_applied.emit(path)        # nouveau signal avec le chemin

        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de sauvegarder la config :\n{e}")

    def _add_loading(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_BG_BOT}; border-radius: 10px; }}")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(12, 8, 12, 8)
        self._loading_lbl = QLabel("Reflexion en cours")
        self._loading_lbl.setStyleSheet(f"font-size: 11px; color: {_TEXT_DIM}; border: none;")
        fl.addWidget(self._loading_lbl)
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(400)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, f)
        QTimer.singleShot(50, self._scroll_bottom)
        return f

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self._loading_lbl.setText("Reflexion en cours" + "." * self._dots)

    def _remove_loading(self, f: QFrame):
        self._timer.stop()
        f.deleteLater()

    def _scroll_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Envoi / reponse ───────────────────────────────────────────────────────

    def _send(self):
        msg = self.input_field.toPlainText().strip()
        if not msg:
            return
        if not self.api_key:
            self._add_bot_message("Aucune cle API configuree. Cliquez sur <b>Configurer</b> ci-dessus.")
            return

        self.send_btn.setEnabled(False)
        self.input_field.setEnabled(False)
        self.input_field.clear()

        self._add_bubble("user", msg)
        self.history.append({"role": "user", "content": msg})
        loading = self._add_loading()

        self._worker = AIWorker(self.provider, self.api_key, list(self.history), self._system_prompt())
        self._worker.finished.connect(lambda r: self._on_response(r, loading))
        self._worker.error.connect(lambda e: self._on_error(e, loading))
        self._worker.start()

    @pyqtSlot(str)
    def _on_response(self, text: str, loading: QFrame):
        self._remove_loading(loading)
        self.history.append({"role": "assistant", "content": text})

        pattern = r"CONFIG_JSON_START\s*([\s\S]*?)\s*CONFIG_JSON_END"
        match   = re.search(pattern, text)
        prose   = re.sub(pattern, "", text).strip()

        if prose:
            self._add_bot_message(prose)
        if match:
            raw = match.group(1).strip()
            try:
                pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                pretty = raw
            self._add_config_block(pretty)

        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()

    @pyqtSlot(str)
    def _on_error(self, msg: str, loading: QFrame):
        self._remove_loading(loading)
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_ERROR_BG}; border-radius: 10px; }}")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(12, 8, 12, 8)
        lbl = QLabel(f"Erreur API ({self.provider}) : {msg}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_ERROR_TEXT}; font-size: 11px; border: none;")
        fl.addWidget(lbl)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, f)
        QTimer.singleShot(50, self._scroll_bottom)
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)

    def _clear(self):
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.history.clear()
        self._add_bot_message(self._welcome_text())

    # ── Gestion provider / cle ────────────────────────────────────────────────

    def _refresh_api_bar(self):
        old = self.api_bar.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            try:
                import sip; sip.delete(old)
            except Exception:
                old.setParent(None)

        has_key = bool(self.api_key)

        if has_key:
            self.api_bar.setStyleSheet("QFrame { background: #F0FDF4; border-radius: 8px; border: 1px solid #BBF7D0; }")
            row = QHBoxLayout(self.api_bar)
            row.setContentsMargins(10, 5, 10, 5)
            dot = QLabel("*")
            dot.setStyleSheet("color: #16A34A; font-size: 14px; font-weight: bold; border: none;")
            row.addWidget(dot)
            masked = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key) > 14 else "****"
            lbl = QLabel(f"<b>{self.provider}</b> &nbsp;<span style='color:#9CA3AF;font-size:10px'>{masked}</span>")
            lbl.setStyleSheet(f"font-size: 11px; color: #15803D; border: none;")
            row.addWidget(lbl)
            row.addStretch()
            btn_mod = QPushButton("Modifier")
            btn_mod.setStyleSheet("QPushButton { font-size:10px; padding:2px 10px; border:1px solid #BBF7D0; border-radius:5px; background:transparent; color:#15803D; } QPushButton:hover { background:#DCFCE7; }")
            btn_mod.clicked.connect(self._open_config_dialog)
            row.addWidget(btn_mod)
            btn_del = QPushButton("Supprimer")
            btn_del.setStyleSheet("QPushButton { font-size:10px; padding:2px 10px; border:1px solid #FECACA; border-radius:5px; background:transparent; color:#DC2626; } QPushButton:hover { background:#FEE2E2; }")
            btn_del.clicked.connect(self._delete_key)
            row.addWidget(btn_del)
        else:
            self.api_bar.setStyleSheet("QFrame { background: #FFF7ED; border-radius: 8px; border: 1px solid #FED7AA; }")
            row = QHBoxLayout(self.api_bar)
            row.setContentsMargins(10, 5, 10, 5)
            lbl = QLabel(f"Aucune cle configuree pour <b>{self.provider}</b>")
            lbl.setStyleSheet(f"font-size: 11px; color: #92400E; border: none;")
            row.addWidget(lbl)
            row.addStretch()
            btn_add = QPushButton("Configurer...")
            btn_add.setStyleSheet(f"QPushButton {{ font-size:10px; padding:2px 12px; border:none; border-radius:5px; background:{_ACCENT}; color:white; font-weight:bold; }} QPushButton:hover {{ background:#2563EB; }}")
            btn_add.clicked.connect(self._open_config_dialog)
            row.addWidget(btn_add)

    def _open_config_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Configuration IA")
        dlg.setFixedWidth(460)
        dlg.setStyleSheet(f"background: {_BG_PAGE}; font-family: 'Segoe UI', Arial, sans-serif;")

        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)

        title_lbl = QLabel("Choisir le provider IA gratuit")
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {_TEXT};")
        v.addWidget(title_lbl)

        selected = [self.provider]
        grp      = QButtonGroup(dlg)

        prov_frame = QFrame()
        prov_frame.setStyleSheet(f"QFrame {{ background: white; border-radius: 8px; border: 1px solid {_BORDER}; }}")
        pfl = QVBoxLayout(prov_frame)
        pfl.setContentsMargins(8, 8, 8, 8)
        pfl.setSpacing(4)

        hint_lbl = QLabel(PROVIDERS[self.provider]["hint"])
        hint_lbl.setStyleSheet(f"font-size: 10px; color: {_TEXT_DIM};")

        link_lbl = QLabel(f"<a href='{PROVIDERS[self.provider]['link']}'>{PROVIDERS[self.provider]['link']}</a>")
        link_lbl.setOpenExternalLinks(True)
        link_lbl.setStyleSheet(f"font-size: 10px; color: {_ACCENT};")

        field = QLineEdit()
        field.setEchoMode(QLineEdit.Password)
        field.setText(load_key(self.provider))
        field.setPlaceholderText(PROVIDERS[self.provider]["prefix"] + "...")
        field.setStyleSheet(f"""
            QLineEdit {{ border: 1px solid {_BORDER}; border-radius: 7px;
                padding: 7px 10px; font-size: 12px; background: white; color: {_TEXT}; }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)

        for name, cfg in PROVIDERS.items():
            rb = QPushButton(f"  {cfg['label']}")
            rb.setCheckable(True)
            rb.setChecked(name == self.provider)
            rb.setStyleSheet(f"""
                QPushButton {{ text-align:left; font-size:12px; padding:7px 10px;
                    border:1px solid transparent; border-radius:6px;
                    background:{'#EFF6FF' if name == self.provider else 'transparent'};
                    color:{_ACCENT if name == self.provider else _TEXT}; }}
                QPushButton:checked {{ background:#EFF6FF; color:{_ACCENT}; border-color:#BFDBFE; }}
                QPushButton:hover:!checked {{ background:#F9FAFB; }}
            """)
            grp.addButton(rb)
            pfl.addWidget(rb)

            def _on_pick(checked, n=name):
                if checked:
                    selected[0] = n
                    hint_lbl.setText(PROVIDERS[n]["hint"])
                    link_lbl.setText(f"<a href='{PROVIDERS[n]['link']}'>{PROVIDERS[n]['link']}</a>")
                    field.setPlaceholderText(PROVIDERS[n]["prefix"] + "...")
                    field.setText(load_key(n))
            rb.toggled.connect(_on_pick)

        v.addWidget(prov_frame)
        v.addWidget(hint_lbl)
        v.addWidget(link_lbl)
        v.addWidget(field)

        show_btn = QPushButton("Afficher la cle")
        show_btn.setCheckable(True)
        show_btn.setStyleSheet(f"QPushButton {{ font-size:10px; padding:2px 8px; border:1px solid {_BORDER}; border-radius:5px; background:white; color:{_TEXT_DIM}; }} QPushButton:checked {{ color:{_ACCENT}; border-color:{_ACCENT}; }}")
        show_btn.toggled.connect(lambda c: field.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password))

        btn_row = QHBoxLayout()
        btn_row.addWidget(show_btn)
        btn_row.addStretch()

        cancel = QPushButton("Annuler")
        cancel.setStyleSheet(f"QPushButton {{ font-size:12px; padding:6px 16px; border:1px solid {_BORDER}; border-radius:7px; background:white; color:{_TEXT}; }} QPushButton:hover {{ background:#F3F4F6; }}")
        cancel.clicked.connect(dlg.reject)

        save = QPushButton("Enregistrer")
        save.setStyleSheet(f"QPushButton {{ font-size:12px; padding:6px 16px; border:none; border-radius:7px; background:{_ACCENT}; color:white; font-weight:bold; }} QPushButton:hover {{ background:#2563EB; }}")

        def _do_save():
            key      = field.text().strip()
            provider = selected[0]
            prefix   = PROVIDERS[provider]["prefix"]
            if not key.startswith(prefix):
                QMessageBox.warning(dlg, "Cle invalide", f"La cle {provider} doit commencer par {prefix}...")
                return
            self.provider = provider
            self.api_key  = key
            save_provider(provider)
            save_key(provider, key)
            self._refresh_api_bar()
            dlg.accept()

        save.clicked.connect(_do_save)
        field.returnPressed.connect(_do_save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        v.addLayout(btn_row)
        dlg.exec_()

    def _delete_key(self):
        if QMessageBox.question(
            self, "Supprimer", f"Supprimer la cle {self.provider} ?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            delete_key(self.provider)
            self.api_key = ""
            self._refresh_api_bar()

    def update_context(self, device_names, output_names):
        self.device_names = device_names
        self.output_names = output_names


# ─── Test standalone ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _load_json(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    app    = QApplication(sys.argv)
    dialog = ChatbotDialog(
        device_names    = {"BMP280_slot8", "AHT20_slot6"},
        output_names    = {"Sortie 1", "Servo 1"},
        appareil_config = _load_json("appareil_config.json"),
        choices_config  = _load_json("choices_config.json"),
    )
    dialog.show()
    sys.exit(app.exec_())