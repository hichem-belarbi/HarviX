#ifndef LOGGER_QUEUE_TYPES_H
#define LOGGER_QUEUE_TYPES_H

#include "FreeRTOS.h"
#include "queue.h"
#include <stdint.h>
#include <stdbool.h>

#define MAX_CHANNELS_PER_RULE   8
#define MAX_RULE_NAME_LEN       32
#define MAX_RULES               16
#define LOGGER_QUEUE_LENGTH     32

typedef enum {
    CMD_LOG,           /* log readings for one rule                */
    CMD_ADD_RULE,      /* register rule_id ↔ name (→ filename)     */
    CMD_REMOVE_RULE,   /* deactivate a rule                        */
    CMD_DELETE_FILE,   /* f_unlink "<name>.csv" on SD              */
    CMD_RENAME_FILE,   /* f_rename old→new                         */
} LogCmdType_t;

/* one channel's reading inside a log command */
typedef struct {
    uint8_t  channel_id;
    float    value;
    uint8_t  status;    /* Sensor_Status_t cast to uint8_t          */
} ChannelReading_t;

/* ── payloads ────────────────────────────────────────────────────── */
typedef struct {
    uint8_t          rule_id;
    uint32_t         timestamp_ms;
    uint8_t          num_channels;
    ChannelReading_t channels[MAX_CHANNELS_PER_RULE];
} LogPayload_t;

typedef struct {
    uint8_t rule_id;
    char    name[MAX_RULE_NAME_LEN];
} AddRulePayload_t;

typedef struct { uint8_t rule_id; }              RemoveRulePayload_t;
typedef struct { char name[MAX_RULE_NAME_LEN]; } DeleteFilePayload_t;

typedef struct {
    char old_name[MAX_RULE_NAME_LEN];
    char new_name[MAX_RULE_NAME_LEN];
} RenameFilePayload_t;

/* ── the command that goes into the queue ────────────────────────── */
typedef struct {
    LogCmdType_t type;
    union {
        LogPayload_t        log;
        AddRulePayload_t    add_rule;
        RemoveRulePayload_t remove_rule;
        DeleteFilePayload_t delete_file;
        RenameFilePayload_t rename_file;
    } u;
} LogCommand_t;

extern QueueHandle_t g_logger_queue;

void logger_queue_init(void);

bool logger_post_log(uint8_t rule_id, uint32_t ts_ms,
                     uint8_t num_ch, const ChannelReading_t *readings);
bool logger_post_add_rule   (uint8_t rule_id, const char *name);
bool logger_post_remove_rule(uint8_t rule_id);
bool logger_post_delete_file(const char *name);
bool logger_post_rename_file(const char *old_name, const char *new_name);

#endif /* LOGGER_QUEUE_TYPES_H */
