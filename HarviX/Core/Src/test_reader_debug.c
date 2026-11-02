/* ============================================================
 *  test_reader_debug.c — Test du reader via le debugger CubeIDE
 *
 *  CONCEPT :
 *    Pas de printf, pas de desktop. Tout se fait via le debugger :
 *    - Live Expressions pour voir les mesures en temps réel
 *    - Modifier des variables pour assigner/retirer des capteurs
 *    - Observer le snapshot qui se remplit à chaque tick
 *
 *  COMMENT UTILISER :
 *
 *  1. Compilez et flashez en mode Debug (Run → Debug As)
 *
 *  2. Dans le panneau "Live Expressions" (Window → Show View →
 *     Live Expressions), ajoutez ces variables :
 *       dbg_snap           → dernier snapshot complet
 *       dbg_snap.count     → nombre de mesures
 *       dbg_snap.measures  → tableau des mesures
 *       dbg_status         → état du système
 *       dbg_tick_count     → compteur de snapshots reçus
 *       dbg_last_error     → dernier code d'erreur
 *
 *  3. Lancez l'exécution (F8 = Resume)
 *     → Les capteurs configurés dans la table initiale commencent
 *       à produire des mesures
 *     → dbg_snap se met à jour toutes les secondes
 *
 *  4. Pour modifier la config EN TEMPS RÉEL :
 *     a. Mettez en pause (Suspend)
 *     b. Dans "Variables" ou "Expressions", modifiez dbg_cmd :
 *          dbg_cmd = 1  → recharger la table dbg_config
 *          dbg_cmd = 2  → démarrer l'acquisition
 *          dbg_cmd = 3  → arrêter l'acquisition
 *          dbg_cmd = 4  → effacer tous les capteurs
 *          dbg_cmd = 10 → assigner dbg_pending_sensor
 *          dbg_cmd = 11 → effacer le slot dbg_pending_slot_id
 *     c. Reprenez l'exécution (Resume)
 *     → Le commander de test voit dbg_cmd != 0, exécute l'action,
 *       puis remet dbg_cmd à 0
 *
 *  5. Pour ajouter un capteur manuellement :
 *     a. Pause
 *     b. Remplissez dbg_pending_sensor :
 *          dbg_pending_sensor.slot_id     = 6
 *          dbg_pending_sensor.model       = 5  (SENSOR_LM75)
 *          dbg_pending_sensor.quantity    = 0  (QUANTITY_TEMPERATURE)
 *          dbg_pending_sensor.i2c_address = 0x48
 *     c. Mettez dbg_cmd = 10
 *     d. Resume
 *     → Le capteur apparaît dans les snapshots suivants
 *
 * ============================================================ */

#include "reader.h"
#include "sensor_types.h"
#include "board_config.h"
#include "cmsis_os.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>

/* ============================================================
 *  Queue snapshots
 * ============================================================ */
osMessageQueueId_t queue_snapshots_dbg;

/* ============================================================
 *  VARIABLES GLOBALES DE DEBUG
 *
 *  Toutes sont `volatile` pour que :
 *    - Le compilateur ne les optimise pas
 *    - Le debugger puisse les lire/écrire en temps réel
 *    - Les modifications depuis le debugger soient prises en compte
 *
 *  AJOUTEZ-LES DANS "Live Expressions" de CubeIDE !
 * ============================================================ */

/* --- Dernier snapshot reçu (mis à jour automatiquement) --- */
volatile Snapshot_t   dbg_snap;

/* --- Compteurs et état --- */
volatile uint32_t     dbg_tick_count   = 0;    /* nombre de snapshots reçus   */
volatile int32_t      dbg_last_error   = 0;    /* dernier code erreur Reader  */
volatile uint8_t      dbg_last_uid     = 0;    /* dernier uid attribué        */
volatile uint8_t      dbg_n_devices    = 0;    /* nombre de devices actifs    */

/* --- État système (lisible dans le debugger) --- */
volatile uint8_t      dbg_status       = 0;
/*  0 = IDLE (pas d'acquisition)
 *  1 = RUNNING (acquisition en cours)
 *  2 = ERROR
 */

/* --- Commande debug (écrire depuis le debugger) --- */
volatile uint8_t      dbg_cmd          = 0;
/*  0  = rien à faire
 *  1  = recharger la table dbg_config[]
 *  2  = démarrer l'acquisition
 *  3  = arrêter l'acquisition
 *  4  = effacer tous les capteurs
 *  10 = assigner dbg_pending_sensor
 *  11 = effacer le slot dbg_pending_slot_id
 */

/* --- Capteur en attente d'assignation (remplir depuis le debugger) --- */
volatile struct {
    uint8_t  slot_id;        /* 1..14                          */
    uint8_t  model;          /* Sensor_Model_t (voir enum)     */
    uint8_t  quantity;       /* Physical_Quantity_t (voir enum) */
    uint8_t  i2c_address;   /* 0 si pas I2C                   */
} dbg_pending_sensor = {0, 0, 0, 0};

/* --- Slot à effacer (écrire depuis le debugger) --- */
volatile uint8_t      dbg_pending_slot_id = 0;

/* --- Période d'acquisition en ms (modifiable depuis le debugger) --- */
volatile uint32_t     dbg_period_ms    = 1000;

/* ============================================================
 *  Table de config initiale — chargée au boot ou sur dbg_cmd=1
 *
 *  Modifiez cette table pour changer la config de départ.
 *  Format : { slot_id, model, quantity, i2c_address }
 *  Terminez par { 0, 0, 0, 0 } (sentinelle).
 *
 *  Rappel des enums :
 *    Sensor_Model_t :
 *      SENSOR_BMP280=1, SENSOR_AHT20=2, SENSOR_BH1750=3,
 *      SENSOR_INA219=4, SENSOR_LM75=5, SENSOR_NTC=6,
 *      SENSOR_DHT11=7, SENSOR_DHT22=8, SENSOR_DS18B20=9
 *
 *    Physical_Quantity_t :
 *      QUANTITY_TEMPERATURE=0, QUANTITY_PRESSURE=1,
 *      QUANTITY_HUMIDITY=2, QUANTITY_VOLTAGE=3,
 *      QUANTITY_CURRENT=4, QUANTITY_LIGHT_LUX=5, QUANTITY_POWER=6
 *
 *    Slots :
 *      1-3   = SPI1       8-12 = ADC
 *      4-5   = SPI4       13-14 = Digital
 *      6     = I2C2
 *      7     = I2C3
 * ============================================================ */

#define MAX_INITIAL_CONFIG  7

typedef struct {
    uint8_t slot_id;
    uint8_t model;
    uint8_t quantity;
    uint8_t i2c_address;
} Debug_Config_Entry_t;

volatile Debug_Config_Entry_t dbg_config[MAX_INITIAL_CONFIG] = {
    /* slot,  model,         quantity,               i2c_addr */

    {  8,     6 ,  1 ,        0x00 },  /* I2C2 slot 6     */
    {  9,     6,           1  ,                       0x00 },  /* sentinelle     */
    {  0,     0,             0,                       0x00 },
    {  0,     0,             0,                       0x00 },
    {  0,     0,             0,                       0x00 },
    {  0,     0,             0,                       0x00 },
    {  0,     0,             0,                       0x00 },
};

/* ============================================================
 *  Mesures individuelles extraites du snapshot
 *  (plus facile à lire dans Live Expressions que snap.measures[0])
 * ============================================================ */

#define MAX_DBG_MEASURES  7

volatile struct {
    uint8_t  uid;
    uint8_t  quantity;
    int8_t   status;
    float    value;
} dbg_measures[MAX_DBG_MEASURES];

volatile uint8_t dbg_measures_count = 0;

/* ============================================================
 *  Charger la table dbg_config dans le Reader
 * ============================================================ */

static void load_config_table(void)
{
    Sensor_Params_t params;
    uint8_t uid;
    int rc;

    dbg_n_devices = 0;

    for (int i = 0; i < MAX_INITIAL_CONFIG; ++i) {
        volatile Debug_Config_Entry_t *entry = &dbg_config[i];

        /* Sentinelle : slot_id = 0 → fin de la table */
        if (entry->slot_id == 0) break;

        memset(&params, 0, sizeof(params));
        params.i2c_address = entry->i2c_address;

        rc = Reader_AssignSensor(
            entry->slot_id,
            (Sensor_Model_t)entry->model,
            (Physical_Quantity_t)entry->quantity,
            &params,
            &uid
        );

        if (rc == READER_OK) {
            dbg_last_uid   = uid;
            dbg_last_error = 0;
            dbg_n_devices++;
        } else {
            dbg_last_error = rc;
        }
    }
}

/* ============================================================
 *  Traiter une commande debug (dbg_cmd)
 * ============================================================ */

static void process_debug_command(void)
{
    uint8_t cmd = dbg_cmd;
    if (cmd == 0) return;

    Sensor_Params_t params;
    uint8_t uid;
    int rc;

    switch (cmd) {
        case 1: /* Recharger la table config */
            Reader_ClearAll();
            load_config_table();
            break;

        case 2: /* Démarrer l'acquisition */
            Reader_SetPeriod(dbg_period_ms);
            Reader_StartAcquisition();
            dbg_status = 1;
            break;

        case 3: /* Arrêter l'acquisition */
            Reader_StopAcquisition();
            dbg_status = 0;
            break;

        case 4: /* Effacer tous les capteurs */
            Reader_StopAcquisition();
            Reader_ClearAll();
            dbg_n_devices = 0;
            dbg_status = 0;
            break;

        case 10: /* Assigner le capteur pending */
            memset(&params, 0, sizeof(params));
            params.i2c_address = dbg_pending_sensor.i2c_address;

            rc = Reader_AssignSensor(
                dbg_pending_sensor.slot_id,
                (Sensor_Model_t)dbg_pending_sensor.model,
                (Physical_Quantity_t)dbg_pending_sensor.quantity,
                &params,
                &uid
            );

            if (rc == READER_OK) {
                dbg_last_uid   = uid;
                dbg_last_error = 0;
                dbg_n_devices++;
            } else {
                dbg_last_error = rc;
            }
            break;

        case 11: /* Effacer un slot */
            rc = Reader_ClearSlot(dbg_pending_slot_id);
            dbg_last_error = rc;
            if (rc == READER_OK && dbg_n_devices > 0) {
                dbg_n_devices--;
            }
            break;

        default:
            dbg_last_error = -99; /* commande inconnue */
            break;
    }

    /* Remettre à 0 — le debugger verra 0 au prochain refresh */
    dbg_cmd = 0;
}

/* ============================================================
 *  Tâche moniteur — consomme les snapshots, met à jour les
 *  variables de debug, et vérifie les commandes du debugger.
 * ============================================================ */

static void debug_monitor_task(void *arg)
{
    (void)arg;
    Snapshot_t snap;

    for (;;) {
        /* Vérifier si le debugger a écrit une commande */
        process_debug_command();

        /* Attendre un snapshot (timeout 100ms pour checker les cmds) */
        if (osMessageQueueGet(queue_snapshots_dbg, &snap, NULL, 100) == osOK) {
            /* Copier dans la variable debug volatile */
            memcpy((void *)&dbg_snap, &snap, sizeof(Snapshot_t));
            dbg_tick_count++;

            /* Extraire les mesures individuelles pour faciliter
             * la lecture dans Live Expressions */
            dbg_measures_count = (snap.count <= MAX_DBG_MEASURES)
                                 ? snap.count : MAX_DBG_MEASURES;

            for (uint8_t i = 0; i < dbg_measures_count; ++i) {
                dbg_measures[i].uid      = snap.measures[i].uid;
                dbg_measures[i].quantity = (uint8_t)snap.measures[i].quantity;
                dbg_measures[i].status   = snap.measures[i].status;
                dbg_measures[i].value    = snap.measures[i].value;
            }
        }
    }
}

/* ============================================================
 *  Point d'entrée — à appeler depuis main()
 *
 *  Exemple d'utilisation dans main.c :
 *
 *    int main(void) {
 *        HAL_Init();
 *        SystemClock_Config();
 *        MX_GPIO_Init();
 *        MX_I2C2_Init();       // pour BH1750
 *        MX_ADC1_Init();       // pour NTC
 *        // ... autres inits si nécessaire ...
 *
 *        osKernelInitialize();
 *        test_debug_main();
 *        osKernelStart();
 *        for (;;) {}
 *    }
 * ============================================================ */

void test_debug_main(void)
{
    /* 1. Créer la queue */
    queue_snapshots_dbg = osMessageQueueNew(3, sizeof(Snapshot_t), NULL);

    /* 2. Init du lecteur */
    Reader_Init();

    /* 3. Charger la config initiale depuis dbg_config[] */
    load_config_table();

    /* 4. Configurer la période */
    Reader_SetPeriod(dbg_period_ms);

    /* 5. Démarrer la tâche moniteur */
    const osThreadAttr_t attr = {
        .name       = "dbg_mon",
        .stack_size = 2048,
        .priority   = osPriorityNormal,
    };
    osThreadNew(debug_monitor_task, NULL, &attr);

    /* 6. Démarrer le lecteur */
    Reader_StartTask();

    /* 7. Démarrer l'acquisition automatiquement */
    Reader_StartAcquisition();
    dbg_status = 1;

    /* Prêt — le debugger peut maintenant :
     *   - Observer dbg_snap, dbg_measures, dbg_tick_count
     *   - Modifier dbg_cmd pour contrôler le système
     *   - Modifier dbg_config[] puis dbg_cmd=1 pour recharger
     *   - Modifier dbg_period_ms puis dbg_cmd=2 pour changer la période
     */
}
