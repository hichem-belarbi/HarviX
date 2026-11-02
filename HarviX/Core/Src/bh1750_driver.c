#include "bh1750_driver.h"
#include "i2c_helper.h"
#include "FreeRTOS.h"
#include "task.h"
#include <stdlib.h>

/* ============================================================
 *  Commandes BH1750
 * ============================================================ */
#define BH1750_POWER_ON          0x01
#define BH1750_POWER_OFF         0x00
#define BH1750_RESET             0x07
#define BH1750_CONT_HIRES_MODE   0x10
#define BH1750_CONV_TIME_MS      180

/* ============================================================
 *  Instance
 * ============================================================ */
typedef struct {
    Slot_t      *slot;
    uint8_t      address;
    TickType_t   ready_tick;   /* premier read pas avant ce tick */
} BH1750_t;

/* ============================================================
 *  API
 * ============================================================ */

static bool bh1750_supports_bus(Bus_Type_t bus)
{
    return bus == BUS_I2C;
}

static bool bh1750_supports_quantity(Physical_Quantity_t q)
{
    return q == QUANTITY_LIGHT_LUX;
}

/* ============================================================
 *  Debug
 * ============================================================ */
volatile struct {
    uint8_t           in_addr;
    uint8_t           step_present;
    uint8_t           step_alloc;
    uint8_t           step_power_on;
    uint8_t           step_mode_set;
    HAL_StatusTypeDef hal_status;
    int8_t            result;
} dbg_init;

/* ============================================================
 *  Init
 * ============================================================ */
static int bh1750_init(Slot_t *slot, Device_t *device, void **handle)
{
    I2C_HandleTypeDef *hi2c = slot->hw.i2c.handle;
    uint8_t addr   = device->i2c_address;
    uint16_t addr_w = (uint16_t)(addr << 1);

    dbg_init.in_addr       = addr;
    dbg_init.step_present  = 0;
    dbg_init.step_alloc    = 0;
    dbg_init.step_power_on = 0;
    dbg_init.step_mode_set = 0;
    dbg_init.hal_status    = HAL_OK;
    dbg_init.result        = 0;

    /* 1. Vérifier si le device est présent */
    if (!I2C_IsDevicePresent(hi2c, addr, 50)) {
        dbg_init.step_present = 0xFF;
        dbg_init.result       = -2;
        return -2;
    }
    dbg_init.step_present = 1;

    /* 2. Allouer l'instance */
    BH1750_t *dev = calloc(1, sizeof(BH1750_t));
    if (dev == NULL) {
        dbg_init.step_alloc = 0xFF;
        dbg_init.result     = -1;
        return -1;
    }
    dbg_init.step_alloc = 1;
    dev->slot    = slot;
    dev->address = addr;

    /* 3. Power ON */
    uint8_t cmd = BH1750_POWER_ON;
    HAL_StatusTypeDef st = I2C_SafeTransmit(hi2c, addr_w, &cmd, 1, 100);
    dbg_init.hal_status = st;
    if (st != HAL_OK) {
        dbg_init.step_power_on = 0xFF;
        dbg_init.result        = -3;
        free(dev);
        return -3;
    }
    dbg_init.step_power_on = 1;

    /* 4. Mode mesure continue haute résolution */
    cmd = BH1750_CONT_HIRES_MODE;
    st  = I2C_SafeTransmit(hi2c, addr_w, &cmd, 1, 100);
    dbg_init.hal_status = st;
    if (st != HAL_OK) {
        dbg_init.step_mode_set = 0xFF;
        dbg_init.result        = -4;
        free(dev);
        return -4;
    }
    dbg_init.step_mode_set = 1;

    /* 5. Mémoriser le tick d'expiration — pas de blocking delay ici */
    dev->ready_tick = xTaskGetTickCount() + pdMS_TO_TICKS(BH1750_CONV_TIME_MS);

    dbg_init.result = 0;
    *handle = dev;
    return 0;
}

/* ============================================================
 *  Read
 * ============================================================ */
static int bh1750_read(void *handle, Physical_Quantity_t quantity,
                       Measurement_t *out)
{
    (void)quantity;
    BH1750_t *dev   = (BH1750_t *)handle;
    I2C_HandleTypeDef *hi2c = dev->slot->hw.i2c.handle;
    uint16_t addr_r = (uint16_t)(dev->address << 1) | 0x01;

    /* Attendre si la première mesure n'est pas encore prête */
    TickType_t now = xTaskGetTickCount();
    if ((int32_t)(dev->ready_tick - now) > 0) {
        vTaskDelay(dev->ready_tick - now);
    }

    uint8_t raw[2];
    if (I2C_SafeReceive(hi2c, addr_r, raw, 2, 100) != HAL_OK) {
        return -1;
    }

    uint16_t raw_val = (uint16_t)((raw[0] << 8) | raw[1]);
    out->value = (float)raw_val / 1.2f;

    return 0;
}

/* ============================================================
 *  Deinit
 * ============================================================ */
static void bh1750_deinit(void *handle)
{
    if (handle) {
        BH1750_t *dev   = (BH1750_t *)handle;
        uint8_t cmd     = BH1750_POWER_OFF;
        uint16_t addr_w = (uint16_t)(dev->address << 1);
        I2C_SafeTransmit(dev->slot->hw.i2c.handle, addr_w, &cmd, 1, 100);
        free(dev);
    }
}

/* ============================================================
 *  Driver API
 * ============================================================ */
const Sensor_Driver_API_t bh1750_driver_api = {
    .init              = bh1750_init,
    .read              = bh1750_read,
    .deinit            = bh1750_deinit,
    .supports_bus      = bh1750_supports_bus,
    .supports_quantity = bh1750_supports_quantity,
};
