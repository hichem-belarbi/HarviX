/* ================================================================
 * App/uart_rx_task.h
 * ================================================================ */
#ifndef RX_H
#define RX_H

#include "cmsis_os2.h"
#include "commander_types.h"
#include <stdint.h>

/* ── Taille de la queue de commandes ────────────────────────── */
#define RX_CMD_QUEUE_LENGTH   8
#define RX_MAX_PAYLOAD        64     /* payload brut avant décodage */

/* ── Mutex partagé UART TX/RX ───────────────────────────────── */
/* Ce mutex est créé par rx_queue_init() et doit être acquis par
 * la tâche TX avant tout HAL_UART_Transmit, et par la tâche RX
 * avant tout HAL_UART_Receive, pour garantir l'exclusion mutuelle
 * sur l'interface UART physique.                                 */
extern osMutexId_t g_uart_mutex;

/* ── Queue de commandes vers le commander ───────────────────── */
/* Contient des Command_t (commander_types.h).
 * Les commandes légères (PING, SYNC_REQUEST) sont traitées
 * inline dans uart_rx_task et n'apparaissent jamais ici.        */
extern osMessageQueueId_t g_cmd_queue;

/* ── API publique ───────────────────────────────────────────── */
void rx_queue_init(void);     /* crée g_uart_mutex + g_cmd_queue         */
void rx_start(void);          /* rx_queue_init() + osThreadNew() en un appel */
void uart_rx_task(void *arg); /* point d'entrée osThreadNew()            */

#endif /* RX_H */
