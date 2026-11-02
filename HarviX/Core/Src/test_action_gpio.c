/* ============================================================
 *  test_action_gpio.c — Consomme queue_action du rules engine
 *                        et exécute les commandes GPIO
 *
 *  ARCHITECTURE :
 *    rules_engine.c  → écrit Hardware_Action_t dans queue_action
 *    action_task.c   → consomme queue_action, mappe vers HAL GPIO
 *
 *  MAPPING pin_or_servo_id → pin physique (board_config.h) :
 *    1 → PD0  (ACTION_PIN1)
 *    2 → PD1  (ACTION_PIN2)
 *    3 → PD3  (ACTION_PIN3)
 *    4 → PD4  (ACTION_PIN4)
 *
 *  MAPPING action_code :
 *    0 → PIN_LOW  (GPIO_PIN_RESET)
 *    1 → PIN_HIGH (GPIO_PIN_SET)
 *    2 → PIN_TOGGLE
 *
 *  LIVE EXPRESSIONS :
 *    dbg_act_received   → nombre de commandes reçues
 *    dbg_act_last       → dernière commande exécutée
 *    dbg_act_err        → 0xFF si pin_id inconnu
 * ============================================================ */

#include "board_config.h"
#include "rule_types.h"
#include "action_queue.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>

/* ============================================================
 *  Queue — définie dans test_rules_debug.c
 * ============================================================ */
extern osMessageQueueId_t queue_action;

/* ============================================================
 *  Table de résolution pin_or_servo_id → port/pin
 * ============================================================ */
typedef struct {
    GPIO_TypeDef *port;
    uint16_t      pin;
} Pin_Entry_t;

static const Pin_Entry_t pin_table[NB_ACTION_PINS] = {
    { ACTION_PIN1_PORT, ACTION_PIN1_PIN },   /* id=1 → PD0 */
    { ACTION_PIN2_PORT, ACTION_PIN2_PIN },   /* id=2 → PD1 */
    { ACTION_PIN3_PORT, ACTION_PIN3_PIN },   /* id=3 → PD3 */
    { ACTION_PIN4_PORT, ACTION_PIN4_PIN },   /* id=4 → PD4 */
};

/* ============================================================
 *  Variables debug
 * ============================================================ */
volatile uint32_t dbg_act_received = 0;
volatile uint8_t  dbg_act_err      = 0;

volatile struct {
    uint8_t  pin_or_servo_id;
    uint8_t  action_code;
    uint16_t param;
} dbg_act_last = {0};

/* ============================================================
 *  Exécution d'une commande GPIO
 * ============================================================ */


/* ============================================================
 *  Tâche — consomme queue_action en permanence
 * ============================================================ */
volatile ActionCommand_t dbg_cmd111;
static void action_gpio_task(void *arg)
{
    (void)arg;
    ActionCommand_t cmd;

    for (;;) {
        if (osMessageQueueGet(queue_action, &cmd, NULL,
                              osWaitForever) == osOK) {
        	dbg_cmd111=cmd;
            dbg_act_last.pin_or_servo_id = cmd.u.gpio.pin;
            dbg_act_last.action_code     = cmd.type;
            dbg_act_received++;

            switch (cmd.type) {
                case ACT_GPIO_WRITE:
                    HAL_GPIO_WritePin(cmd.u.gpio.port, cmd.u.gpio.pin,
                                      cmd.u.gpio.state ? GPIO_PIN_SET
                                                       : GPIO_PIN_RESET);
                    break;
                case ACT_GPIO_TOGGLE:
                    HAL_GPIO_TogglePin(cmd.u.gpio.port, cmd.u.gpio.pin);
                    break;
                case ACT_GPIO_BLINK:
                    for (uint8_t i = 0; i < cmd.u.gpio.count; i++) {
                        HAL_GPIO_WritePin(cmd.u.gpio.port, cmd.u.gpio.pin,
                                          GPIO_PIN_SET);
                        vTaskDelay(pdMS_TO_TICKS(cmd.u.gpio.period_ms));
                        HAL_GPIO_WritePin(cmd.u.gpio.port, cmd.u.gpio.pin,
                                          GPIO_PIN_RESET);
                        if (i < cmd.u.gpio.count - 1)
                            vTaskDelay(pdMS_TO_TICKS(cmd.u.gpio.period_ms));
                    }
                    break;
                default:
                    dbg_act_err = 0xFE;
                    break;
            }
        }
    }
}
/* ============================================================
 *  Point d'entrée — appeler depuis main() après
 *  test_rules_debug_main() et avant osKernelStart()
 *
 *  Dans main.c :
 *    osKernelInitialize();
 *    test_debug_main();          // reader
 *    test_rules_debug_main();    // rules engine
 *    test_action_gpio_main();    // ← ici
 *    osKernelStart();
 * ============================================================ */
void test_action_gpio_main(void)
{
    const osThreadAttr_t attr = {
        .name       = "act_gpio",
        .stack_size = 512,
        .priority   = osPriorityAboveNormal,
    };
    osThreadNew(action_gpio_task, NULL, &attr);
}
