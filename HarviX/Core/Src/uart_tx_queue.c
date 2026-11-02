/* ================================================================
 * App/uart_tx_queue.c
 * ================================================================ */
#include "uart_tx_queue.h"
#include <string.h>

extern osMessageQueueId_t queue_tx;

void tx_queue_init(void)
{
    queue_tx = osMessageQueueNew(TX_QUEUE_LENGTH, sizeof(TxCommand_t),NULL);
    configASSERT(queue_tx);
}

static bool post(TxCommand_t *cmd)
{
    return osMessageQueuePut(queue_tx, cmd, 0,0) == pdTRUE;
}

bool tx_post_live_data(uint8_t rule_id, uint32_t ts_ms,
                        uint8_t n, const ChannelReading_t *r)
{
    TxCommand_t cmd = { .type = TX_LIVE_DATA };
    cmd.u.live.rule_id      = rule_id;
    cmd.u.live.timestamp_ms = ts_ms;
    cmd.u.live.num_channels = n > MAX_CHANNELS_PER_RULE ? MAX_CHANNELS_PER_RULE : n;
    memcpy(cmd.u.live.channels, r,
           cmd.u.live.num_channels * sizeof(ChannelReading_t));
    return post(&cmd);
}

bool tx_post_alert(uint8_t rule_id, AlertLevel_t level,
                   uint32_t ts_ms, float value, float threshold)
{
    TxCommand_t cmd = { .type = TX_ALERT };
    cmd.u.alert.rule_id      = rule_id;
    cmd.u.alert.level        = level;
    cmd.u.alert.timestamp_ms = ts_ms;
    cmd.u.alert.value        = value;
    cmd.u.alert.threshold    = threshold;
    return post(&cmd);
}

bool tx_post_cmd_response(uint8_t cmd_id, uint8_t status, const char *data)
{
    TxCommand_t cmd = { .type = TX_CMD_RESPONSE };
    cmd.u.response.cmd_id = cmd_id;
    cmd.u.response.status = status;
    strncpy(cmd.u.response.data, data, TX_MAX_MSG - 1);
    return post(&cmd);
}

bool tx_post_heartbeat(uint32_t uptime, uint8_t sd_st,
                        uint8_t rules, uint8_t chans, uint16_t heap_kb)
{
    TxCommand_t cmd = { .type = TX_HEARTBEAT };
    cmd.u.heartbeat.uptime_ms       = uptime;
    cmd.u.heartbeat.sd_status       = sd_st;
    cmd.u.heartbeat.active_rules    = rules;
    cmd.u.heartbeat.active_channels = chans;
    cmd.u.heartbeat.free_heap_kb    = heap_kb;
    return post(&cmd);
}

bool tx_post_rule_event(uint8_t rule_id, uint8_t event, uint8_t action)
{
    TxCommand_t cmd = { .type = TX_RULE_EVENT };
    cmd.u.rule_event.rule_id      = rule_id;
    cmd.u.rule_event.event        = event;
    cmd.u.rule_event.action_taken = action;
    cmd.u.rule_event.timestamp_ms = HAL_GetTick();
    return post(&cmd);
}
