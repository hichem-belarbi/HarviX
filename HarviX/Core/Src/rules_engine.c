#include "rules_engine.h"
#include "rule_types.h"
#include "rules_store.h"
#include "history_buffer.h"
#include "primitives.h"
#include "pattern_parser.h"
#include "sensor_types.h"
#include "log_queue_types.h"
#include "action_queue.h"    /* ActionCommand_t, ActionType_t, AlertLevel_t */
#include "uart_tx_queue.h"   /* TxCommand_t, tx_post_live_data              */
#include "board_config.h"    /* ACTION_PIN1_PORT/PIN etc.                   */
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>
#include <math.h>

/* queue_snapshots — définie dans test_rules_debug.c */
extern osMessageQueueId_t queue_snapshots;

/* queue_log — définie dans test_rules_debug.c, type LogCommand_t */
extern osMessageQueueId_t queue_log;

/* queue_tx — définie dans test_rules_debug.c, type TxCommand_t */
extern osMessageQueueId_t queue_tx;

/* queue_action — définie dans test_rules_debug.c, type ActionCommand_t */
extern osMessageQueueId_t queue_action;

/* ============================================================
 *  État interne du moteur
 *
 *  - was_true[]    : pour détection de front (faux → vrai)
 *  - last_trig_val[][] : pour PRIM_DELTA_LAST, par règle et par
 *                        condition, la dernière valeur ayant
 *                        causé un déclenchement.
 *  - snapshot      : copie locale de la table de règles, refraîchie
 *                    en début de cycle si la version a changé.
 * ============================================================ */
static volatile bool g_eval_running = false;
static osThreadId_t  g_task;

/* Compteurs de diagnostic — lus depuis test_rules_debug.c via extern */
uint32_t re_eval_entered    = 0;  /* process_snapshot() appelé          */
uint32_t re_cond_true_count = 0;  /* eval_condition() a retourné true   */
float    re_last_lux        = 0.0f; /* dernière valeur lue pour uid_a   */
uint32_t re_pattern_true    = 0;  /* tirs effectifs (condition vraie)   */

static bool             g_was_true[MAX_RULES];
static float            g_last_trig_val[MAX_RULES][MAX_COND_PER_RULE];
static Rules_Snapshot_t g_snapshot;
static uint32_t         g_known_version = 0;

/* ============================================================
 *  Prototypes internes
 * ============================================================ */
static void rules_task_fn(void *arg);
static void process_snapshot(const Snapshot_t *snap);
static void update_history(const Snapshot_t *snap);
static bool eval_condition(const Condition_t *c, uint8_t rule_idx,
                           uint8_t cond_idx, bool *was_triggered);
static void fire_triggers(const Rule_t *rule, const Snapshot_t *snap);
static const Measurement_t *find_in_snapshot(const Snapshot_t *snap, uint8_t uid);

/* ============================================================
 *  Init
 * ============================================================ */
void RulesEngine_Init(void)
{
    g_eval_running = false;
    memset(g_was_true, 0, sizeof(g_was_true));
    /* Initialise last_trig_val à NaN pour signaler "jamais déclenché" */
    for (int i = 0; i < MAX_RULES; ++i) {
        for (int j = 0; j < MAX_COND_PER_RULE; ++j) {
            g_last_trig_val[i][j] = NAN;
        }
    }
    memset(&g_snapshot, 0, sizeof(g_snapshot));
    g_known_version = 0;
}

void RulesEngine_StartTask(void)
{
    const osThreadAttr_t attr = {
        .name       = "rules_engine",
        .stack_size = 2048,
        .priority   = osPriorityNormal,
    };
    g_task = osThreadNew(rules_task_fn, NULL, &attr);
}

void RulesEngine_StartEvaluation(void) { g_eval_running = true;  }
void RulesEngine_StopEvaluation(void)  { g_eval_running = false; }

/* ============================================================
 *  Tâche principale — boucle bloquante sur queue_snapshots
 * ============================================================ */
static void rules_task_fn(void *arg)
{
    (void)arg;
    Snapshot_t snap;

    for (;;) {
        if (osMessageQueueGet(queue_snapshots, &snap, NULL, osWaitForever) == osOK) {
            if (g_eval_running) {
                process_snapshot(&snap);
            }
        }
    }
}

/* ============================================================
 *  Traitement d'un snapshot
 * ============================================================ */
static void process_snapshot(const Snapshot_t *snap)
{
    re_eval_entered++;
    /* 1. Refresh local de la table si elle a été modifiée */
    uint32_t v = RulesStore_GetVersion();
    if (v != g_known_version) {
        RulesStore_GetSnapshot(&g_snapshot);
        g_known_version = v;
        /* Reset des états — les indices ont pu changer après tri */
        memset(g_was_true, 0, sizeof(g_was_true));
    }

    /* 2. Mise à jour de l'historique avec les nouvelles mesures */
    update_history(snap);

    /* 3. Évaluation des règles, par priorité croissante (déjà triées) */
    bool cond_results[MAX_COND_PER_RULE];

    for (uint8_t r = 0; r < g_snapshot.count; ++r) {
        const Rule_t *rule = &g_snapshot.rules[r];
        if (!rule->enabled) continue;

        /* Évaluer chaque condition individuellement */
        bool any_triggered_for_delta = false;
        for (uint8_t i = 0; i < rule->n_conditions; ++i) {
            bool was_triggered = false;
            cond_results[i] = eval_condition(&rule->conditions[i],
                                             r, i, &was_triggered);
            (void)any_triggered_for_delta;
        }

        /* Évaluer le pattern logique global */
        bool now_true = Pattern_Evaluate(rule->pattern_rpn,
                                         rule->n_tokens,
                                         cond_results);

        /* Tirer les triggers à chaque tick où le pattern est vrai */
        if (now_true) {
            re_pattern_true++;
            fire_triggers(rule, snap);

            /* Mettre à jour last_trig_val pour PRIM_DELTA_LAST */
            for (uint8_t i = 0; i < rule->n_conditions; ++i) {
                const Condition_t *c = &rule->conditions[i];
                if (c->fn_a == PRIM_DELTA_LAST && cond_results[i]) {
                    float current;
                    if (History_GetValue(c->uid_a, 0, &current)) {
                        g_last_trig_val[r][i] = current;
                    }
                }
            }
        }

        g_was_true[r] = now_true;
        /* fire_blocked n'a plus de sens sans détection de front */
    }
}

/* ============================================================
 *  Mise à jour de l'historique pour chaque mesure du snapshot
 * ============================================================ */
static void update_history(const Snapshot_t *snap)
{
    for (uint8_t i = 0; i < snap->count; ++i) {
        const Measurement_t *m = &snap->measures[i];
        if (m->status != 0) continue;   /* on n'historiise pas les erreurs */
        History_Push(m->uid, m->value, snap->timestamp_ms);
    }
}

/* ============================================================
 *  Évaluation d'une condition atomique
 * ============================================================ */
static bool eval_condition(const Condition_t *c, uint8_t rule_idx,
                           uint8_t cond_idx, bool *was_triggered)
{
    (void)was_triggered;

    /* Évalue le LHS = coeff_a * fn_a(uid_a) [arith coeff_b * fn_b(uid_b)] + offset */
    float a, b = 0.0f;
    if (!Primitive_Eval(c->fn_a, c->uid_a, c->window_a, c->param_a,
                        g_last_trig_val[rule_idx][cond_idx], &a)) {
        return false;
    }
    re_last_lux = a;   /* trace la dernière valeur lue (uid_a) */
    a *= c->coeff_a;

    if (c->arith != ARITH_NONE && c->fn_b != PRIM_NONE) {
        if (!Primitive_Eval(c->fn_b, c->uid_b, c->window_b, c->param_b,
                            NAN, &b)) {
            return false;
        }
        b *= c->coeff_b;
    }

    float lhs = a;
    switch (c->arith) {
        case ARITH_ADD: lhs = a + b; break;
        case ARITH_SUB: lhs = a - b; break;
        default: break;
    }
    lhs += c->offset;

    /* Comparaison */
    bool result;
    switch (c->cmp) {
        case CMP_GT:   result = lhs >  c->rhs; break;
        case CMP_LT:   result = lhs <  c->rhs; break;
        case CMP_GE:   result = lhs >= c->rhs; break;
        case CMP_LE:   result = lhs <= c->rhs; break;
        case CMP_NEQ:  result = fabsf(lhs - c->rhs) > c->tolerance; break;
        case CMP_EQ:   result = fabsf(lhs - c->rhs) <= c->tolerance; break;
        case CMP_NEAR: result = fabsf(lhs - c->rhs) <= c->tolerance; break;
        default:       result = false; break;
    }
    if (result) re_cond_true_count++;
    return result;
}

/* ============================================================
 *  Publication des triggers — structure propre par queue
 *
 *  TRIG_LOG    → LogCommand_t   via osMessageQueuePut(queue_log)
 *  TRIG_STREAM → TxCommand_t   via tx_post_live_data()
 *  TRIG_ACTION → ActionCommand_t via action_post_gpio_write() etc.
 *
 *  Le snapshot courant est passé pour lire les valeurs des UIDs.
 * ============================================================ */

/* Helper : trouve la mesure d'un uid dans le snapshot courant */
static const Measurement_t *find_measure(const Snapshot_t *snap, uint8_t uid)
{
    for (uint8_t i = 0; i < snap->count; ++i)
        if (snap->measures[i].uid == uid) return &snap->measures[i];
    return NULL;
}

/* --- TRIG_LOG → LogCommand_t dans queue_log --- */
static void fire_log(const Trigger_t *trig, const Rule_t *rule,
                     const Snapshot_t *snap, uint32_t ts)
{
    LogCommand_t cmd;
    memset(&cmd, 0, sizeof(cmd));
    cmd.type               = CMD_LOG;
    cmd.u.log.rule_id      = rule->rule_id;
    cmd.u.log.timestamp_ms = ts;

    uint8_t n = 0;
    for (uint8_t i = 0; i < trig->data.payload.n_uids
                        && n < MAX_CHANNELS_PER_RULE; ++i) {
        uint8_t uid = trig->data.payload.uids[i];
        const Measurement_t *m = find_measure(snap, uid);
        if (m == NULL) continue;
        cmd.u.log.channels[n].channel_id = uid;
        cmd.u.log.channels[n].value      = m->value;
        cmd.u.log.channels[n].status     = (uint8_t)m->status;
        n++;
    }
    cmd.u.log.num_channels = n;

    if (n > 0 && queue_log != NULL)
        osMessageQueuePut(queue_log, &cmd, 0, 0);
}

/* --- TRIG_STREAM → TxCommand_t (TX_LIVE_DATA) via tx_post_live_data() --- */
static void fire_stream(const Trigger_t *trig, const Rule_t *rule,
                        const Snapshot_t *snap, uint32_t ts)
{
    /* Construire le tableau ChannelReading_t attendu par tx_post_live_data */
    ChannelReading_t readings[MAX_CHANNELS_PER_RULE];
    uint8_t n = 0;

    for (uint8_t i = 0; i < trig->data.payload.n_uids
                        && n < MAX_CHANNELS_PER_RULE; ++i) {
        uint8_t uid = trig->data.payload.uids[i];
        const Measurement_t *m = find_measure(snap, uid);
        if (m == NULL) continue;
        readings[n].channel_id = uid;
        readings[n].value      = m->value;
        readings[n].status     = (uint8_t)m->status;
        n++;
    }

    if (n > 0)
        tx_post_live_data(rule->rule_id, ts, n, readings);
}

/* --- TRIG_ACTION → ActionCommand_t via action_post_*() ---
 *
 *  Le champ action_code dans Hardware_Action_t détermine le type :
 *    0 = ACT_GPIO_WRITE  LOW
 *    1 = ACT_GPIO_WRITE  HIGH
 *    2 = ACT_GPIO_TOGGLE
 *    3 = ACT_GPIO_BLINK  (param = period_ms, count = 3 par défaut)
 *    4 = ACT_BUZZER_BEEP (param = on_ms)
 *    5 = ACT_LCD_ALERT   INFO
 *    6 = ACT_LCD_ALERT   WARN
 *    7 = ACT_LCD_ALERT   ERROR
 *
 *  pin_or_servo_id est mappé sur les sorties GPIO de board_config.h :
 *    1 = ACTION_PIN1 (PD0)
 *    2 = ACTION_PIN2 (PD1)
 *    3 = ACTION_PIN3 (PD3)
 *    4 = ACTION_PIN4 (PD4)
 * ============================================================ */
static GPIO_TypeDef *action_port(uint8_t pin_id)
{
    switch (pin_id) {
        case 1: return ACTION_PIN1_PORT;
        case 2: return ACTION_PIN2_PORT;
        case 3: return ACTION_PIN3_PORT;
        case 4: return ACTION_PIN4_PORT;
        default: return NULL;
    }
}

static uint16_t action_pin(uint8_t pin_id)
{
    switch (pin_id) {
        case 1: return ACTION_PIN1_PIN;
        case 2: return ACTION_PIN2_PIN;
        case 3: return ACTION_PIN3_PIN;
        case 4: return ACTION_PIN4_PIN;
        default: return 0;
    }
}

static void fire_action(const Trigger_t *trig, uint32_t ts)
{
    (void)ts;
    const Hardware_Action_t *a = &trig->data.action;
    GPIO_TypeDef *port = action_port(a->pin_or_servo_id);
    uint16_t      pin  = action_pin(a->pin_or_servo_id);

    ActionCommand_t cmd;
    memset(&cmd, 0, sizeof(cmd));

    switch (a->action_code) {
        case 0:  /* GPIO LOW */
            cmd.type        = ACT_GPIO_WRITE;
            cmd.u.gpio.port = port;
            cmd.u.gpio.pin  = pin;
            cmd.u.gpio.state = 0;
            break;
        case 1:  /* GPIO HIGH */
            cmd.type        = ACT_GPIO_WRITE;
            cmd.u.gpio.port = port;
            cmd.u.gpio.pin  = pin;
            cmd.u.gpio.state = 1;
            break;
        case 2:  /* GPIO TOGGLE */
            cmd.type        = ACT_GPIO_TOGGLE;
            cmd.u.gpio.port = port;
            cmd.u.gpio.pin  = pin;
            break;
        case 3:  /* GPIO BLINK — param = period_ms, count = 3 */
            cmd.type             = ACT_GPIO_BLINK;
            cmd.u.gpio.port      = port;
            cmd.u.gpio.pin       = pin;
            cmd.u.gpio.count     = 3;
            cmd.u.gpio.period_ms = a->param;
            break;
        case 4:  /* BUZZER BEEP — param = on_ms */
            cmd.type            = ACT_BUZZER_BEEP;
            cmd.u.buzzer.freq_hz = 1000;
            cmd.u.buzzer.on_ms  = a->param;
            cmd.u.buzzer.off_ms = a->param;
            cmd.u.buzzer.count  = 1;
            break;
        case 5:  /* LCD ALERT INFO */
            cmd.type = ACT_LCD_ALERT;
            cmd.u.lcd_alert.level = ALERT_INFO;
            strncpy(cmd.u.lcd_alert.title,   "Rule",          ACTION_MAX_LABEL - 1);
            strncpy(cmd.u.lcd_alert.message, "Condition met", ACTION_MAX_TEXT  - 1);
            cmd.u.lcd_alert.timeout_ms = a->param;
            break;
        case 6:  /* LCD ALERT WARN */
            cmd.type = ACT_LCD_ALERT;
            cmd.u.lcd_alert.level = ALERT_WARN;
            strncpy(cmd.u.lcd_alert.title,   "Rule",          ACTION_MAX_LABEL - 1);
            strncpy(cmd.u.lcd_alert.message, "Condition met", ACTION_MAX_TEXT  - 1);
            cmd.u.lcd_alert.timeout_ms = a->param;
            break;
        case 7:  /* LCD ALERT ERROR */
            cmd.type = ACT_LCD_ALERT;
            cmd.u.lcd_alert.level = ALERT_ERROR;
            strncpy(cmd.u.lcd_alert.title,   "Rule",          ACTION_MAX_LABEL - 1);
            strncpy(cmd.u.lcd_alert.message, "Condition met", ACTION_MAX_TEXT  - 1);
            cmd.u.lcd_alert.timeout_ms = a->param;
            break;
        default:
            return;  /* action_code inconnu — ne rien poster */
    }

    if (queue_action != NULL)
        osMessageQueuePut(queue_action, &cmd, 0, 0);
}
int re_fire_trigger_entred=0;
static void fire_triggers(const Rule_t *rule, const Snapshot_t *snap)
{
    uint32_t ts = osKernelGetTickCount();
    re_fire_trigger_entred++;
    for (uint8_t i = 0; i < rule->n_triggers; ++i) {

        const Trigger_t *trig = &rule->triggers[i];
        switch (trig->type) {
        	case TRIG_ACTION: fire_action(trig, ts);            break;
            case TRIG_LOG:    fire_log(trig, rule, snap, ts);     break;
            case TRIG_STREAM: fire_stream(trig, rule, snap, ts);  break;

            default: break;
        }
    }

}

/* ============================================================
 *  Helper — recherche d'une mesure dans un snapshot par UID
 * ============================================================ */
static const Measurement_t *find_in_snapshot(const Snapshot_t *snap, uint8_t uid)
{
    return find_measure(snap, uid);
}
