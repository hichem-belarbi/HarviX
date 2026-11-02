/* ================================================================
 * App/uart_tx_queue.h
 * ================================================================ */
#ifndef UART_TX_QUEUE_H
#define UART_TX_QUEUE_H

#include "FreeRTOS.h"
#include "queue.h"
#include "action_queue.h"   /* AlertLevel_t          */
#include "log_queue_types.h"   /* ChannelReading_t      */
#include <stdint.h>
#include <stdbool.h>

#define TX_QUEUE_LENGTH  32
#define TX_MAX_MSG       48

typedef enum {
    TX_LIVE_DATA    = 0x01,
    TX_ALERT        = 0x02,
    TX_CMD_RESPONSE = 0x03,
    TX_HEARTBEAT    = 0x04,
    TX_RULE_EVENT   = 0x05,
} TxFrameType_t;

typedef struct {
    uint8_t          rule_id;
    uint32_t         timestamp_ms;
    uint8_t          num_channels;
    ChannelReading_t channels[MAX_CHANNELS_PER_RULE];
} TxLiveDataPayload_t;

typedef struct {
    uint8_t      rule_id;
    AlertLevel_t level;
    uint32_t     timestamp_ms;
    float        value;
    float        threshold;
} TxAlertPayload_t;

typedef struct {
    uint8_t cmd_id;
    uint8_t status;          /* 0=ACK  1=NACK  2=ERROR */
    char    data[TX_MAX_MSG];
} TxCmdResponsePayload_t;

typedef struct {
    uint32_t uptime_ms;
    uint8_t  sd_status;      /* 0=OK  1=FULL  2=ERROR  3=NOT_MOUNTED */
    uint8_t  active_rules;
    uint8_t  active_channels;
    uint16_t free_heap_kb;
} TxHeartbeatPayload_t;

typedef struct {
    uint8_t  rule_id;
    uint8_t  event;          /* 0=ACT 1=DEACT 2=COND_MET 3=COND_CLEARED */
    uint8_t  action_taken;
    uint32_t timestamp_ms;
} TxRuleEventPayload_t;

typedef struct {
    TxFrameType_t type;
    union {
        TxLiveDataPayload_t    live;
        TxAlertPayload_t       alert;
        TxCmdResponsePayload_t response;
        TxHeartbeatPayload_t   heartbeat;
        TxRuleEventPayload_t   rule_event;
    } u;
} TxCommand_t;

extern QueueHandle_t g_tx_queue;

void tx_queue_init(void);
bool tx_post_live_data   (uint8_t rule_id, uint32_t ts_ms,
                           uint8_t n, const ChannelReading_t *r);
bool tx_post_alert       (uint8_t rule_id, AlertLevel_t level,
                           uint32_t ts_ms, float value, float threshold);
bool tx_post_cmd_response(uint8_t cmd_id, uint8_t status, const char *data);
bool tx_post_heartbeat   (uint32_t uptime, uint8_t sd_st,
                           uint8_t rules, uint8_t chans, uint16_t heap_kb);
bool tx_post_rule_event  (uint8_t rule_id, uint8_t event, uint8_t action);

#endif
