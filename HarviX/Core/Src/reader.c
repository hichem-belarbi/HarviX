#include "reader.h"
#include "board_config.h"
#include "sensor_dispatch.h"
#include "cmsis_os2.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>

/* Queue snapshots — définie dans main.c ou freertos.c */
extern osMessageQueueId_t queue_snapshots;
extern osMessageQueueId_t queue_snapshots_dbg;
/* ============================================================
 *  État global du module
 * ============================================================ */
static Slot_t          g_slots[NB_SLOTS];

/* Un mutex par bus physique configuré */
static osMutexId_t     g_mutex_i2c2;
static osMutexId_t     g_mutex_adc1;

static volatile bool     g_acquisition_running = false;
static volatile uint32_t g_period_ms = 1000;
static osThreadId_t      g_reader_task;
static uint8_t           g_next_uid = 1;

/* ============================================================
 *  Prototypes internes
 * ============================================================ */
static Slot_t         *find_slot(uint8_t slot_id);
static void            init_slots_from_board(void);
static osMutexId_t     get_bus_mutex(const Slot_t *slot);
static void            reader_task_fn(void *arg);

/* ============================================================
 *  Initialisation
 * ============================================================ */

void Reader_Init(void)
{
    memset(g_slots, 0, sizeof(g_slots));
    init_slots_from_board();

    const osMutexAttr_t a_i2c2 = { .name = "bus_i2c2" };
    const osMutexAttr_t a_adc1 = { .name = "bus_adc1" };

    g_mutex_i2c2 = osMutexNew(&a_i2c2);
    g_mutex_adc1 = osMutexNew(&a_adc1);

    g_acquisition_running = false;
    g_period_ms = 1000;
    g_next_uid  = 1;
}

/* ============================================================
 *  Init des slots — version réduite (2 slots seulement)
 *
 *  Slot 1 (index 0) : I2C2 → BH1750
 *  Slot 2 (index 1) : ADC1 CH1 → NTC / signal analogique
 * ============================================================ */

static void init_slots_from_board(void)
{
    /* --- SPI1 : slots 1, 2, 3 (PA5/PA6/PA7 + CS PB0/PB1/PB2) ---*/
    g_slots[0] = (Slot_t){
        .slot_id      = 1,
        .bus_type     = BUS_SPI,
        .hw.spi       = { CH1_SPI_HANDLE, CH1_CS_PORT, CH1_CS_PIN },
        .device_count = 0
    };
    g_slots[1] = (Slot_t){
        .slot_id      = 2,
        .bus_type     = BUS_SPI,
        .hw.spi       = { CH2_SPI_HANDLE, CH2_CS_PORT, CH2_CS_PIN },
        .device_count = 0
    };
    g_slots[2] = (Slot_t){
        .slot_id      = 3,
        .bus_type     = BUS_SPI,
        .hw.spi       = { CH3_SPI_HANDLE, CH3_CS_PORT, CH3_CS_PIN },
        .device_count = 0
    };

     /*--- SPI4 : slots 4, 5 (PE2/PE5/PE6 + CS PE3/PE4) ---*/
    g_slots[3] = (Slot_t){
        .slot_id      = 4,
        .bus_type     = BUS_SPI,
        .hw.spi       = { CH4_SPI_HANDLE, CH4_CS_PORT, CH4_CS_PIN },
        .device_count = 0
    };
    g_slots[4] = (Slot_t){
        .slot_id      = 5,
        .bus_type     = BUS_SPI,
        .hw.spi       = { CH5_SPI_HANDLE, CH5_CS_PORT, CH5_CS_PIN },
        .device_count = 0
    };

    /* --- I2C2 : slot 6 (PF0/PF1) — jusqu'à 6 devices --- */
    g_slots[5] = (Slot_t){
        .slot_id      = 6,
        .bus_type     = BUS_I2C,
        .hw.i2c       = { CH6_I2C_HANDLE },
        .device_count = 0
    };

    /* --- I2C3 : slot 7 (PA8/PC9) — jusqu'à 6 devices --- */
    g_slots[6] = (Slot_t){
        .slot_id      = 7,
        .bus_type     = BUS_I2C,
        .hw.i2c       = { CH7_I2C_HANDLE },
        .device_count = 0
    };

    /* --- ADC1 : slots 8..12 (PA1, PA2, PA3, PC0, PC2) --- */
    g_slots[7] = (Slot_t){
        .slot_id      = 8,
        .bus_type     = BUS_ADC,
        .hw.adc       = { CH8_ADC_HANDLE, CH8_ADC_CHANNEL },
        .device_count = 0
    };
    g_slots[8] = (Slot_t){
        .slot_id      = 9,
        .bus_type     = BUS_ADC,
        .hw.adc       = { CH9_ADC_HANDLE, CH9_ADC_CHANNEL },
        .device_count = 0
    };
    g_slots[9] = (Slot_t){
        .slot_id      = 10,
        .bus_type     = BUS_ADC,
        .hw.adc       = { CH10_ADC_HANDLE, CH10_ADC_CHANNEL },
        .device_count = 0
    };
    g_slots[10] = (Slot_t){
        .slot_id      = 11,
        .bus_type     = BUS_ADC,
        .hw.adc       = { CH11_ADC_HANDLE, CH11_ADC_CHANNEL },
        .device_count = 0
    };
    g_slots[11] = (Slot_t){
        .slot_id      = 12,
        .bus_type     = BUS_ADC,
        .hw.adc       = { CH12_ADC_HANDLE, CH12_ADC_CHANNEL },
        .device_count = 0
    };

    /* --- Digital : slots 13, 14 (PD14/TIM4_CH3, PD15/TIM4_CH4) --- */
    g_slots[12] = (Slot_t){
        .slot_id      = 13,
        .bus_type     = BUS_DIGITAL,
        .hw.digital   = { CH13_DIGITAL_PORT, CH13_DIGITAL_PIN,
                          CH13_TIM_HANDLE,   CH13_TIM_CHANNEL },
        .device_count = 0
    };
    g_slots[13] = (Slot_t){
        .slot_id      = 14,
        .bus_type     = BUS_DIGITAL,
        .hw.digital   = { CH14_DIGITAL_PORT, CH14_DIGITAL_PIN,
                          CH14_TIM_HANDLE,   CH14_TIM_CHANNEL },
        .device_count = 0
    };
}

/* ============================================================
 *  Démarrage de la tâche
 * ============================================================ */

void Reader_StartTask(void)
{
    const osThreadAttr_t attr = {
        .name       = "reader",
        .stack_size = 2048,
        .priority   = osPriorityAboveNormal,
    };
    g_reader_task = osThreadNew(reader_task_fn, NULL, &attr);
}

/* ============================================================
 *  API — affectation / libération de capteurs
 * ============================================================ */
/* ============================================================
 *  TABLE DE DEBUG — à supprimer après les tests
 * ============================================================ */
volatile struct {
    uint8_t  in_slot_id;
    uint8_t  in_model;
    uint8_t  in_quantity;
    uint8_t  in_i2c_addr;
    uint8_t  step_params_ok;
    uint8_t  step_slot_found;
    uint8_t  step_slot_not_full;
    uint8_t  step_drv_found;
    uint8_t  step_bus_ok;
    uint8_t  step_qty_ok;
    uint8_t  step_init_ok;
    uint8_t  slot_bus_type;
    uint8_t  slot_device_count;
    uint8_t  slot_index;
    int8_t   result;
    uint8_t  assigned_uid;
} dbg_assign;
int Reader_AssignSensor(uint8_t slot_id,
                        Sensor_Model_t model,
                        Physical_Quantity_t quantity,
                        const Sensor_Params_t *params,
                        uint8_t *out_uid)
{
    memset((void*)&dbg_assign, 0, sizeof(dbg_assign));
    dbg_assign.in_slot_id  = slot_id;
    dbg_assign.in_model    = (uint8_t)model;
    dbg_assign.in_quantity = (uint8_t)quantity;
    dbg_assign.in_i2c_addr = (params != NULL) ? params->i2c_address : 0xFF;

    if (out_uid == NULL || params == NULL) {
        dbg_assign.result = READER_ERR_BAD_PARAMS;
        return READER_ERR_BAD_PARAMS;
    }
    if (quantity == QUANTITY_NONE) {
        dbg_assign.result = READER_ERR_BAD_PARAMS;
        return READER_ERR_BAD_PARAMS;
    }
    dbg_assign.step_params_ok = 1;

    Slot_t *slot = find_slot(slot_id);
    if (slot == NULL) {
        dbg_assign.result = READER_ERR_NO_SLOT;
        return READER_ERR_NO_SLOT;
    }
    dbg_assign.step_slot_found   = 1;
    dbg_assign.slot_bus_type     = (uint8_t)slot->bus_type;
    dbg_assign.slot_device_count = slot->device_count;
    dbg_assign.slot_index        = (uint8_t)(slot - g_slots);

    if (slot->bus_type != BUS_I2C && slot->device_count >= 1) {
        dbg_assign.result = READER_ERR_SLOT_FULL;
        return READER_ERR_SLOT_FULL;
    }
    if (slot->bus_type == BUS_I2C &&
        slot->device_count >= MAX_I2C_DEVICES_PER_SLOT) {
        dbg_assign.result = READER_ERR_SLOT_FULL;
        return READER_ERR_SLOT_FULL;
    }
    dbg_assign.step_slot_not_full = 1;

    const Sensor_Driver_API_t *drv = SensorDispatch_Get(model);
    if (drv == NULL) {
        dbg_assign.result = READER_ERR_INCOMPAT;
        return READER_ERR_INCOMPAT;
    }
    dbg_assign.step_drv_found = 1;

    if (!drv->supports_bus(slot->bus_type)) {
        dbg_assign.result = READER_ERR_INCOMPAT;
        return READER_ERR_INCOMPAT;
    }
    dbg_assign.step_bus_ok = 1;

    if (!drv->supports_quantity(quantity)) {
        dbg_assign.result = READER_ERR_INCOMPAT;
        return READER_ERR_INCOMPAT;
    }
    dbg_assign.step_qty_ok = 1;

    /* Réserver le device */
    Device_t *device = &slot->devices[slot->device_count];
    memset(device, 0, sizeof(Device_t));
    device->uid         = g_next_uid++;
    device->model       = model;
    device->quantity    = quantity;
    device->i2c_address = params->i2c_address;
    device->driver      = drv;
    device->read_count  = 0;
    device->error_count = 0;

    /* Tenter l'init — si ça échoue, on assigne quand même */
    void *handle = NULL;
    if (drv->init(slot, device, &handle) == 0) {
    	dbg_assign.step_init_ok = 1;
        device->driver_handle = handle;
        device->initialized   = true;

    } else {
        device->driver_handle = NULL;
        device->initialized   = false;
        dbg_assign.step_init_ok = 12;
    }

    device->occupied = true;

    *out_uid = device->uid;
    slot->device_count++;

    dbg_assign.assigned_uid = device->uid;
    dbg_assign.result       = READER_OK;
    return READER_OK;  /* toujours OK — assigné même si init échoue */
}
int Reader_ClearSlot(uint8_t slot_id)
{
    Slot_t *slot = find_slot(slot_id);
    if (slot == NULL) return READER_ERR_NO_SLOT;

    for (int i = 0; i < slot->device_count; ++i) {
        Device_t *dev = &slot->devices[i];
        if (dev->driver && dev->driver->deinit) {
            dev->driver->deinit(dev->driver_handle);
        }
        memset(dev, 0, sizeof(Device_t));
    }
    slot->device_count = 0;
    return READER_OK;
}

int Reader_ClearDevice(uint8_t uid)
{
    for (int i = 0; i < NB_SLOTS; ++i) {
        Slot_t *slot = &g_slots[i];
        for (int j = 0; j < slot->device_count; ++j) {
            Device_t *dev = &slot->devices[j];
            if (dev->occupied && dev->uid == uid) {
                if (dev->driver && dev->driver->deinit) {
                    dev->driver->deinit(dev->driver_handle);
                }
                for (int k = j; k < slot->device_count - 1; ++k) {
                    slot->devices[k] = slot->devices[k + 1];
                }
                memset(&slot->devices[slot->device_count - 1], 0,
                       sizeof(Device_t));
                slot->device_count--;
                return READER_OK;
            }
        }
    }
    return READER_ERR_NO_DEVICE;
}

void Reader_ClearAll(void)
{
    for (int i = 0; i < NB_SLOTS; ++i) {
        Reader_ClearSlot(g_slots[i].slot_id);
    }
    g_next_uid = 1;
}

int Reader_GetSlotInfo(uint8_t slot_id, Slot_t *out)
{
    if (out == NULL) return READER_ERR_BAD_PARAMS;
    Slot_t *slot = find_slot(slot_id);
    if (slot == NULL) return READER_ERR_NO_SLOT;
    *out = *slot;
    return READER_OK;
}

/* ============================================================
 *  API — contrôle de l'acquisition
 * ============================================================ */

void Reader_StartAcquisition(void)  { g_acquisition_running = true;  }
void Reader_StopAcquisition(void)   { g_acquisition_running = false; }

void Reader_SetPeriod(uint32_t period_ms)
{
    if (period_ms > 0) {
        g_period_ms = period_ms;
    }
}

/* ============================================================
 *  Tâche FreeRTOS — Snapshot synchrone
 * ============================================================ */

static void reader_task_fn(void *arg)
{
    (void)arg;

    for (;;) {
        osDelay(g_period_ms);

        if (!g_acquisition_running) continue;

        Snapshot_t snap;
        memset(&snap, 0, sizeof(snap));
        snap.timestamp_ms = osKernelGetTickCount();
        snap.count = 0;

        for (int i = 0; i < NB_SLOTS; ++i) {
            Slot_t *slot = &g_slots[i];

            for (int j = 0; j < slot->device_count; ++j) {
                Device_t *dev = &slot->devices[j];

                if (!dev->occupied) continue;
                if (dev->driver == NULL) continue;
                if (snap.count >= MAX_TOTAL_DEVICES) break;

                Measurement_t *m = &snap.measures[snap.count];
                memset(m, 0, sizeof(Measurement_t));
                m->uid      = dev->uid;
                m->slot_id  = slot->slot_id;
                m->model    = dev->model;
                m->quantity = dev->quantity;

                /* --- Capteur pas encore initialisé : tenter la réinit --- */
                if (!dev->initialized) {
                    void *handle = NULL;
                    if (dev->driver->init(slot, dev, &handle) == 0) {
                        dev->driver_handle = handle;
                        dev->initialized   = true;
                        /* init OK → on continue vers la lecture ci-dessous */
                    } else {
                        /* Toujours absent — signaler dans le snapshot */
                        m->status       = -1;
                        m->value        = 0.0f;
                        m->timestamp_ms = snap.timestamp_ms;
                        dev->error_count++;
                        snap.count++;
                        continue;  /* capteur suivant */
                    }
                }

                /* --- Lecture du capteur --- */
                osMutexId_t mtx = get_bus_mutex(slot);
                if (mtx != NULL) osMutexAcquire(mtx, osWaitForever);

                int rc = dev->driver->read(dev->driver_handle,
                                           dev->quantity,
                                           m);

                if (mtx != NULL) osMutexRelease(mtx);

                if (rc == 0) {
                    m->timestamp_ms = snap.timestamp_ms;
                    m->status = 0;
                    dev->read_count++;
                } else {
                    m->status = (int8_t)rc;
                    m->value  = 0.0f;
                    m->timestamp_ms = snap.timestamp_ms;
                    dev->error_count++;

                    /* Lecture échouée → capteur probablement débranché.
                     * On libère le handle et on marque non-initialisé.
                     * Au prochain cycle, init sera retentée. */
                    if (dev->driver->deinit) {
                        dev->driver->deinit(dev->driver_handle);
                    }
                    dev->driver_handle = NULL;
                    dev->initialized   = false;
                }

                snap.count++;
            }
        }

        if (snap.count > 0) {
            osMessageQueuePut(queue_snapshots, &snap, 0, 0);
            osMessageQueuePut(queue_snapshots_dbg, &snap, 0, 0);

        }
    }
}

/* ============================================================
 *  Helpers internes
 * ============================================================ */

static Slot_t *find_slot(uint8_t slot_id)
{
    if (slot_id == 0 || slot_id > NB_SLOTS) return NULL;
    return &g_slots[slot_id - 1];
}

static osMutexId_t get_bus_mutex(const Slot_t *slot)
{
    switch (slot->bus_type) {
        case BUS_I2C: return g_mutex_i2c2;
        case BUS_ADC: return g_mutex_adc1;
        default:      return NULL;
    }
}
