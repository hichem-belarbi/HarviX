/* ================================================================
 * App/uart_rx_task.c
 *
 * Responsabilités :
 *   1. Recevoir les trames UART (STX | CMD | LEN | PAYLOAD | ETX)
 *   2. Traiter inline les commandes légères :
 *        - PING         → HAL_UART_Transmit direct (latence minimale)
 *        - GET_STATUS   → via queue_tx
 *        - SYNC_REQUEST → via queue_tx
 *   3. Pousser les commandes lourdes dans queue_cmds (→ commander)
 *
 * Protection UART :
 *   Pas de mutex sur HAL_UART_Receive (RxState/gState séparés, HAL v1.7+).
 *   g_uart_mutex protège UNIQUEMENT HAL_UART_Transmit — partagé avec
 *   la tâche TX pour éviter deux envois simultanés.
 *
 * Protocole de trame (sans CRC) :
 *   [STX=0xAA] [CMD(1)] [LEN(1)] [PAYLOAD(LEN)] [ETX=0x55]
 * ================================================================ */

#include "rx.h"
#include "commander_types.h"
#include "stm32f4xx_hal.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>

/* ── Handles externes ───────────────────────────────────────── */
extern UART_HandleTypeDef    huart1;
extern osMessageQueueId_t    queue_tx;

/* ── Handles publics ────────────────────────────────────────── */
osMutexId_t        g_uart_mutex;
osMessageQueueId_t queue_cmds;

/* ================================================================
 *  Tx_Message_t — structure partagée avec la tâche TX
 *  Doit correspondre à Tx_Message_t dans commander.c
 * ================================================================ */
typedef struct {
    uint8_t  cmd_id;
    uint16_t payload_len;
    uint8_t  payload[MAX_CMD_PAYLOAD];
} Tx_Message_t;

/* ================================================================
 *  Prototypes internes
 * ================================================================ */
static int  uart_read(uint8_t *dst, uint16_t n, uint32_t timeout_ms);
static void uart_transmit_locked(const uint8_t *data, uint16_t len);
static void tx_push(uint8_t cmd_id, const uint8_t *payload, uint16_t len);
static void tx_nack(uint8_t original_cmd, uint8_t error_code);

static void inline_handle_ping        (void);
static void inline_handle_sync_request(const uint8_t *payload, uint8_t len);
static void inline_handle_get_status  (void);

/* ================================================================
 *  Init
 * ================================================================ */

void rx_queue_init(void)
{
    const osMutexAttr_t mutex_attr = {
        .name      = "uart_mutex",
        .attr_bits = osMutexPrioInherit,
    };
    g_uart_mutex = osMutexNew(&mutex_attr);
    configASSERT(g_uart_mutex);

    queue_cmds = osMessageQueueNew(RX_CMD_QUEUE_LENGTH, sizeof(Command_t), NULL);
    configASSERT(queue_cmds);
}

/* ================================================================
 *  rx_start — un seul appel depuis main
 *
 *      osKernelInitialize();
 *      rx_start();
 *      osKernelStart();
 * ================================================================ */

void rx_start(void)
{
    rx_queue_init();

    static const osThreadAttr_t attr = {
        .name       = "uart_rx",
        .stack_size = 512,
        .priority   = osPriorityNormal,
    };
    osThreadId_t tid = osThreadNew(uart_rx_task, NULL, &attr);
    configASSERT(tid);
}

/* ================================================================
 *  Tâche RX principale
 *
 *  Lecture en 3 appels HAL seulement :
 *    1. osWaitForever sur le STX
 *    2. 500ms sur CMD + LEN
 *    3. 500ms sur PAYLOAD + ETX (tout d'un coup)
 * ================================================================ */
uint8_t dbg_cmd_rx;

uint32_t rcvd_cmd_count=0;
uint32_t rcvd_cmd[11];
void uart_rx_task(void *arg)
{
    (void)arg;

    /* Buffer taille max : STX(1) + CMD(1) + LEN(1) + PAYLOAD(n) + ETX(1) */
    uint8_t frame[3 + RX_MAX_PAYLOAD + 1];

    for (;;)
    {
        /* ── 1. Attendre STX (resync automatique) ───────────────── */
        do {
            if (uart_read(&frame[0], 1, osWaitForever) != 0) continue;
        } while (frame[0] != FRAME_STX);

        /* ── 2. Lire CMD + LEN ──────────────────────────────────── */
        if (uart_read(&frame[1], 2, 500) != 0) continue;

        uint8_t cmd = frame[1];
        dbg_cmd_rx=cmd;
        uint8_t len = frame[2];
        if (len > RX_MAX_PAYLOAD) continue;

        /* ── 3. Lire PAYLOAD + ETX en une seule fois ────────────── */
        /*       rest = payload(len) + etx(1)                        */
        uint16_t rest_len = (uint16_t)len + 1u;
        if (uart_read(&frame[3], rest_len, 500) != 0) continue;

        uint8_t *payload = &frame[3];
        uint8_t  etx     =  frame[3 + len];

        /* ── 4. Vérifier ETX ────────────────────────────────────── */
        if (etx != FRAME_ETX) continue;

        /* ── 5. Dispatch ─────────────────────────────────────────── */
        switch (cmd)
        {
            case CMD_PING:
                inline_handle_ping();
                break;

            case CMD_SYNC_REQUEST:
                inline_handle_sync_request(payload, len);
                break;

            case CMD_GET_STATUS:
                inline_handle_get_status();
                break;

            default:
            {
                Command_t cmd_msg;
                memset(&cmd_msg, 0, sizeof(cmd_msg));
                cmd_msg.cmd_id      = cmd;

                cmd_msg.source      = CMD_SRC_UART;
                cmd_msg.payload_len = len;
                if (len > 0)
                    memcpy(cmd_msg.payload.raw, payload, len);

                if (osMessageQueuePut(queue_cmds, &cmd_msg, 0, 0) != osOK)
                    tx_nack(cmd, ERR_NO_SENSOR_ASSIGNED);
                else inline_handle_ping();


                break;
            }
        }
    }
}

/* ================================================================
 *  Handlers inline
 * ================================================================ */

/* PING — transmit direct sous mutex, latence minimale
 * Trame : STX | ACK | LEN=2 | CMD_PING | 0x00 | ETX              */
static void inline_handle_ping(void)
{
    uint8_t frame[] = {
        FRAME_STX,
        CMD_ACK,
        0x02,       /* LEN : 2 octets de payload */
        CMD_PING,   /* original cmd              */
        0x00,       /* status OK                 */
        FRAME_ETX,
    };
    uart_transmit_locked(frame, sizeof(frame));
}

/* SYNC_REQUEST — réponse minimale via queue_tx */
static void inline_handle_sync_request(const uint8_t *payload, uint8_t len)
{
    (void)payload;
    (void)len;
    uint8_t resp[1] = { 0x00 };
    tx_push(CMD_SYNC_RESPONSE, resp, 1);
}

/* GET_STATUS — uptime + alive via queue_tx */
static void inline_handle_get_status(void)
{
    uint8_t  resp[5];
    uint32_t uptime_ms = osKernelGetTickCount();
    memcpy(&resp[0], &uptime_ms, 4);
    resp[4] = 0x01;
    tx_push(CMD_STATUS_RESPONSE, resp, sizeof(resp));
}

/* ================================================================
 *  Couche transport
 * ================================================================ */

/* uart_read — sans mutex (RxState indépendant de gState) */
static int uart_read(uint8_t *dst, uint16_t n, uint32_t timeout_ms)
{
    return (HAL_UART_Receive(&huart1, dst, n, timeout_ms) == HAL_OK) ? 0 : -1;
}

/* uart_transmit_locked — mutex TX, utilisé uniquement pour PING direct */
static void uart_transmit_locked(const uint8_t *data, uint16_t len)
{
    osMutexAcquire(g_uart_mutex, osWaitForever);
    HAL_UART_Transmit(&huart1, (uint8_t *)data, len, HAL_MAX_DELAY);
    osMutexRelease(g_uart_mutex);
}

/* tx_push — pousse dans queue_tx
 * La tâche TX construit la trame : STX | CMD | LEN | PAYLOAD | ETX */
static void tx_push(uint8_t cmd_id, const uint8_t *payload, uint16_t len)
{
    Tx_Message_t msg;
    msg.cmd_id      = cmd_id;
    msg.payload_len = (len <= MAX_CMD_PAYLOAD) ? len : MAX_CMD_PAYLOAD;
    if (payload && len > 0)
        memcpy(msg.payload, payload, msg.payload_len);
    else
        msg.payload_len = 0;

    osMessageQueuePut(queue_tx, &msg, 0, 0);
}

static void tx_nack(uint8_t original_cmd, uint8_t error_code)
{
    uint8_t payload[2] = { original_cmd, error_code };
    tx_push(CMD_NACK, payload, 2);
}
