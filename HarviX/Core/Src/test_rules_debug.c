/* ============================================================
 *  test_rules_debug.c — Test du moteur de règles
 *
 *  ARCHITECTURE :
 *    reader.c             →  publie dans queue_snapshots + queue_snapshots_dbg
 *    test_reader_debug.c  →  consomme queue_snapshots_dbg (moniteur reader)
 *    rules_engine.c       →  consomme queue_snapshots     (évaluation)
 *    test_rules_debug.c   →  définit les queues de sortie + les consomme
 *
 *  DANS main.c :
 *    osKernelInitialize();
 *    test_debug_main();        // reader — EN PREMIER
 *    test_rules_debug_main();  // moteur de règles
 *    osKernelStart();
 *
 *  LIVE EXPRESSIONS :
 *    dbg_trace              → diagnostic d'init et d'évaluation
 *    dbg_rule_fired_count   → total déclenchements
 *    dbg_log_count          → messages LOG reçus
 *    dbg_stream_count       → messages STREAM reçus
 *    dbg_action_count       → messages ACTION reçus
 *    dbg_last_log_msg       → dernier message LOG
 *    dbg_lux_threshold      → seuil modifiable en live
 *    dbg_rules_cmd          → commande debug
 *
 *  COMMANDES :
 *    1 = recharger la règle avec dbg_lux_threshold
 *    2 = activer l'évaluation
 *    3 = désactiver l'évaluation
 *    4 = reset compteurs
 * ============================================================ */

#include "rules_engine.h"
#include "action_queue.h"
#include "rules_store.h"
#include "history_buffer.h"
#include "rule_types.h"
#include "sensor_types.h"
#include "log_queue_types.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>
#include <math.h>

/* ============================================================
 *  queue_snapshots — définie ici, utilisée par :
 *    - reader.c (extern, publie)
 *    - rules_engine.c (extern, consomme)
 * ============================================================ */
osMessageQueueId_t queue_snapshots;

/* ============================================================
 *  Queues de sortie — définies ici, extern dans rules_engine.c
 * ============================================================ */
osMessageQueueId_t queue_log;
osMessageQueueId_t queue_tx;
osMessageQueueId_t queue_action;

/* ============================================================
 *  Types des messages de sortie
 *  DOIVENT correspondre exactement à ceux de rules_engine.c
 * ============================================================ */

/* Stream_Msg_t — même struct que dans rules_engine.c */
typedef struct {
    uint8_t  rule_id;
    uint32_t timestamp_ms;
    uint8_t  n_uids;
    struct {
        uint8_t uid;
        float   value;
        int8_t  status;
    } entries[MAX_UIDS_PER_TRIGGER];
} Stream_Msg_t;

/* Action_Msg_t — même struct que dans rules_engine.c */
typedef struct {
    uint8_t  pin_or_servo_id;
    uint8_t  action_code;
    uint16_t param;
    uint32_t timestamp_ms;
} Action_Msg_t;

/* ============================================================
 *  VARIABLES DE DEBUG
 * ============================================================ */
volatile uint32_t      dbg_rule_fired_count = 0;
volatile uint32_t      dbg_log_count        = 0;
volatile uint32_t      dbg_stream_count     = 0;
volatile uint32_t      dbg_action_count     = 0;

volatile LogCommand_t  dbg_last_log_msg;
volatile Stream_Msg_t  dbg_last_stream_msg;
volatile ActionCommand_t  dbg_last_action_msg;

volatile float         dbg_lux_threshold = 100.0f;
volatile uint8_t       dbg_rules_cmd     = 0;

/* ============================================================
 *  Diagnostic — trace chaque étape
 * ============================================================ */
volatile struct {
    uint8_t  init_step;          /* 0→7 progression de l'init        */
    int8_t   rule_load_rc;       /* retour de RulesStore_Add         */
    uint8_t  uid_used;           /* uid passé à la condition         */
    uint32_t eval_entered;       /* process_snapshot() appelé        */
    uint32_t cond_eval_count;    /* eval_condition() → true          */
    float    last_lux_seen;      /* dernière valeur lue par le moteur*/
    uint32_t pattern_true_count; /* Pattern_Evaluate → true          */
} dbg_trace = {0};

/* ============================================================
 *  UID du capteur — exposé par test_reader_debug.c
 * ============================================================ */
extern volatile uint8_t dbg_last_uid;

/* ============================================================
 *  Compteurs internes du moteur — exposés depuis rules_engine.c
 * ============================================================ */
extern uint32_t re_eval_entered;
extern uint32_t re_cond_true_count;
extern float    re_last_lux;
extern uint32_t re_pattern_true;

#define TEST_RULE_ID  1

/* ============================================================
 *  Construire et charger la règle
 *
 *  Règle : SI current(bh1750) > seuil ALORS LOG + STREAM
 *  Pattern : "c1"
 * ============================================================ */
int comparateur=0;
static void load_rule(void)
{
    RulesStore_ClearAll();

    Rule_t rule;
    memset(&rule, 0, sizeof(Rule_t));

    rule.rule_id  = TEST_RULE_ID;
    rule.priority = 10;
    rule.enabled  = true;

    /* --- Condition c1 : CURRENT(uid) > dbg_lux_threshold --- */
    rule.n_conditions = 1;

    rule.conditions[0].fn_a      = PRIM_CURRENT;
    rule.conditions[0].uid_a     = 1;
    rule.conditions[0].window_a  = 1;
    rule.conditions[0].coeff_a   = 1.0f;
    rule.conditions[0].param_a   = 0.0f;
    rule.conditions[0].offset    = 0.0f;

    rule.conditions[0].arith     = ARITH_NONE;
    rule.conditions[0].fn_b      = PRIM_NONE;
    rule.conditions[0].uid_b     = 0;

    rule.conditions[0].cmp       = comparateur;
    rule.conditions[0].rhs       = dbg_lux_threshold;
    rule.conditions[0].tolerance = 0.0f;

    /* --- Pattern : "c1" → RPN = [COND(0)] --- */
    rule.n_tokens                  = 1;
    rule.pattern_rpn[0].type       = TOK_COND;
    rule.pattern_rpn[0].cond_index = 0;

    /* --- Trigger 1 : LOG (enregistrer la valeur) --- */
    rule.triggers[0].type                 = TRIG_LOG;
    rule.triggers[0].data.payload.n_uids  = 2;
    rule.triggers[0].data.payload.uids[0] = 1;
    rule.triggers[0].data.payload.uids[1] = 2;
    /* --- Trigger 2 : STREAM (envoyer vers desktop) --- */
    rule.triggers[1].type                 = TRIG_STREAM;
    rule.triggers[1].data.payload.n_uids  = 1;
    rule.triggers[1].data.payload.uids[0] = dbg_last_uid;
    /*---- trigger 3 : avtion ---*/
    rule.triggers[2].type=TRIG_ACTION;
    rule.triggers[2].data.action.pin_or_servo_id=1;
    rule.triggers[2].data.action.action_code=1;
    rule.triggers[2].data.action.param=0;

    rule.triggers[3].type=TRIG_ACTION;
    rule.triggers[3].data.action.pin_or_servo_id=2;
    rule.triggers[3].data.action.action_code=1;
    rule.triggers[3].data.action.param=0;


    /* --- n_triggers = nombre de triggers RÉELLEMENT configurés --- */
    rule.n_triggers = 4;

    dbg_trace.uid_used     = dbg_last_uid;
    dbg_trace.rule_load_rc = (int8_t)RulesStore_Add(&rule);



    rule.rule_id  = 2;
    rule.priority = 10;
    rule.enabled  = true;

    /* --- Condition c1 : CURRENT(uid) > dbg_lux_threshold --- */
    rule.n_conditions = 1;

    rule.conditions[0].fn_a      = PRIM_CURRENT;
    rule.conditions[0].uid_a     = 1;
    rule.conditions[0].window_a  = 1;
    rule.conditions[0].coeff_a   = 1.0f;
    rule.conditions[0].param_a   = 0.0f;
    rule.conditions[0].offset    = 0.0f;

    rule.conditions[0].arith     = ARITH_NONE;
    rule.conditions[0].fn_b      = PRIM_NONE;
    rule.conditions[0].uid_b     = 0;

    rule.conditions[0].cmp       = 1-comparateur;
    rule.conditions[0].rhs       = dbg_lux_threshold;
    rule.conditions[0].tolerance = 0.0f;

    /* --- Pattern : "c1" → RPN = [COND(0)] --- */
    rule.n_tokens                  = 1;
    rule.pattern_rpn[0].type       = TOK_COND;
    rule.pattern_rpn[0].cond_index = 0;


    /*---- trigger 3 : avtion ---*/
    rule.triggers[0].type=TRIG_ACTION;
    rule.triggers[0].data.action.pin_or_servo_id=1;
    rule.triggers[0].data.action.action_code=0;
    rule.triggers[0].data.action.param=0;

    rule.triggers[1].type=TRIG_ACTION;
    rule.triggers[1].data.action.pin_or_servo_id=2;
    rule.triggers[1].data.action.action_code=0;
    rule.triggers[1].data.action.param=0;

    /* --- n_triggers = nombre de triggers RÉELLEMENT configurés --- */
    rule.n_triggers = 2;

    dbg_trace.uid_used     = dbg_last_uid;
    dbg_trace.rule_load_rc = (int8_t)RulesStore_Add(&rule);
}

/* ============================================================
 *  Commandes debug
 * ============================================================ */
static void process_rules_cmd(void)
{
    uint8_t cmd = dbg_rules_cmd;
    if (cmd == 0) return;

    switch (cmd) {
        case 1: load_rule(); break;
        case 2: RulesEngine_StartEvaluation(); break;
        case 3: RulesEngine_StopEvaluation(); break;
        case 4:
            dbg_rule_fired_count = 0;
            dbg_log_count        = 0;
            dbg_stream_count     = 0;
            dbg_action_count     = 0;
            re_eval_entered      = 0;
            re_cond_true_count   = 0;
            re_pattern_true      = 0;
            break;
        default: break;
    }
    dbg_rules_cmd = 0;
}

/* ============================================================
 *  Tâche moniteur — consomme les queues de sortie
 * ============================================================ */
static void rules_monitor_task(void *arg)
{
    (void)arg;
    LogCommand_t log_msg;
    Stream_Msg_t stream_msg;
    Action_Msg_t action_msg;

    for (;;) {
        process_rules_cmd();

        /* Miroir des compteurs du moteur */
        dbg_trace.eval_entered       = re_eval_entered;
        dbg_trace.cond_eval_count    = re_cond_true_count;
        dbg_trace.last_lux_seen      = re_last_lux;
        dbg_trace.pattern_true_count = re_pattern_true;

        /* Consommer queue_log */
        if (queue_log != NULL &&
            osMessageQueueGet(queue_log, &log_msg, NULL, 0) == osOK) {
            memcpy((void *)&dbg_last_log_msg, &log_msg, sizeof(LogCommand_t));
            dbg_log_count++;
            dbg_rule_fired_count++;
        }

        /* Consommer queue_tx */
        if (queue_tx != NULL &&
            osMessageQueueGet(queue_tx, &stream_msg, NULL, 0) == osOK) {
            memcpy((void *)&dbg_last_stream_msg, &stream_msg, sizeof(Stream_Msg_t));
            dbg_stream_count++;
        }

        /* Consommer queue_action */
      /*  if (queue_action != NULL &&
            osMessageQueueGet(queue_action, &action_msg, NULL, 0) == osOK) {
            memcpy((void *)&dbg_last_action_msg, &action_msg, sizeof(ActionCommand_t));
            dbg_action_count++;
        }*/

        osDelay(50);
    }
}

/* ============================================================
 *  Point d'entrée
 * ============================================================ */
void test_rules_debug_main(void)
{
    /* 1. Créer les queues — TAILLES CORRECTES */
    queue_snapshots = osMessageQueueNew(3, sizeof(Snapshot_t), NULL);
    queue_log       = osMessageQueueNew(8, sizeof(LogCommand_t), NULL);
    queue_tx    = osMessageQueueNew(8, sizeof(Stream_Msg_t), NULL);
    queue_action = osMessageQueueNew(8, sizeof(ActionCommand_t),NULL);


    dbg_trace.init_step = 1;

    /* 2. Init store + history */
    RulesStore_Init();
    History_Init();
    dbg_trace.init_step = 2;

    /* 3. Charger la règle */
    load_rule();
    dbg_trace.init_step = 3;

    /* 4. Init moteur */
    RulesEngine_Init();
    dbg_trace.init_step = 4;

    /* 5. Tâche moniteur */
    const osThreadAttr_t attr = {
        .name       = "rules_mon",
        .stack_size = 2048,
        .priority   = osPriorityNormal,
    };
    osThreadNew(rules_monitor_task, NULL, &attr);
    dbg_trace.init_step = 5;

    /* 6. Démarrer le moteur */
    RulesEngine_StartTask();
    dbg_trace.init_step = 6;

    /* 7. Activer l'évaluation */
    RulesEngine_StartEvaluation();
    dbg_trace.init_step = 7;
}
