#ifndef COMMANDER_TYPES_H
#define COMMANDER_TYPES_H

#include <stdint.h>
#include <stdbool.h>

#define MAX_CMD_PAYLOAD  256

/* ============================================================
 *  Source d'une commande
 * ============================================================ */
typedef enum {
    CMD_SRC_UART = 0,
    CMD_SRC_UI,
    CMD_SRC_INTERNAL,
} Command_Source_t;

/* ============================================================
 *  IDs de commandes — organisées par famille
 * ============================================================ */

/* Famille 0x0_ — Système et session */
#define CMD_SYNC_REQUEST       0x01
#define CMD_SYNC_RESPONSE      0x02
#define CMD_LOGIN              0x03
#define CMD_LOGOUT             0x04
#define CMD_SET_CREDENTIALS    0x05
#define CMD_PING               0x06
#define CMD_GET_STATUS         0x07
#define CMD_STATUS_RESPONSE    0x08

/* Famille 0x1_ — Capteurs (lecteur) */
#define CMD_ASSIGN_SENSOR      0x10
#define CMD_CLEAR_DEVICE       0x11
#define CMD_CLEAR_SLOT         0x12
#define CMD_CLEAR_ALL_SENSORS  0x13
#define CMD_GET_SLOT_INFO      0x14
#define CMD_SLOT_INFO_RESP     0x15

/* Famille 0x2_ — Règles (moteur de règles) */
#define CMD_ADD_RULE           0x20
#define CMD_REMOVE_RULE        0x21
#define CMD_UPDATE_RULE        0x22
#define CMD_ENABLE_RULE        0x23
#define CMD_CLEAR_ALL_RULES    0x24
#define CMD_GET_RULE           0x25
#define CMD_RULE_RESP          0x26

/* Famille 0x3_ — Acquisition et streaming */
#define CMD_START_ACQ          0x30
#define CMD_STOP_ACQ           0x31
#define CMD_SET_PERIOD         0x32
#define CMD_DATA_FRAME         0x33
#define CMD_ALERT              0x34

/* Famille 0x4_ — Persistance flash */
#define CMD_SAVE_TO_FLASH      0x40
#define CMD_LOAD_FROM_FLASH    0x41
#define CMD_ERASE_FLASH        0x42

/* Famille 0xF_ — Réponses génériques */
#define CMD_ACK                0xF0
#define CMD_NACK               0xF1

/* ============================================================
 *  Codes d'erreur pour NACK
 * ============================================================ */
typedef enum {
    ERR_NONE = 0,
    ERR_UNKNOWN_CMD        = 0x01,
    ERR_BAD_PAYLOAD        = 0x02,
    ERR_NOT_AUTHENTICATED  = 0x03,

    /* Capteurs */
    ERR_SLOT_NOT_FOUND     = 0x10,
    ERR_SLOT_FULL          = 0x11,
    ERR_BUS_INCOMPATIBLE   = 0x12,
    ERR_SENSOR_INIT_FAIL   = 0x13,
    ERR_DEVICE_NOT_FOUND   = 0x14,

    /* Règles */
    ERR_RULES_TABLE_FULL   = 0x20,
    ERR_RULE_NOT_FOUND     = 0x21,
    ERR_PATTERN_SYNTAX     = 0x22,
    ERR_TOO_MANY_COND      = 0x23,
    ERR_INVALID_CONDITION  = 0x24,

    /* Acquisition */
    ERR_NO_SENSOR_ASSIGNED = 0x30,
    ERR_ALREADY_RUNNING    = 0x31,
    ERR_NOT_RUNNING        = 0x32,

    /* Flash */
    ERR_FLASH_WRITE_FAIL   = 0x40,
    ERR_FLASH_READ_FAIL    = 0x41,
    ERR_FLASH_EMPTY        = 0x42,
} Error_Code_t;

/* ============================================================
 *  Modes d'acquisition
 * ============================================================ */
typedef enum {
    ACQ_MODE_SD_ONLY = 0,
    ACQ_MODE_STREAM_ONLY,
    ACQ_MODE_BOTH,
} Acq_Mode_t;

/* ============================================================
 *  Payloads des commandes (packed pour sérialisation UART)
 *  Définis AVANT Command_Payload_t qui les référence.
 * ============================================================ */

typedef struct __attribute__((packed)) {
    uint8_t  slot_id;
    uint8_t  model;           /* Sensor_Model_t     */
    uint8_t  quantity;        /* Physical_Quantity_t */
    uint8_t  i2c_address;
    uint8_t  raw[16];
} Cmd_AssignSensor_t;         /* 20 octets */

typedef struct __attribute__((packed)) {
    uint8_t  uid;
} Cmd_ClearDevice_t;

typedef struct __attribute__((packed)) {
    uint8_t  slot_id;
} Cmd_ClearSlot_t;

typedef struct __attribute__((packed)) {
    uint8_t  mode;            /* Acq_Mode_t         */
    uint32_t period_ms;
} Cmd_StartAcq_t;             /* 5 octets */

typedef struct __attribute__((packed)) {
    uint32_t period_ms;
} Cmd_SetPeriod_t;

typedef struct __attribute__((packed)) {
    uint8_t  rule_id;
    uint8_t  enabled;         /* 0 ou 1              */
} Cmd_EnableRule_t;

typedef struct __attribute__((packed)) {
    uint8_t  rule_id;
} Cmd_RemoveRule_t;

typedef struct __attribute__((packed)) {
    uint8_t  original_cmd_id;
    uint8_t  data_len;
    uint8_t  data[8];
} Cmd_Ack_Payload_t;

typedef struct __attribute__((packed)) {
    uint8_t  original_cmd_id;
    uint8_t  error_code;      /* Error_Code_t        */
} Cmd_Nack_Payload_t;

/* ============================================================
 *  Union de tous les payloads possibles
 *
 *  Chaque handler accède au champ correspondant à sa commande :
 *    cmd->payload.assign_sensor.slot_id
 *    cmd->payload.start_acq.period_ms
 *    cmd->payload.enable_rule.rule_id
 *
 *  Le champ `raw` sert pour les payloads à taille variable
 *  (ADD_RULE, SYNC_RESPONSE) qui nécessitent un parsing
 *  séquentiel octet par octet.
 * ============================================================ */
typedef union {
    Cmd_AssignSensor_t  assign_sensor;   /* CMD_ASSIGN_SENSOR  */
    Cmd_ClearDevice_t   clear_device;    /* CMD_CLEAR_DEVICE   */
    Cmd_ClearSlot_t     clear_slot;      /* CMD_CLEAR_SLOT     */
    Cmd_StartAcq_t      start_acq;       /* CMD_START_ACQ      */
    Cmd_SetPeriod_t     set_period;      /* CMD_SET_PERIOD     */
    Cmd_EnableRule_t    enable_rule;      /* CMD_ENABLE_RULE    */
    Cmd_RemoveRule_t    remove_rule;      /* CMD_REMOVE_RULE    */
    Cmd_Ack_Payload_t   ack;             /* CMD_ACK            */
    Cmd_Nack_Payload_t  nack;            /* CMD_NACK           */
    uint8_t             raw[MAX_CMD_PAYLOAD]; /* ADD_RULE, etc. */
} Command_Payload_t;

/* ============================================================
 *  Commande unifiée — poussée dans queue_cmds
 * ============================================================ */
typedef struct {
    uint8_t            cmd_id;
    Command_Source_t   source;
    uint16_t           payload_len;
    Command_Payload_t  payload;
} Command_t;

/* ============================================================
 *  Frame UART — protocole de communication
 * ============================================================ */
#define FRAME_STX   0xAA
#define FRAME_ETX   0x55

#endif /* COMMANDER_TYPES_H */