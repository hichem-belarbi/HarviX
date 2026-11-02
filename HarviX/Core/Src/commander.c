#include "commander.h"
#include "reader.h"
#include "rules_store.h"
#include "rules_engine.h"
#include "history_buffer.h"
#include "pattern_parser.h"
#include "sensor_types.h"
#include "rule_types.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>
#include <stdio.h>

/* ============================================================
 *  Queues externes
 * ============================================================ */
extern osMessageQueueId_t queue_cmds;     /* ← reception uart / UI   */
extern osMessageQueueId_t queue_tx;       /* → expédition uart       */
extern osMessageQueueId_t queue_log;      /* → logger                */

/* ============================================================
 *  État interne
 * ============================================================ */
static osThreadId_t  g_task;
static bool          g_authenticated = true;   /* TODO: false quand auth activée */
static bool          g_acq_running   = false;
static Acq_Mode_t   g_acq_mode      = ACQ_MODE_BOTH;

/* ============================================================
 *  Prototypes internes
 * ============================================================ */
static void commander_task_fn(void *arg);
static void dispatch_command(const Command_t *cmd);

/* Handlers par famille */
static void handle_sync_request(const Command_t *cmd);
static void handle_ping(const Command_t *cmd);
static void handle_get_status(const Command_t *cmd);

static void handle_assign_sensor(const Command_t *cmd);
static void handle_clear_device(const Command_t *cmd);
static void handle_clear_slot(const Command_t *cmd);
static void handle_clear_all_sensors(const Command_t *cmd);
static void handle_get_slot_info(const Command_t *cmd);

static void handle_add_rule(const Command_t *cmd);
static void handle_remove_rule(const Command_t *cmd);
static void handle_update_rule(const Command_t *cmd);
static void handle_enable_rule(const Command_t *cmd);
static void handle_clear_all_rules(const Command_t *cmd);

static void handle_start_acq(const Command_t *cmd);
static void handle_stop_acq(const Command_t *cmd);
static void handle_set_period(const Command_t *cmd);

static void handle_save_to_flash(const Command_t *cmd);
static void handle_load_from_flash(const Command_t *cmd);
static void handle_erase_flash(const Command_t *cmd);

/* Helpers de réponse */
static void send_ack(uint8_t original_cmd, const uint8_t *data, uint8_t data_len);
static void send_nack(uint8_t original_cmd, Error_Code_t error);
static void send_response(uint8_t cmd_id, const uint8_t *payload, uint16_t len);
static void log_event(const char *msg);

/* Helpers de parsing */
static int parse_rule_from_payload(const uint8_t *payload, uint16_t len, Rule_t *out);

/* ============================================================
 *  Init et démarrage
 * ============================================================ */

void Commander_Init(void)
{
    g_authenticated = true;    /* auth désactivée pour le moment */
    g_acq_running   = false;
}

void Commander_StartTask(void)
{
    const osThreadAttr_t attr = {
        .name       = "commander",
        .stack_size = 2048,
        .priority   = osPriorityAboveNormal,
    };
    g_task = osThreadNew(commander_task_fn, NULL, &attr);
}
void Commander_Main(void)
{
	Commander_Init();
	Commander_StartTask();
}
/* ============================================================
 *  Tâche principale — boucle sur queue_cmds
 * ============================================================ */

static void commander_task_fn(void *arg)
{
    (void)arg;
    Command_t cmd;

    log_event("Commander started");

    for (;;) {
        if (osMessageQueueGet(queue_cmds, &cmd, NULL, osWaitForever) == osOK) {
            dispatch_command(&cmd);
        }
    }
}

/* ============================================================
 *  Dispatch — aiguillage vers le bon handler
 * ============================================================ */

static void dispatch_command(const Command_t *cmd)
{
    /* Commandes toujours autorisées (même sans auth) */
    switch (cmd->cmd_id) {
        case CMD_PING:          handle_ping(cmd);         return;
        case CMD_LOGIN:         /* TODO: handle_login */  return;
        case CMD_SYNC_REQUEST:  handle_sync_request(cmd); return;
    }

    /* Vérification authentification */
    if (!g_authenticated) {
        send_nack(cmd->cmd_id, ERR_NOT_AUTHENTICATED);
        return;
    }

    /* Dispatch principal */
    switch (cmd->cmd_id) {
        /* Système */
        case CMD_GET_STATUS:        handle_get_status(cmd);        break;
        case CMD_LOGOUT:            g_authenticated = false;
                                    send_ack(CMD_LOGOUT, NULL, 0); break;

        /* Capteurs */
        case CMD_ASSIGN_SENSOR:     handle_assign_sensor(cmd);     break;
        case CMD_CLEAR_DEVICE:      handle_clear_device(cmd);      break;
        case CMD_CLEAR_SLOT:        handle_clear_slot(cmd);        break;
        case CMD_CLEAR_ALL_SENSORS: handle_clear_all_sensors(cmd); break;
        case CMD_GET_SLOT_INFO:     handle_get_slot_info(cmd);     break;

        /* Règles */
        case CMD_ADD_RULE:          handle_add_rule(cmd);          break;
        case CMD_REMOVE_RULE:       handle_remove_rule(cmd);       break;
        case CMD_UPDATE_RULE:       handle_update_rule(cmd);       break;
        case CMD_ENABLE_RULE:       handle_enable_rule(cmd);       break;
        case CMD_CLEAR_ALL_RULES:   handle_clear_all_rules(cmd);   break;

        /* Acquisition */
        case CMD_START_ACQ:         handle_start_acq(cmd);         break;
        case CMD_STOP_ACQ:          handle_stop_acq(cmd);          break;
        case CMD_SET_PERIOD:        handle_set_period(cmd);        break;

        /* Flash */
        case CMD_SAVE_TO_FLASH:     handle_save_to_flash(cmd);     break;
        case CMD_LOAD_FROM_FLASH:   handle_load_from_flash(cmd);   break;
        case CMD_ERASE_FLASH:       handle_erase_flash(cmd);       break;

        default:
            send_nack(cmd->cmd_id, ERR_UNKNOWN_CMD);
            break;
    }
}

/* ============================================================
 *  Handlers — Système
 * ============================================================ */

static void handle_ping(const Command_t *cmd)
{
    send_ack(CMD_PING, NULL, 0);
}

static void handle_get_status(const Command_t *cmd)
{
    uint8_t resp[16];
    uint8_t pos = 0;

    /* uptime en secondes */
    uint32_t uptime = osKernelGetTickCount() / 1000;
    memcpy(&resp[pos], &uptime, 4);  pos += 4;

    /* état acquisition */
    resp[pos++] = g_acq_running ? 1 : 0;
    resp[pos++] = (uint8_t)g_acq_mode;

    /* nombre de règles actives */
    resp[pos++] = (uint8_t)(RulesStore_GetVersion() & 0xFF);

    send_response(CMD_STATUS_RESPONSE, resp, pos);
}

static void handle_sync_request(const Command_t *cmd)
{
    /* Construit un JSON de l'état de la carte.
     *
     * Format attendu par SerialManager.sync_from_device() Python :
     * {
     *   "assignments": [
     *     { "slot_id": N, "type": "I2C",
     *       "devices": [
     *         { "uid": U, "model": "BMP280", "quantity": "temperature",
     *           "i2c_address": "0x76" }
     *       ]
     *     }
     *   ],
     *   "rules": [ { "rule_id": R, "enabled": true, "text": "" } ],
     *   "period_ms": 1000,
     *   "stream_enabled": true,
     *   "log_enabled": false
     * }
     */

    static const char * const MODEL_NAMES[] = {
        "NONE","BMP280","AHT20","BH1750","INA219",
        "LM75","NTC","ACS712","DHT11","DHT22","DS18B20"
    };
    static const char * const QTY_NAMES[] = {
        "none","temperature","pressure","humidity","voltage",
        "light_lux","bus_voltage","shunt_voltage","current","power","count"
    };
    static const char * const BUS_NAMES[] = {
        "UNKNOWN","SPI","I2C","ADC","Digital","UART"
    };

    char buf[MAX_CMD_PAYLOAD];
    int  pos = 0;

#define J(...) do { pos += snprintf(&buf[pos], sizeof(buf)-pos, __VA_ARGS__); } while(0)

    J("{\"assignments\":[");

    bool first_slot = true;
    for (uint8_t s = 1; s <= NB_SLOTS && pos < (int)sizeof(buf) - 30; ++s) {
        Slot_t info;
        if (Reader_GetSlotInfo(s, &info) != READER_OK || info.device_count == 0) continue;

        if (!first_slot) J(",");
        first_slot = false;

        const char *bus = (info.bus_type < 6) ? BUS_NAMES[info.bus_type] : "UNKNOWN";
        J("{\"slot_id\":%u,\"type\":\"%s\",\"devices\":[", info.slot_id, bus);

        for (uint8_t d = 0; d < info.device_count && pos < (int)sizeof(buf) - 60; ++d) {
            const Device_t *dev = &info.devices[d];
            if (d > 0) J(",");
            const char *model = (dev->model < 11) ? MODEL_NAMES[dev->model] : "NONE";
            const char *qty   = (dev->quantity < 11) ? QTY_NAMES[dev->quantity] : "none";
            if (info.bus_type == BUS_I2C) {
                J("{\"uid\":%u,\"model\":\"%s\",\"quantity\":\"%s\","
                  "\"i2c_address\":\"0x%02X\"}", dev->uid, model, qty, dev->i2c_address);
            } else {
                J("{\"uid\":%u,\"model\":\"%s\",\"quantity\":\"%s\"}", dev->uid, model, qty);
            }
        }
        J("]}");
    }

    J("],\"rules\":[");
    Rules_Snapshot_t snap;
    RulesStore_GetSnapshot(&snap);
    for (uint8_t r = 0; r < snap.count && pos < (int)sizeof(buf) - 30; ++r) {
        if (r > 0) J(",");
        J("{\"rule_id\":%u,\"enabled\":%s,\"text\":\"\"}",
          snap.rules[r].rule_id, snap.rules[r].enabled ? "true" : "false");
    }

    uint32_t period_ms = Reader_GetPeriod();
    J("],\"period_ms\":%lu,\"stream_enabled\":%s,\"log_enabled\":false}",
      (unsigned long)period_ms, g_acq_running ? "true" : "false");

#undef J

    buf[sizeof(buf) - 1] = '\0';
    send_response(CMD_SYNC_RESPONSE, (uint8_t *)buf, (uint16_t)strlen(buf));
}

/* ============================================================
 *  Handlers — Capteurs
 * ============================================================ */

static void handle_assign_sensor(const Command_t *cmd)
{
    if (cmd->payload_len < sizeof(Cmd_AssignSensor_t)) {
        send_nack(CMD_ASSIGN_SENSOR, ERR_BAD_PAYLOAD);
        return;
    }

    const Cmd_AssignSensor_t *p = &cmd->payload.assign_sensor;

    Sensor_Params_t params;
    params.i2c_address = p->i2c_address;
    memcpy(params.raw, p->raw, sizeof(params.raw));

    uint8_t uid = 0;
    int rc = Reader_AssignSensor(p->slot_id,
                                 (Sensor_Model_t)p->model,
                                 (Physical_Quantity_t)p->quantity,
                                 &params,
                                 &uid);

    if (rc == READER_OK) {
        send_ack(CMD_ASSIGN_SENSOR, &uid, 1);
        log_event("Sensor assigned");
    } else {
        Error_Code_t err;
        switch (rc) {
            case READER_ERR_NO_SLOT:    err = ERR_SLOT_NOT_FOUND;  break;
            case READER_ERR_SLOT_FULL:  err = ERR_SLOT_FULL;       break;
            case READER_ERR_INCOMPAT:   err = ERR_BUS_INCOMPATIBLE; break;
            case READER_ERR_INIT_FAIL:  err = ERR_SENSOR_INIT_FAIL; break;
            default:                    err = ERR_BAD_PAYLOAD;      break;
        }
        send_nack(CMD_ASSIGN_SENSOR, err);
    }
}

static void handle_clear_device(const Command_t *cmd)
{
    if (cmd->payload_len < 1) {
        send_nack(CMD_CLEAR_DEVICE, ERR_BAD_PAYLOAD);
        return;
    }

    uint8_t uid = cmd->payload.clear_device.uid;
    int rc = Reader_ClearDevice(uid);

    if (rc == READER_OK) {
        send_ack(CMD_CLEAR_DEVICE, NULL, 0);
    } else {
        send_nack(CMD_CLEAR_DEVICE, ERR_DEVICE_NOT_FOUND);
    }
}

static void handle_clear_slot(const Command_t *cmd)
{
    if (cmd->payload_len < 1) {
        send_nack(CMD_CLEAR_SLOT, ERR_BAD_PAYLOAD);
        return;
    }

    int rc = Reader_ClearSlot(cmd->payload.clear_slot.slot_id);
    if (rc == READER_OK) {
        send_ack(CMD_CLEAR_SLOT, NULL, 0);
    } else {
        send_nack(CMD_CLEAR_SLOT, ERR_SLOT_NOT_FOUND);
    }
}

static void handle_clear_all_sensors(const Command_t *cmd)
{
    Reader_ClearAll();
    send_ack(CMD_CLEAR_ALL_SENSORS, NULL, 0);
    log_event("All sensors cleared");
}

static void handle_get_slot_info(const Command_t *cmd)
{
    if (cmd->payload_len < 1) {
        send_nack(CMD_GET_SLOT_INFO, ERR_BAD_PAYLOAD);
        return;
    }

    Slot_t info;
    int rc = Reader_GetSlotInfo(cmd->payload.clear_slot.slot_id, &info);
    if (rc != READER_OK) {
        send_nack(CMD_GET_SLOT_INFO, ERR_SLOT_NOT_FOUND);
        return;
    }

    /* Sérialiser la réponse */
    uint8_t resp[64];
    uint8_t pos = 0;
    resp[pos++] = info.slot_id;
    resp[pos++] = (uint8_t)info.bus_type;
    resp[pos++] = info.device_count;
    for (uint8_t d = 0; d < info.device_count; ++d) {
        resp[pos++] = info.devices[d].uid;
        resp[pos++] = (uint8_t)info.devices[d].model;
        resp[pos++] = (uint8_t)info.devices[d].quantity;
        resp[pos++] = info.devices[d].i2c_address;
        resp[pos++] = info.devices[d].initialized ? 1 : 0;
    }

    send_response(CMD_SLOT_INFO_RESP, resp, pos);
}

/* ============================================================
 *  Handlers — Règles
 * ============================================================ */

static void handle_add_rule(const Command_t *cmd)
{
    Rule_t rule;
    memset(&rule, 0, sizeof(rule));

    int rc = parse_rule_from_payload(cmd->payload.raw, cmd->payload_len, &rule);
    if (rc != 0) {
        Error_Code_t err;
        switch (rc) {
            case -1: err = ERR_BAD_PAYLOAD;       break;
            case -2: err = ERR_TOO_MANY_COND;     break;
            case -3: err = ERR_PATTERN_SYNTAX;     break;
            case -4: err = ERR_INVALID_CONDITION;  break;
            default: err = ERR_BAD_PAYLOAD;        break;
        }
        send_nack(CMD_ADD_RULE, err);
        return;
    }

    rc = RulesStore_Add(&rule);
    if (rc == STORE_OK) {
        send_ack(CMD_ADD_RULE, &rule.rule_id, 1);
        log_event("Rule added");
    } else {
        send_nack(CMD_ADD_RULE, ERR_RULES_TABLE_FULL);
    }
}

static void handle_remove_rule(const Command_t *cmd)
{
    if (cmd->payload_len < 1) {
        send_nack(CMD_REMOVE_RULE, ERR_BAD_PAYLOAD);
        return;
    }

    int rc = RulesStore_Remove(cmd->payload.remove_rule.rule_id);
    if (rc == STORE_OK) {
        send_ack(CMD_REMOVE_RULE, NULL, 0);
    } else {
        send_nack(CMD_REMOVE_RULE, ERR_RULE_NOT_FOUND);
    }
}

static void handle_update_rule(const Command_t *cmd)
{
    Rule_t rule;
    memset(&rule, 0, sizeof(rule));

    int rc = parse_rule_from_payload(cmd->payload.raw, cmd->payload_len, &rule);
    if (rc != 0) {
        send_nack(CMD_UPDATE_RULE, ERR_BAD_PAYLOAD);
        return;
    }

    rc = RulesStore_Update(&rule);
    if (rc == STORE_OK) {
        send_ack(CMD_UPDATE_RULE, NULL, 0);
    } else {
        send_nack(CMD_UPDATE_RULE, ERR_RULE_NOT_FOUND);
    }
}

static void handle_enable_rule(const Command_t *cmd)
{
    if (cmd->payload_len < sizeof(Cmd_EnableRule_t)) {
        send_nack(CMD_ENABLE_RULE, ERR_BAD_PAYLOAD);
        return;
    }

    const Cmd_EnableRule_t *p = &cmd->payload.enable_rule;

    /* Récupérer la règle, modifier enabled, remettre */
    Rules_Snapshot_t snap;
    RulesStore_GetSnapshot(&snap);

    bool found = false;
    for (uint8_t i = 0; i < snap.count; ++i) {
        if (snap.rules[i].rule_id == p->rule_id) {
            snap.rules[i].enabled = (p->enabled != 0);
            RulesStore_Update(&snap.rules[i]);
            found = true;
            break;
        }
    }

    if (found) {
        send_ack(CMD_ENABLE_RULE, NULL, 0);
    } else {
        send_nack(CMD_ENABLE_RULE, ERR_RULE_NOT_FOUND);
    }
}

static void handle_clear_all_rules(const Command_t *cmd)
{
    RulesStore_ClearAll();
    send_ack(CMD_CLEAR_ALL_RULES, NULL, 0);
    log_event("All rules cleared");
}

/* ============================================================
 *  Handlers — Acquisition
 * ============================================================ */

static void handle_start_acq(const Command_t *cmd)
{
    if (g_acq_running) {
        send_nack(CMD_START_ACQ, ERR_ALREADY_RUNNING);
        return;
    }

    if (cmd->payload_len >= sizeof(Cmd_StartAcq_t)) {
        const Cmd_StartAcq_t *p = &cmd->payload.start_acq;
        g_acq_mode = (Acq_Mode_t)p->mode;
        if (p->period_ms > 0) {
            Reader_SetPeriod(p->period_ms);
        }
    }

    Reader_StartAcquisition();
    RulesEngine_StartEvaluation();
    g_acq_running = true;

    send_ack(CMD_START_ACQ, NULL, 0);
    log_event("Acquisition started");
}

static void handle_stop_acq(const Command_t *cmd)
{
    if (!g_acq_running) {
        send_nack(CMD_STOP_ACQ, ERR_NOT_RUNNING);
        return;
    }

    Reader_StopAcquisition();
    RulesEngine_StopEvaluation();
    g_acq_running = false;

    send_ack(CMD_STOP_ACQ, NULL, 0);
    log_event("Acquisition stopped");
}

static void handle_set_period(const Command_t *cmd)
{
    if (cmd->payload_len < sizeof(Cmd_SetPeriod_t)) {
        send_nack(CMD_SET_PERIOD, ERR_BAD_PAYLOAD);
        return;
    }

    const Cmd_SetPeriod_t *p = &cmd->payload.set_period;
    if (p->period_ms == 0) {
        send_nack(CMD_SET_PERIOD, ERR_BAD_PAYLOAD);
        return;
    }

    Reader_SetPeriod(p->period_ms);
    send_ack(CMD_SET_PERIOD, NULL, 0);
}

/* ============================================================
 *  Handlers — Flash
 *
 *  TODO: implémenter la lecture/écriture flash réelle.
 *  Pour l'instant, ces handlers sont des squelettes qui
 *  répondent ACK/NACK sans toucher la flash.
 * ============================================================ */

static void handle_save_to_flash(const Command_t *cmd)
{
    /* TODO: sérialiser les slots du reader + les règles du store
     * dans un secteur flash dédié.
     *
     * Layout flash proposé :
     *   - Magic number (4 octets) pour valider la présence de données
     *   - Version du format (2 octets)
     *   - Nombre de devices (1 octet)
     *   - Pour chaque device : slot_id, model, quantity, i2c_addr, params
     *   - Nombre de règles (1 octet)
     *   - Pour chaque règle : Rule_t sérialisée
     *   - CRC32 de tout le bloc
     */
    send_ack(CMD_SAVE_TO_FLASH, NULL, 0);
    log_event("Config saved to flash");
}

static void handle_load_from_flash(const Command_t *cmd)
{
    /* TODO: lire le secteur flash, vérifier magic + CRC,
     * désérialiser et appeler Reader_AssignSensor + RulesStore_Add
     * pour chaque entrée.
     */
    send_ack(CMD_LOAD_FROM_FLASH, NULL, 0);
    log_event("Config loaded from flash");
}

static void handle_erase_flash(const Command_t *cmd)
{
    /* TODO: effacer le secteur flash de config */
    send_ack(CMD_ERASE_FLASH, NULL, 0);
    log_event("Flash config erased");
}

/* ============================================================
 *  Parsing du payload ADD_RULE / UPDATE_RULE
 *
 *  Format binaire du payload :
 *    [rule_id(1)] [priority(1)] [enabled(1)]
 *    [n_conditions(1)]
 *    [condition_0 ... condition_N-1]  (chaque = sizeof Condition_Payload_t)
 *    [pattern_len(1)] [pattern_text(pattern_len)] (null-terminated)
 *    [n_triggers(1)]
 *    [trigger_0 ... trigger_M-1]     (chaque = sizeof Trigger_Payload_t)
 *
 *  Retourne 0 si OK, négatif sinon.
 * ============================================================ */

/* Taille d'une condition dans le payload binaire */
#define COND_PAYLOAD_SIZE  35
/* Taille d'un trigger dans le payload binaire */
#define TRIG_PAYLOAD_SIZE  14
volatile uint16_t dgb_pos;
static int parse_rule_from_payload(const uint8_t *p, uint16_t len, Rule_t *out)
{
    uint16_t pos = 0;

    /* Header : rule_id, priority, enabled */
    if (len < 4) return -1;
    out->rule_id  = p[pos++];
    out->priority = p[pos++];
    out->enabled  = (p[pos++] != 0);

    /* Conditions */
    out->n_conditions = p[pos++];
    if (out->n_conditions > MAX_COND_PER_RULE) return -2;
    if (pos + out->n_conditions * COND_PAYLOAD_SIZE > len) return -1;

    for (uint8_t i = 0; i < out->n_conditions; ++i) {
        Condition_t *c = &out->conditions[i];
        c->fn_a     = (Primitive_t)p[pos++];
        c->uid_a    = p[pos++];
        c->window_a = p[pos++];
        memcpy(&c->param_a, &p[pos], 4);  pos += 4;
        memcpy(&c->coeff_a, &p[pos], 4);  pos += 4;
        c->arith    = (Arith_Op_t)p[pos++];
        c->fn_b     = (Primitive_t)p[pos++];
        c->uid_b    = p[pos++];
        c->window_b = p[pos++];
        memcpy(&c->param_b, &p[pos], 4);  pos += 4;
        memcpy(&c->coeff_b, &p[pos], 4);  pos += 4;
        memcpy(&c->offset,  &p[pos], 4);  pos += 4;
        c->cmp      = (Compare_Op_t)p[pos++];
        memcpy(&c->rhs,       &p[pos], 4);  pos += 4;
        memcpy(&c->tolerance, &p[pos], 4);  pos += 4;
    }

    /* Pattern texte */
    if (pos >= len) return -1;
    uint8_t pattern_len = p[pos++];
    if (pos + pattern_len > len) return -1;

    char pattern_text[MAX_CMD_PAYLOAD];
    memcpy(pattern_text, &p[pos], pattern_len);
    pattern_text[pattern_len] = '\0';
    pos += pattern_len;

    /* Compiler le pattern en RPN */
    int rc = Pattern_Compile(pattern_text,
                             out->n_conditions,
                             out->pattern_rpn,
                             &out->n_tokens);
    if (rc != PATTERN_OK) return -3;
    dgb_pos=pos;
    /* Triggers */
    if (pos >= len) return -1;
    out->n_triggers = p[pos++];
    if (out->n_triggers > MAX_TRIGGERS_PER_RULE) return -4;
    if (pos + out->n_triggers * TRIG_PAYLOAD_SIZE > len) return -1;

    for (uint8_t i = 0; i < out->n_triggers; ++i) {
        Trigger_t *t = &out->triggers[i];
        t->type = (Trigger_Type_t)p[pos++];

        if (t->type == TRIG_LOG || t->type == TRIG_STREAM) {
            t->data.payload.n_uids = p[pos++];
            if (t->data.payload.n_uids > MAX_UIDS_PER_TRIGGER) {
                t->data.payload.n_uids = MAX_UIDS_PER_TRIGGER;
            }
            memcpy(t->data.payload.uids, &p[pos], t->data.payload.n_uids);
            pos += MAX_UIDS_PER_TRIGGER;
            /* Sauter les champs action inutilisés */
            pos += 4;  /* action_pin + action_code + action_param */
        } else if (t->type == TRIG_ACTION) {
            pos += 1 + MAX_UIDS_PER_TRIGGER;  /* sauter n_uids + uids[] */
            t->data.action.pin_or_servo_id = p[pos++];
            t->data.action.action_code     = p[pos++];
            memcpy(&t->data.action.param, &p[pos], 2);  pos += 2;
        } else {
            pos += TRIG_PAYLOAD_SIZE - 1;  /* sauter le reste */
        }
    }

    return 0;
}

/* ============================================================
 *  Helpers de communication — envoi vers queue_tx
 *
 *  Le module expédition_uart consomme queue_tx et construit
 *  les frames UART (STX/CMD/LEN/PAYLOAD/CRC/ETX).
 *  Le commander pousse juste le contenu logique.
 * ============================================================ */

/* Structure de message pour queue_tx */
typedef struct {
    uint8_t  cmd_id;
    uint16_t payload_len;
    uint8_t  payload[MAX_CMD_PAYLOAD];
} Tx_Message_t;

static void send_response(uint8_t cmd_id, const uint8_t *payload, uint16_t len)
{
    Tx_Message_t msg;
    msg.cmd_id      = cmd_id;
    msg.payload_len = (len <= MAX_CMD_PAYLOAD) ? len : MAX_CMD_PAYLOAD;
    if (payload && len > 0) {
        memcpy(msg.payload, payload, msg.payload_len);
    }
    osMessageQueuePut(queue_tx, &msg, 0, 0);
}

static void send_ack(uint8_t original_cmd, const uint8_t *data, uint8_t data_len)
{
    uint8_t payload[10];
    payload[0] = original_cmd;
    payload[1] = data_len;
    if (data && data_len > 0 && data_len <= 8) {
        memcpy(&payload[2], data, data_len);
    }
    send_response(CMD_ACK, payload, 2 + data_len);
}

static void send_nack(uint8_t original_cmd, Error_Code_t error)
{
    uint8_t payload[2];
    payload[0] = original_cmd;
    payload[1] = (uint8_t)error;
    send_response(CMD_NACK, payload, 2);
}

/* ============================================================
 *  Log d'événements système
 * ============================================================ */

typedef struct {
    uint32_t timestamp_ms;
    char     message[64];
} Log_Event_t;

static void log_event(const char *msg)
{
    Log_Event_t evt;
    evt.timestamp_ms = osKernelGetTickCount();
    strncpy(evt.message, msg, sizeof(evt.message) - 1);
    evt.message[sizeof(evt.message) - 1] = '\0';

    /* Non-bloquant — si la queue log est pleine, on perd l'événement */
    osMessageQueuePut(queue_log, &evt, 0, 0);
}
