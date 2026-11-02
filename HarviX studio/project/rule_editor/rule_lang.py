"""
rule_lang.py — Définition du langage de règles

Syntaxe d'une règle :
    nom_de_la_regle:
    condition1 & condition2 | condition3 => action1 & action2

Conditions :
    device1 > 30
    slope(device2, 8) >= 1.5
    2.5 * device1 - device2 > 10
    max(device1, 10) < device2

Actions :
    on(sortie1)
    off(sortie2)
    rotation(servo1, 90)
    log
    stream

Opérateurs logiques : & (AND), | (OR), ! (NOT)
Opérateurs de comparaison : >  <  >=  <=  ==  !=  ~= (near)
Séparateur condition/action : =>
"""

# ── Primitives (fonctions sur les capteurs) ──────
PRIMITIVES = {
    "current":       {"args": 1, "label": "valeur courante",    "hint": "current(device)"},
    "mean":          {"args": 2, "label": "moyenne",            "hint": "mean(device, window)"},
    "slope":         {"args": 2, "label": "pente",              "hint": "slope(device, window)"},
    "stddev":        {"args": 2, "label": "écart-type",         "hint": "stddev(device, window)"},
    "min":           {"args": 2, "label": "minimum",            "hint": "min(device, window)"},
    "max":           {"args": 2, "label": "maximum",            "hint": "max(device, window)"},
    "noise_level":   {"args": 2, "label": "niveau de bruit",    "hint": "noise_level(device, window)"},
    "deriv_time":    {"args": 2, "label": "dérivée temporelle", "hint": "deriv_time(device, window)"},
    "delta_last":    {"args": 1, "label": "delta depuis trigger","hint": "delta_last(device)"},
    "near_multiple": {"args": 2, "label": "proche d'un multiple","hint": "near_multiple(device, base)"},
}

# ── Actions (fonctions sur les sorties) ──────────
ACTIONS = {
    "on":       {"args": 1, "label": "activer",         "hint": "on(sortie)"},
    "off":      {"args": 1, "label": "désactiver",      "hint": "off(sortie)"},
    "toggle":   {"args": 1, "label": "basculer",        "hint": "toggle(sortie)"},
    "rotation": {"args": 2, "label": "rotation servo",  "hint": "rotation(servo, angle)"},
    "pwm":      {"args": 2, "label": "valeur PWM",      "hint": "pwm(servo, valeur)"},
    "pulse":    {"args": 2, "label": "impulsion",        "hint": "pulse(sortie, durée_ms)"},
    "log":      {"args": 0, "label": "enregistrer",      "hint": "log"},
    "stream":   {"args": 0, "label": "streamer",         "hint": "stream"},
}

# ── Opérateurs ───────────────────────────────────
COMPARE_OPS = [">", "<", ">=", "<=", "==", "!=", "~="]
LOGIC_OPS   = ["&", "|", "!"]
ARROW       = "=>"

# ── Mots-clés réservés ───────────────────────────
KEYWORDS = set(PRIMITIVES.keys()) | set(ACTIONS.keys()) | {"log", "stream"}

# ── Couleurs pour la coloration syntaxique ───────
TOKEN_COLORS = {
    "device":    "#2563EB",   # bleu
    "output":    "#DC2626",   # rouge
    "primitive": "#7C3AED",   # violet
    "action":    "#EA580C",   # orange
    "operator":  "#D97706",   # ambre
    "logic":     "#0891B2",   # cyan
    "number":    "#059669",   # vert
    "arrow":     "#DC2626",   # rouge
    "name":      "#374151",   # gris foncé
    "comment":   "#9CA3AF",   # gris
    "error":     "#EF4444",   # rouge vif
    "paren":     "#6B7280",   # gris
}


def build_completions(devices: list, outputs: list) -> list[dict]:
    """
    Construit la liste d'autocomplétion à partir de la config courante.

    Retourne une liste de dicts :
        {"text": "device1", "type": "device", "detail": "LM75 (temperature)"}
    """
    completions = []

    # Devices
    for d in devices:
        dev = d["device"]
        completions.append({
            "text":   f"device{dev.uid}",
            "type":   "device",
            "detail": dev.display_name(),
            "color":  TOKEN_COLORS["device"],
        })

    # Outputs
    for o in outputs:
        name = f"sortie{o.output_id}" if o.type == "digital" else f"servo{o.output_id}"
        completions.append({
            "text":   name,
            "type":   "output",
            "detail": o.label,
            "color":  TOKEN_COLORS["output"],
        })

    # Primitives
    for name, info in PRIMITIVES.items():
        completions.append({
            "text":   name,
            "type":   "primitive",
            "detail": info["hint"],
            "color":  TOKEN_COLORS["primitive"],
        })

    # Actions
    for name, info in ACTIONS.items():
        completions.append({
            "text":   name,
            "type":   "action",
            "detail": info["hint"],
            "color":  TOKEN_COLORS["action"],
        })

    # Operators
    for op in COMPARE_OPS:
        completions.append({
            "text":   op,
            "type":   "operator",
            "detail": "opérateur de comparaison",
            "color":  TOKEN_COLORS["operator"],
        })

    return completions


def validate_rule_text(text: str, device_names: set, output_names: set) -> list[dict]:
    """
    Valide le texte d'une règle et retourne les erreurs trouvées.

    Retourne une liste de dicts :
        {"line": 0, "col": 5, "message": "device inconnu: device99", "severity": "error"}
    """
    errors = []
    lines = text.strip().split("\n")

    if len(lines) < 2:
        errors.append({"line": 0, "col": 0,
                        "message": "Une règle doit avoir un nom (ligne 1) et un corps (ligne 2)",
                        "severity": "error"})
        return errors

    # Ligne 1 : nom
    name_line = lines[0].strip()
    if not name_line.endswith(":"):
        errors.append({"line": 0, "col": len(name_line),
                        "message": "Le nom de la règle doit se terminer par ':'",
                        "severity": "error"})

    # Ligne 2+ : corps
    body = " ".join(lines[1:]).strip()

    if "=>" not in body:
        errors.append({"line": 1, "col": 0,
                        "message": "Il manque '=>' pour séparer conditions et actions",
                        "severity": "error"})
        return errors

    parts = body.split("=>", 1)
    cond_part = parts[0].strip()
    action_part = parts[1].strip()

    if not cond_part:
        errors.append({"line": 1, "col": 0,
                        "message": "Aucune condition définie avant '=>'",
                        "severity": "error"})

    if not action_part:
        errors.append({"line": 1, "col": len(body),
                        "message": "Aucune action définie après '=>'",
                        "severity": "error"})

    # Vérifier les identifiants dans la partie condition
    import re
    identifiers = re.findall(r'(?:device|sortie|servo)\d+', body)
    for ident in identifiers:
        if ident.startswith("device") and ident not in device_names:
            col = body.find(ident)
            errors.append({"line": 1, "col": col,
                            "message": f"Inconnu: {ident}",
                            "severity": "error"})
        elif (ident.startswith("sortie") or ident.startswith("servo")) and ident not in output_names:
            col = body.find(ident)
            errors.append({"line": 1, "col": col,
                            "message": f"Sortie inactive ou inconnue: {ident}",
                            "severity": "warning"})

    # Vérifier les fonctions
    func_calls = re.findall(r'([a-z_]+)\s*\(', body)
    known = set(PRIMITIVES.keys()) | set(ACTIONS.keys())
    for func in func_calls:
        if func not in known:
            col = body.find(func)
            errors.append({"line": 1, "col": col,
                            "message": f"Fonction inconnue: {func}",
                            "severity": "error"})

    # Parenthèses équilibrées
    depth = 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            errors.append({"line": 1, "col": i,
                            "message": "Parenthèse fermante sans ouvrante",
                            "severity": "error"})
            break
    if depth > 0:
        errors.append({"line": 1, "col": len(body),
                        "message": f"{depth} parenthèse(s) non fermée(s)",
                        "severity": "error"})

    return errors
