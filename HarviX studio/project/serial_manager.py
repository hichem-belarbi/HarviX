"""
serial_manager.py

Protocole de trame (sans CRC) :
    [STX=0xAA] [CMD(1)] [LEN(1)] [PAYLOAD(LEN)] [ETX=0x55]

Flux de synchronisation + patch :
    1. CMD_SYNC_REQUEST  → la carte répond SYNC_RESPONSE (JSON de son état)
    2. Sauvegarder dans actual_config.json
    3. Calculer le diff (current_config vs actual_config)
    4. Envoyer seulement les différences, ACK par ACK

Avantage : si la connexion coupe, on re-sync et on renvoie seulement
           ce qui n'a pas encore été appliqué — idempotent par nature.
"""

import json
import struct
import time
import re
import os
from typing import Dict, List, Optional, Tuple

from PyQt5.QtGui import QIcon
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
# ── Protocole ─────────────────────────────────────────────────
FRAME_STX = 0xAA
FRAME_ETX = 0x55

# Système
CMD_SYNC_REQUEST    = 0x01
CMD_SYNC_RESPONSE   = 0x02
CMD_PING            = 0x06
CMD_GET_STATUS      = 0x07
CMD_STATUS_RESPONSE = 0x08

# Capteurs
CMD_ASSIGN_SENSOR     = 0x10
CMD_CLEAR_DEVICE      = 0x11
CMD_CLEAR_SLOT        = 0x12
CMD_CLEAR_ALL_SENSORS = 0x13

# Règles
CMD_ADD_RULE        = 0x20
CMD_REMOVE_RULE     = 0x21
CMD_CLEAR_ALL_RULES = 0x24

# Acquisition
CMD_START_ACQ  = 0x30
CMD_STOP_ACQ   = 0x31
CMD_SET_PERIOD = 0x32

# Flash
CMD_SAVE_TO_FLASH   = 0x40
CMD_LOAD_FROM_FLASH = 0x41

# Réponses
CMD_ACK  = 0xF0
CMD_NACK = 0xF1

# ── Enums miroir de commander_types.h ─────────────────────────
# FIX : retrait de "SENSOR_COUNT" qui n'est pas un modèle réel
SENSOR_MODEL: Dict[str, int] = {
    "NONE":    0,
    "BMP280":  1,
    "AHT20":   2,
    "BH1750":  3,
    "INA219":  4,
    "LM75":    5,
    "NTC":     6,
    "ACS712":  7,
    "DHT11":   8,
    "DHT22":   9,
    "DS18B20": 10,
}

# FIX : vérifier l'alignement avec Physical_Quantity_t dans sensor_types.h
# Si QUANTITY_TEMPERATURE=0 côté firmware, inverser none/temperature ci-dessous.
PHYSICAL_QUANTITY: Dict[str, int] = {
    "none":          0,
    "temperature":   1,
    "pressure":      2,
    "humidity":      3,
    "voltage":       4,
    "light_lux":     5,
    "bus_voltage":   6,
    "shunt_voltage": 7,
    "current":       8,
    "power":         9,
    "count":         10,
}

# FIX : acq_mode — les valeurs doivent correspondre exactement aux clés de ce dict
ACQ_MODE: Dict[str, int] = {
    "no_log_no_stream": 0,
    "sd_only":          1,
    "stream_only":      2,
    "both":             3,
}

# ── Enums miroir de rule_types.h ──────────────────────────────
PRIM_MAP: Dict[str, int] = {
    "device":        1,
    "current":       1,
    "mean":          2,
    "avg":           2,
    "slope":         3,
    "stddev":        4,
    "min":           5,
    "max":           6,
    "monotonicity":  7,
    "noise":         8,
    "noise_level":   8,
    "deriv":         9,
    "deriv_time":    9,
    "delta":         10,
    "delta_last":    10,
    "near_multiple": 11,
}

# CMP_GT=0, CMP_LT=1, CMP_GTE=2, CMP_LTE=3, CMP_EQ=4, CMP_NEQ=5, CMP_APPROX=6
CMP_MAP: Dict[str, int] = {
    ">":  0,
    "<":  1,
    ">=": 2,
    "<=": 3,
    "==": 4,
    "!=": 5,
    "~=": 6,   # FIX : CMP_APPROX — plus CMP_EQ
}

# TRIG_LOG=0, TRIG_STREAM=1, TRIG_ACTION=2 — miroir exact de rule_types.h
TRIG_LOG    = 1
TRIG_STREAM = 2
TRIG_ACTION = 3

# Action codes
ACT_GPIO_LOW    = 0
ACT_GPIO_HIGH   = 1
ACT_GPIO_TOGGLE = 2

# MAX_UIDS_PER_TRIGGER — miroir de rule_types.h
MAX_UIDS_PER_TRIGGER = 8


# ═════════════════════════════════════════════════════════════
#  Helpers de diff
# ═════════════════════════════════════════════════════════════

def _flatten_devices(config: dict) -> Dict[int, dict]:
    """
    Retourne { uid: { slot_id, model, quantity, i2c_address } }
    depuis la structure assignments[] du JSON.
    """
    result = {}
    for assignment in config.get("assignments", []):
        slot_id = assignment.get("slot_id")
        for device in assignment.get("devices", []):
            uid = device.get("uid")
            if uid is not None:
                result[uid] = {
                    "uid":         uid,
                    "slot_id":     slot_id,
                    "model":       device.get("model", ""),
                    "quantity":    device.get("quantity", ""),
                    "i2c_address": device.get("i2c_address", "0x00"),
                }
    return result


def _parse_i2c(addr) -> int:
    """Convertit '0x76' ou 118 en int."""
    try:
        if isinstance(addr, str):
            return int(addr, 16)
        return int(addr)
    except (ValueError, TypeError):
        return 0


def compute_diff(current: dict, actual: dict) -> dict:
    """
    Calcule les opérations à effectuer pour amener l'état de la
    carte (actual) vers la configuration souhaitée (current).

    Retourne :
    {
        "sensors_to_remove": [uid, ...],
        "sensors_to_add":    [{ slot_id, model, quantity, i2c_address }, ...],
        "rules_to_remove":   [rule_id, ...],
        "rules_to_add":      [{ rule_id, enabled, text, ... }, ...],
        "period_changed":    int | None,
        "stream_changed":    bool | None,
        "acq_mode":          str,   ← clé valide dans ACQ_MODE
    }
    """
    diff: dict = {
        "sensors_to_remove": [],
        "sensors_to_add":    [],
        "rules_to_remove":   [],
        "rules_to_add":      [],
        "period_changed":    None,
        "stream_changed":    None,
        "acq_mode":          "both",
    }

    # ── Devices ──────────────────────────────────────────────
    actual_devs  = _flatten_devices(actual)
    current_devs = _flatten_devices(current)

    for uid in sorted(current_devs.keys()):
        dev = current_devs[uid]
        if uid not in actual_devs:
            diff["sensors_to_add"].append(dev)
        else:
            a = actual_devs[uid]
            if (a["slot_id"]  != dev["slot_id"]  or
                a["model"]    != dev["model"]     or
                a["quantity"] != dev["quantity"]  or
                _parse_i2c(a["i2c_address"]) != _parse_i2c(dev["i2c_address"])):
                diff["sensors_to_remove"].append(uid)
                diff["sensors_to_add"].append(dev)

    for uid in sorted(actual_devs.keys()):
        if uid not in current_devs:
            diff["sensors_to_remove"].append(uid)

    # ── Règles ───────────────────────────────────────────────
    actual_rules  = {r["rule_id"]: r for r in actual.get("rules", [])}
    current_rules = {r["rule_id"]: r for r in current.get("rules", [])}

    for rid, rule in current_rules.items():
        if rid not in actual_rules:
            diff["rules_to_add"].append(rule)
        else:
            a = actual_rules[rid]
            if (a.get("enabled") != rule.get("enabled") or
                a.get("text", "").strip() != rule.get("text", "").strip()):
                diff["rules_to_remove"].append(rid)
                diff["rules_to_add"].append(rule)

    for rid in actual_rules:
        if rid not in current_rules:
            diff["rules_to_remove"].append(rid)

    # ── Paramètres ───────────────────────────────────────────
    cur_period = current.get("period_ms", 1000)
    act_period = actual.get("period_ms", 1000)
    if cur_period != act_period:
        diff["period_changed"] = cur_period

    cur_stream = current.get("stream_enabled", False)
    act_stream = actual.get("stream_enabled", False)
    if cur_stream != act_stream:
        diff["stream_changed"] = cur_stream

    # FIX : utiliser des clés valides dans ACQ_MODE
    stream = current.get("stream_enabled", False)
    log    = current.get("log_enabled",    False)
    if stream and log:
        diff["acq_mode"] = "both"
    elif stream:
        diff["acq_mode"] = "stream_only"
    elif log:
        diff["acq_mode"] = "sd_only"
    else:
        diff["acq_mode"] = "no_log_no_stream"

    return diff


# ═════════════════════════════════════════════════════════════
#  Sérialiseurs binaires (partagés)
# ═════════════════════════════════════════════════════════════

def _ser_cond(c: dict) -> bytes:
    """
    Sérialise une Condition_t en 35 octets — miroir exact de
    parse_rule_from_payload() dans commander.c :
        fn_a(1) uid_a(1) window_a(1) param_a(4f) coeff_a(4f)
        arith(1) fn_b(1) uid_b(1) window_b(1) param_b(4f) coeff_b(4f)
        offset(4f) cmp(1) rhs(4f) tolerance(4f)
    """
    return struct.pack(
        "<BBBffBBBBfffBff",
        c.get("fn_a",      1),
        c.get("uid_a",     0),
        c.get("window_a",  1),
        c.get("param_a",   0.0),
        c.get("coeff_a",   1.0),
        c.get("arith",     0),
        c.get("fn_b",      0),
        c.get("uid_b",     0),
        c.get("window_b",  1),
        c.get("param_b",   0.0),
        c.get("coeff_b",   1.0),
        c.get("offset",    0.0),
        c.get("cmp",       0),
        c.get("rhs",       0.0),
        c.get("tolerance", 0.0),
    )


def _ser_trig(t: dict) -> bytes:
    """
    Sérialise un Trigger_t en 14 octets — miroir exact de
    parse_rule_from_payload() dans commander.c :
        type(1)
        LOG/STREAM : n_uids(1) uids[MAX_UIDS](8) pad_action(4)
        ACTION     : n_uids=0(1) uids=0(8) pin(1) code(1) param(2)

    FIX : TRIG_LOG=0, TRIG_STREAM=1, TRIG_ACTION=2
    """
    ttype = t.get("type", TRIG_LOG)
    buf   = struct.pack("B", ttype)

    if ttype in (TRIG_LOG, TRIG_STREAM):
        uids = t.get("uids", [])
        n    = min(len(uids), MAX_UIDS_PER_TRIGGER)
        buf += struct.pack("B", n)
        buf += bytes(uids[:n]) + bytes(MAX_UIDS_PER_TRIGGER - n)
        buf += bytes(4)   # padding action fields
    elif ttype == TRIG_ACTION:
        pin   = t.get("pin_or_servo_id", 1)
        code  = t.get("action_code",     ACT_GPIO_HIGH)
        param = t.get("param",           0)
        buf  += struct.pack("B", 0)
        buf  += bytes(MAX_UIDS_PER_TRIGGER)
        buf  += struct.pack("<BBH", pin, code, param)
    else:
        buf += bytes(13)

    assert len(buf) == 14, f"Trigger mal sérialisé : {len(buf)} != 14"
    return buf


def _uid_from_name(name: str) -> int:
    """'device7' → 7,  'sortie3' → 3"""
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 0


# ═════════════════════════════════════════════════════════════
#  SerialManager
# ═════════════════════════════════════════════════════════════

class SerialManager(QObject): # <--- Hérite maintenant de QObject pour supporter les signaux
    
    # Signal émis chaque fois que des octets bruts arrivent sur l'UART
    raw_data_received = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self._serial: Optional[serial.Serial] = None
        self.port_name: Optional[str] = None
        
        # Timer PyQt pour surveiller l'arrivée de données en tâche de fond (Live Data Stream)
        self._read_timer = QTimer()
        self._read_timer.setInterval(10) # Vérification toutes les 10 ms
        self._read_timer.timeout.connect(self._check_incoming_data)

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @staticmethod
    def list_ports() -> List[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

    def open_port(self, port: str, baudrate: int = 115200,
                  timeout: float = 0.1) -> None: # Optionnel: Réduire le timeout pour ne pas bloquer l'UI
        if self.is_connected:
            self.close()
        self._serial = serial.Serial(port=port, baudrate=baudrate,
                                     timeout=timeout)
        self.port_name = port
        
        # Démarrer l'écoute asynchrone dès que le port s'ouvre
        self._read_timer.start()

    def close(self) -> None:
        self._read_timer.stop() # Arrêter le timer avant de fermer
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self.port_name = None

    def _check_incoming_data(self) -> None:
        """ Méthode appelée toutes les 10ms pour extraire les octets bruts du port """
        
        if not self.is_connected or self._serial is None:
            return
            
        try:
            # On regarde s'il y a des octets disponibles dans le buffer de réception OS
            available = self._serial.in_waiting
            if available > 0:
                raw_bytes = self._serial.read(available)
                if raw_bytes:
                    # On envoie les octets bruts à travers le signal pour le décodeur
                    self.raw_data_received.emit(raw_bytes)
                    
        except Exception as e:
            print(f"[SerialManager] Erreur lecture arrière-plan : {e}")
    # ── Couche trame ──────────────────────────────────────────

    def _build_frame(self, cmd_id: int, payload: bytes = b"") -> bytes:
        """STX | CMD | LEN | PAYLOAD… | ETX"""
        if len(payload) > 255:
            raise ValueError(f"Payload trop long : {len(payload)} > 255")
        return bytes([FRAME_STX, cmd_id, len(payload)]) + payload + bytes([FRAME_ETX])

    def _read_frame(self, timeout: float = 2.0) -> Optional[Tuple[int, bytes]]:
        """
        Lit une trame complète.
        Retourne (cmd_id, payload) ou None si timeout/erreur.
        """
        if not self.is_connected or self._serial is None:
            return None

        deadline = time.time() + timeout
        buffer   = bytearray()

        while time.time() < deadline:
            available = self._serial.in_waiting
            if available:
                buffer.extend(self._serial.read(available))

            if len(buffer) < 4:
                time.sleep(0.005)
                continue

            start = buffer.find(bytes([FRAME_STX]))
            if start == -1:
                buffer.clear()
                continue

            if len(buffer) < start + 3:
                time.sleep(0.005)
                continue

            payload_len  = buffer[start + 2]
            frame_length = 4 + payload_len   # STX+CMD+LEN+PAYLOAD+ETX

            if len(buffer) < start + frame_length:
                time.sleep(0.005)
                continue

            frame = bytes(buffer[start: start + frame_length])

            if frame[-1] != FRAME_ETX:
                buffer = buffer[start + 1:]
                continue

            buffer  = buffer[start + frame_length:]
            cmd_id  = frame[1]
            payload = frame[3:-1]
            return cmd_id, payload

        return None

    def send_frame(self, cmd_id: int, payload: bytes = b"",
                   response_timeout: float = 2.0,
                   ) -> Tuple[bool, Optional[int], Optional[bytes]]:
        """Envoie une trame et attend la réponse."""
        if not self.is_connected or self._serial is None:
            return False, None, None
        frame = self._build_frame(cmd_id, payload)
        self._serial.reset_input_buffer()
        self._serial.write(frame)
        result = self._read_frame(timeout=response_timeout)
        
        if result is None:
            return False, None, None
        return True, result[0], result[1]

    # ── Commandes de base ─────────────────────────────────────

    def send_ping(self) -> Tuple[bool, Optional[int], Optional[bytes]]:
        return self.send_frame(CMD_PING, response_timeout=5.0)

    def stop_acquisition(self) -> Tuple[bool, Optional[int], Optional[bytes]]:
        return self.send_frame(CMD_STOP_ACQ)

    def start_acquisition(self, mode: str = "both",
                          period_ms: int = 1000,
                          ) -> Tuple[bool, Optional[int], Optional[bytes]]:
        # FIX : ACQ_MODE.get() avec fallback explicite sur "both"
        mode_byte = ACQ_MODE.get(mode, ACQ_MODE["both"])
        payload   = struct.pack("<BI", mode_byte, period_ms)
        return self.send_frame(CMD_START_ACQ, payload)

    def save_to_flash(self) -> Tuple[bool, Optional[int], Optional[bytes]]:
        return self.send_frame(CMD_SAVE_TO_FLASH)

    def load_from_flash(self) -> Tuple[bool, Optional[int], Optional[bytes]]:
        return self.send_frame(CMD_LOAD_FROM_FLASH)

    # ── Synchronisation ───────────────────────────────────────

    def sync_from_device(self, actual_config_path: str,
                         timeout: float = 5.0,
                         ) -> Tuple[bool, Optional[dict]]:
        """
        Envoie CMD_SYNC_REQUEST et reçoit le JSON de l'état de la carte.
        Sauvegarde dans actual_config_path.
        Retourne (True, dict) ou (False, None).
        """
        if not self.is_connected:
            return False, None

        self._serial.reset_input_buffer()
        self._serial.write(self._build_frame(CMD_SYNC_REQUEST))

        result = self._read_frame(timeout=timeout)
        print(f"\n-----\n[sync] Résultat de la lecture : {result}\n--------\n")
        if result is None:
            return False, None

        cmd_id, payload = result
        if cmd_id != CMD_SYNC_RESPONSE:
            return False, None

        
        try:
            json_str = payload.decode("utf-8")
            actual   = json.loads(json_str)
        except UnicodeDecodeError as e:
            print(f"[sync] Erreur décodage UTF-8 : {e}")
            return False, None
        except json.JSONDecodeError as e:
            print(f"[sync] JSON invalide : {e} — payload brut : {payload!r}")
            return False, None

        try:
            with open(actual_config_path, "w", encoding="utf-8") as f:
                json.dump(actual, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"[sync] Impossible d'écrire actual_config : {e}")

        return True, actual

    # ── Commandes de configuration ────────────────────────────

    def _send_assign_sensor(self, slot_id: int, model: str, quantity: str,
                             i2c_address: int = 0,
                             ) -> Tuple[bool, Optional[int], Optional[bytes]]:
        """
        Cmd_AssignSensor_t (packed) :
            slot_id(1) | model(1) | quantity(1) | i2c_address(1) | raw[16]
        """
        model_b    = SENSOR_MODEL.get(model, 0)
        quantity_b = PHYSICAL_QUANTITY.get(quantity, 0)
        payload    = struct.pack("BBBB", slot_id, model_b, quantity_b,
                                 i2c_address) + bytes(16)
        return self.send_frame(CMD_ASSIGN_SENSOR, payload, response_timeout=3.0)

    def _send_clear_device(self, uid: int,
                           ) -> Tuple[bool, Optional[int], Optional[bytes]]:
        """CMD_CLEAR_DEVICE payload : uid(1)"""
        return self.send_frame(CMD_CLEAR_DEVICE, bytes([uid]))

    def _send_set_period(self, period_ms: int,
                         ) -> Tuple[bool, Optional[int], Optional[bytes]]:
        """CMD_SET_PERIOD payload : period_ms(4 LE)"""
        return self.send_frame(CMD_SET_PERIOD, struct.pack("<I", period_ms))

    def _send_remove_rule(self, rule_id: int,
                          ) -> Tuple[bool, Optional[int], Optional[bytes]]:
        """CMD_REMOVE_RULE payload : rule_id(1)"""
        return self.send_frame(CMD_REMOVE_RULE, bytes([rule_id]))

    def _send_add_rule(self, rule: dict) -> Tuple[bool, Optional[int], Optional[bytes]]:
        """
        Accepte un rule_dict au format rule_editor.RuleCell.get_rule_dict() :
        {
            "rule_id":    int,
            "priority":   int,           # optionnel, défaut 0
            "enabled":    bool,
            "text":       str,
            "structured": {              # présent si créé via RuleFormDialog
                "conditions": [...],     # ConditionRow.to_dict()
                "actions":    [...],     # ActionRow.to_dict()
            }
        }

        Sérialise en payload binaire EXACT pour parse_rule_from_payload()
        dans commander.c :
            rule_id(1) priority(1) enabled(1) n_conditions(1)
            [condition × n_cond]   35 octets chacune
            pattern_len(1) pattern_text(pattern_len)  ← "c1 AND c2 AND c3"
            n_triggers(1)
            [trigger × n_trig]     14 octets chacun

        Enums (miroir de rule_types.h) :
            Primitive_t   : PRIM_NONE=0, PRIM_CURRENT=1, PRIM_MEAN=2, ...
            Arith_Op_t    : ARITH_NONE=0, ARITH_ADD=1, ...
            Compare_Op_t  : CMP_GT=0, CMP_LT=1, CMP_GTE=2, CMP_LTE=3,
                            CMP_EQ=4, CMP_NEQ=5, CMP_APPROX=6
            Trigger_Type_t: TRIG_LOG=0, TRIG_STREAM=1, TRIG_ACTION=2
        """
        rule_id    = rule.get("rule_id",  1)
        priority   = rule.get("priority", 0)
        enabled    = rule.get("enabled",  True)
        structured = rule.get("structured")

        conditions: List[dict] = []
        triggers:   List[dict] = []

        if structured:
            # ── Conditions depuis ConditionRow.to_dict() ───────
            for cond in structured.get("conditions", []):
                prim_str = cond.get("primitive") or "device"
                fn_a     = PRIM_MAP.get(prim_str, 1)
                uid_a    = _uid_from_name(cond.get("device", "device0"))
                window_a = int(cond.get("window") or 1)
                op_str   = cond.get("operator", ">")
                cmp_val  = CMP_MAP.get(op_str, 0)
                rhs      = float(cond.get("rhs") or 0.0)
                # FIX : tolerance non nulle pour ~=
                tolerance = float(cond.get("tolerance") or 0.0)

                conditions.append({
                    "fn_a":      fn_a,
                    "uid_a":     uid_a,
                    "window_a":  window_a,
                    "param_a":   0.0,
                    "coeff_a":   1.0,
                    "arith":     0,
                    "fn_b":      0,
                    "uid_b":     0,
                    "window_b":  1,
                    "param_b":   0.0,
                    "coeff_b":   1.0,
                    "offset":    0.0,
                    "cmp":       cmp_val,
                    "rhs":       rhs,
                    "tolerance": tolerance,
                })

            # ── Triggers depuis ActionRow.to_dict() ────────────
            all_uids = [
                _uid_from_name(c.get("device", "device0"))
                for c in structured.get("conditions", [])
            ]

            for action in structured.get("actions", []):
                
                act   = action.get("action", "")
                out   = action.get("output", "")
                pin   = _uid_from_name(out) if out else 0
                param = int(action.get("param") or 0)

                if act == "log":
                    triggers.append({
                        "type": TRIG_LOG,
                        "uids": all_uids,
                    })
                elif act == "stream":
                    triggers.append({
                        "type": TRIG_STREAM,
                        "uids": all_uids,
                    })
                elif act == "on":
                    triggers.append({
                        "type":            TRIG_ACTION,
                        "pin_or_servo_id": pin,
                        "action_code":     ACT_GPIO_HIGH,
                        "param":           0,
                    })
                elif act == "off":
                    triggers.append({
                        "type":            TRIG_ACTION,
                        "pin_or_servo_id": pin,
                        "action_code":     ACT_GPIO_LOW,
                        "param":           0,
                    })
                elif act == "toggle":
                    triggers.append({
                        "type":            TRIG_ACTION,
                        "pin_or_servo_id": pin,
                        "action_code":     ACT_GPIO_TOGGLE,
                        "param":           0,
                    })
                elif act in ("pwm", "rotation", "pulse"):
                    triggers.append({
                        "type":            TRIG_ACTION,
                        "pin_or_servo_id": pin,
                        "action_code":     ACT_GPIO_HIGH,
                        "param":           param,
                    })

        else:
            # ── Parsing du texte brut ──────────────────────────
            text  = rule.get("text", "")
            lines = text.strip().split("\n")
            body  = " ".join(lines[1:]).strip() if len(lines) >= 2 else ""

            if "=>" in body:
                cond_part, act_part = body.split("=>", 1)

                for ct in re.split(r"\s*[&|]\s*", cond_part.strip()):
                    ct = ct.strip()
                    if not ct:
                        continue
                    m = re.search(r"(>=|<=|==|!=|~=|>|<)", ct)
                    if not m:
                        continue
                    op    = m.group(1)
                    left  = ct[:m.start()].strip()
                    right = ct[m.end():].strip()
                    try:
                        rhs = float(right)
                    except ValueError:
                        continue

                    mf = re.match(
                        r"([a-z_]+)\s*\(\s*(device\d+)\s*(?:,\s*(\d+))?\s*\)", left
                    )
                    md = re.match(r"device(\d+)", left)

                    if mf:
                        fn_a     = PRIM_MAP.get(mf.group(1), 1)
                        uid_a    = _uid_from_name(mf.group(2))
                        window_a = int(mf.group(3)) if mf.group(3) else 1
                    elif md:
                        fn_a, uid_a, window_a = 1, int(md.group(1)), 1
                    else:
                        continue

                    conditions.append({
                        "fn_a":      fn_a,
                        "uid_a":     uid_a,
                        "window_a":  window_a,
                        "param_a":   0.0,
                        "coeff_a":   1.0,
                        "arith":     0,
                        "fn_b":      0,
                        "uid_b":     0,
                        "window_b":  1,
                        "param_b":   0.0,
                        "coeff_b":   1.0,
                        "offset":    0.0,
                        "cmp":       CMP_MAP.get(op, 0),
                        "rhs":       rhs,
                        "tolerance": 0.0,
                    })

                all_uids = [c["uid_a"] for c in conditions]

                for at in re.split(r"\s*&\s*", act_part.strip()):
                    at = at.strip()
                    if not at:
                        continue
                    if at.lower() == "log":
                        triggers.append({"type": TRIG_LOG, "uids": all_uids})
                    elif at.lower() == "stream":
                        triggers.append({"type": TRIG_STREAM, "uids": all_uids})
                    else:
                        m_on  = re.match(r"on\s*\(\s*(sortie|servo)(\d+)\s*\)",     at, re.I)
                        m_off = re.match(r"off\s*\(\s*(sortie|servo)(\d+)\s*\)",    at, re.I)
                        m_tog = re.match(r"toggle\s*\(\s*(sortie|servo)(\d+)\s*\)", at, re.I)
                        m_pwm = re.match(
                            r"(?:pwm|rotation|pulse)\s*\(\s*(?:sortie|servo)(\d+)"
                            r"\s*,\s*(\d+)\s*\)", at, re.I
                        )
                        if m_on:
                            triggers.append({
                                "type": TRIG_ACTION,
                                "pin_or_servo_id": int(m_on.group(2)),
                                "action_code": ACT_GPIO_HIGH, "param": 0,
                            })
                        elif m_off:
                            triggers.append({
                                "type": TRIG_ACTION,
                                "pin_or_servo_id": int(m_off.group(2)),
                                "action_code": ACT_GPIO_LOW, "param": 0,
                            })
                        elif m_tog:
                            triggers.append({
                                "type": TRIG_ACTION,
                                "pin_or_servo_id": int(m_tog.group(2)),
                                "action_code": ACT_GPIO_TOGGLE, "param": 0,
                            })
                        elif m_pwm:
                            triggers.append({
                                "type": TRIG_ACTION,
                                "pin_or_servo_id": int(m_pwm.group(1)),
                                "action_code": ACT_GPIO_HIGH,
                                "param": int(m_pwm.group(2)),
                            })

            # Fallback : trigger LOG vide si aucun trigger parsé
            if not triggers:
                triggers = [{"type": TRIG_LOG, "uids": []}]

        # ── Pattern "c1 AND c2 AND ..." ────────────────────────
        #  : syntaxe exacte reconnue par Pattern_Compile() côté STM32
        n_cond = min(len(conditions), 8)
        n_trig = min(len(triggers),   8)

        if n_cond == 0:
            pattern = b"c1"   # sera rejeté par la carte (PATTERN_ERR_UNKNOWN_COND)
        else:
            pattern = " AND ".join(f"c{i+1}" for i in range(n_cond)).encode("utf-8")

        # ── Construire le payload ──────────────────────────────
        payload  = struct.pack("BBBB", rule_id, priority, 1 if enabled else 0, n_cond)
        for i in range(n_cond):
            payload += _ser_cond(conditions[i])
        pattern  = pattern[:255]
        payload += struct.pack("B", len(pattern)) + pattern
        payload += struct.pack("B", n_trig)
        for i in range(n_trig):
            print(f"serialized trigger {i+1}: {triggers[i]} → {_ser_trig(triggers[i])}")
            payload += _ser_trig(triggers[i])
            

        if len(payload) > 255:
            raise ValueError(
                f"Payload règle trop long : {len(payload)} octets (max 255). "
                f"Réduire le nombre de conditions/triggers."
            )

        return self.send_frame(CMD_ADD_RULE, payload, response_timeout=5.0)

    # ── Sync + Diff + Patch ───────────────────────────────────

    def sync_and_patch(self, current_config_path: str,
                       actual_config_path: str,
                       progress_callback=None,
                       ) -> Tuple[bool, str]:
        """
        Flux complet :
            1. Synchronise avec la carte → actual_config.json
            2. Calcule le diff (current vs actual)
            3. Envoie seulement les différences, ACK par ACK
        """
        if not self.is_connected:
            return False, "Port COM non connecté."

        try:
            with open(current_config_path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception as e:
            return False, f"Erreur lecture current_config : {e}"

        def _progress(step, total, msg):
            if progress_callback:
                progress_callback(step, total, msg)

        _progress(0, 1, "Synchronisation avec la carte…")

        ok, actual = self.sync_from_device(actual_config_path, timeout=5.0)
        if not ok:
            return False, "Impossible de synchroniser avec la carte."

        diff = compute_diff(current, actual)
        ops  = self._build_ops_from_diff(current, diff)
        return self._apply_ops(ops, progress_callback)

    def _build_ops_from_diff(self, current: dict,
                             diff: dict) -> List[Tuple[str, object]]:
        ops: List[Tuple[str, object]] = []

        for uid in diff["sensors_to_remove"]:
            ops.append((
                f"Supprimer device uid={uid}",
                lambda u=uid: self._send_clear_device(u),
            ))

        for dev in diff["sensors_to_add"]:
            addr = _parse_i2c(dev.get("i2c_address", 0))
            ops.append((
                f"Ajouter {dev['model']}/{dev['quantity']} → slot {dev['slot_id']}",
                lambda d=dev, a=addr: self._send_assign_sensor(
                    d["slot_id"], d["model"], d["quantity"], a),
            ))

        for rid in diff["rules_to_remove"]:
            ops.append((
                f"Supprimer règle {rid}",
                lambda r=rid: self._send_remove_rule(r),
            ))

        for rule in diff["rules_to_add"]:
            print(f"DEBUG: Rule to add: {rule}")
            ops.append((
                f"Ajouter règle {rule['rule_id']}",
                lambda r=rule: self._send_add_rule(r),
            ))

        if diff["period_changed"] is not None:
            p = diff["period_changed"]
            ops.append((
                f"Période → {p} ms",
                lambda v=p: self._send_set_period(v),
            ))

        if diff["stream_changed"] is not None or diff["period_changed"] is not None:
            mode      = diff["acq_mode"]
            period_ms = current.get("period_ms", 1000)
            ops.append((
                f"Redémarrer acquisition (mode={mode})",
                lambda m=mode, p=period_ms: self.start_acquisition(m, p),
            ))

        return ops

    def _apply_ops(self, ops: List[Tuple[str, object]],
                   progress_callback=None) -> Tuple[bool, str]:
        total = len(ops)
        if total == 0:
            return True, "Carte déjà à jour — aucune différence détectée."

        for step, (description, cmd_fn) in enumerate(ops, start=1):
            if progress_callback:
                progress_callback(step, total, description)

            ok, cmd_id, data = cmd_fn()

            if not ok:
                return False, f"Timeout à l'étape {step}/{total} : {description}"

            if cmd_id == CMD_NACK:
                # FIX : data peut être None
                err = data[1] if (data is not None and len(data) >= 2) else 0xFF
                return False, (
                    f"NACK 0x{err:02X} à l'étape {step}/{total} : {description}"
                )

        return True, f"{total} opération(s) appliquée(s) avec succès."

    def patch_from_files(self, current_config_path: str,
                         actual_config_path: str,
                         progress_callback=None) -> Tuple[bool, str]:
        """
        Applique le patch à partir des fichiers sur disque sans re-synchroniser.
        Utile pour le bouton "Lancer l'envoi" qui utilise un actual_config
        déjà sauvegardé.
        """
        try:
            with open(current_config_path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception as e:
            return False, f"Erreur lecture current_config : {e}"

        try:
            with open(actual_config_path, "r", encoding="utf-8") as f:
                actual = json.load(f)
        except Exception as e:
            return False, f"Erreur lecture actual_config : {e}"

        diff = compute_diff(current, actual)
        ops  = self._build_ops_from_diff(current, diff)
        return self._apply_ops(ops, progress_callback)


# ═════════════════════════════════════════════════════════════
#  UI — ComPortDialog
# ═════════════════════════════════════════════════════════════

from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QDialogButtonBox, QMessageBox,
    QPlainTextEdit, QProgressBar,
)
from utils.styles import STYLE_BTN, STYLE_BTN_PRIMARY, STYLE_BTN_SECONDARY

icons_dir = os.path.join(os.path.dirname(__file__), "icons")


class ComPortDialog(QDialog):
    def __init__(self, manager: SerialManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Connexion COM")
        self.setWindowIcon(QIcon(os.path.join(icons_dir, "com_port.png")))
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Sélectionnez le port COM et vérifiez la connexion :"))

        self.port_combo   = QComboBox()
        self.status_label = QLabel("Aucun port sélectionné.")
        self.status_label.setStyleSheet("color:#374151;font-size:12px;")
        self._populate_ports()
        layout.addWidget(self.port_combo)

        row = QHBoxLayout()
        btn = QPushButton("Rafraîchir")
    
        btn.clicked.connect(self._populate_ports)
        row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.status_label)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = btns.button(QDialogButtonBox.Ok)
        ok_btn.setText("Connecter")
        
        btns.button(QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_connect)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _populate_ports(self) -> None:
        self.port_combo.clear()
        ports = SerialManager.list_ports()
        if not ports:
            self.port_combo.addItem("Aucun port COM détecté")
            self.port_combo.setEnabled(False)
            self.status_label.setText("Aucun port COM trouvé.")
            return
        self.port_combo.setEnabled(True)
        for p in ports:
            self.port_combo.addItem(p)
        self.status_label.setText(f"{len(ports)} port(s) détecté(s).")

    def _on_connect(self) -> None:
        if not self.port_combo.isEnabled():
            QMessageBox.warning(self, "Port COM", "Sélectionnez un port valide.")
            return
        port_name = self.port_combo.currentText()
        try:
            self.manager.open_port(port_name)
            self.status_label.setText(f"Connexion à {port_name}…")
            self.repaint()
            ok, cmd_id, _ = self.manager.send_ping()
            if ok and cmd_id in (CMD_ACK, CMD_PING, CMD_STATUS_RESPONSE):
                self.status_label.setText(f"Connexion établie sur {port_name}.")
                QMessageBox.information(self, "Connexion établie",
                                        f"Port {port_name} connecté.")
                self.accept()
                return
            self.manager.close()
            QMessageBox.critical(self, "Échec", "Aucune réponse ACK reçue.")
            self.status_label.setText("Aucune réponse reçue.")
        except Exception as e:
            self.manager.close()
            QMessageBox.critical(self, "Erreur COM", str(e))


# ═════════════════════════════════════════════════════════════
#  UI — ConfigSyncDialog
# ═════════════════════════════════════════════════════════════

class ConfigSyncDialog(QDialog):
    def __init__(self, manager: SerialManager,
                 current_config_path: str,
                 actual_config_path: str,
                 parent=None):
        super().__init__(parent)
        self.manager             = manager
        self.current_config_path = current_config_path
        self.actual_config_path  = actual_config_path
        self.setWindowTitle("Synchronisation de configuration")
        self.setWindowIcon(QIcon(os.path.join(icons_dir, "upload.png")))
        self.setMinimumSize(660, 480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QLabel(
            "En cas de coupure, relancez : seules les différences restantes "
            "seront envoyées."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            "background:#F8FAFC;color:#111;border-radius:1px;"
            "font-family:Consolas,'Courier New',monospace;font-size:11px;"
        )
        layout.addWidget(self.log_view, 1)

        row = QHBoxLayout()
        self.sync_btn = QPushButton("Lancer l'envoi")
        #self.sync_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        self.sync_btn.clicked.connect(self._start)
        row.addWidget(self.sync_btn)
        close_btn = QPushButton("Fermer")
        #close_btn.setStyleSheet(STYLE_BTN)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        row.addStretch()
        layout.addLayout(row)

    def _log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _start(self) -> None:
        if not self.manager.is_connected:
            QMessageBox.warning(self, "Connexion requise",
                                "Connectez un port COM d'abord.")
            return

        self.sync_btn.setEnabled(False)
        self.progress.setValue(0)
        self.log_view.clear()
        self._log("Démarrage de la synchronisation…")
        QApplication.processEvents()

        def on_progress(step: int, total: int, msg: str) -> None:
            if total > 0:
                self.progress.setMaximum(total)
                self.progress.setValue(step)
            self._log(f"  [{step}/{total}] {msg}")
            QApplication.processEvents()

        ok, message = self.manager.patch_from_files(
            self.current_config_path,
            self.actual_config_path,
            progress_callback=on_progress,
        )

        if ok:
            self.progress.setValue(self.progress.maximum())
            self._log(f"\n✓ {message}")
            QMessageBox.information(self, "Succès", message)
        else:
            self._log(f"\n✗ {message}")
            QMessageBox.critical(self, "Échec", message)

        self.sync_btn.setEnabled(True)