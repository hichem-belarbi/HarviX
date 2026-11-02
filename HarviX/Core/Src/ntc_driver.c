#include "ntc_driver.h"
#include <stdlib.h>
#include <math.h>

/* ============================================================
 *  Constantes NTC 10k par défaut
 * ============================================================ */
#define NTC_R0          10000.0f    /* résistance à T0 (ohms)    */
#define NTC_T0_KELVIN   298.15f    /* 25°C en Kelvin             */
#define NTC_BETA        3950.0f    /* coefficient bêta           */
#define NTC_R_FIXED     10000.0f   /* résistance fixe du pont    */
#define NTC_ADC_MAX     4095.0f    /* ADC 12 bits                */

/* ============================================================
 *  Instance
 * ============================================================ */
typedef struct {
    Slot_t *slot;
} NTC_t;

/* ============================================================
 *  API
 * ============================================================ */

static bool ntc_supports_bus(Bus_Type_t bus)
{
    return bus == BUS_ADC;
}

static bool ntc_supports_quantity(Physical_Quantity_t q)
{
    return q == QUANTITY_TEMPERATURE || q == QUANTITY_VOLTAGE;
}

static int ntc_init(Slot_t *slot, Device_t *device, void **handle)
{
    (void)device;

    NTC_t *dev = calloc(1, sizeof(NTC_t));
    if (dev == NULL) return -1;
    dev->slot = slot;

    *handle = dev;
    return 0;
}

static int ntc_read(void *handle, Physical_Quantity_t quantity,
                    Measurement_t *out)
{
    NTC_t *dev = (NTC_t *)handle;
    Bus_ADC_HW_t *hw = &dev->slot->hw.adc;

    /* Configurer le canal ADC */
    ADC_ChannelConfTypeDef conf = {
        .Channel = hw->channel,
        .Rank    = 1,
        .SamplingTime = ADC_SAMPLETIME_84CYCLES,
    };
    if (HAL_ADC_ConfigChannel(hw->handle, &conf) != HAL_OK) {
        return -1;
    }

    /* Lancer la conversion */
    HAL_ADC_Start(hw->handle);
    if (HAL_ADC_PollForConversion(hw->handle, 100) != HAL_OK) {
        HAL_ADC_Stop(hw->handle);
        return -2;
    }

    uint32_t adc_raw = HAL_ADC_GetValue(hw->handle);
    HAL_ADC_Stop(hw->handle);

    /* Si l'utilisateur veut juste la tension brute */
    if (quantity == QUANTITY_VOLTAGE) {
        out->value = (float)adc_raw * 3.3f / NTC_ADC_MAX;
        return 0;
    }

    /* Conversion ADC → résistance NTC (pont diviseur) */
    if (adc_raw == 0) adc_raw = 1;  /* éviter division par zéro */
    float r_ntc = NTC_R_FIXED * (float)adc_raw / (NTC_ADC_MAX - (float)adc_raw);

    /* Conversion résistance → température (équation bêta) */
    float t_kelvin = 1.0f / (
        (1.0f / NTC_T0_KELVIN) +
        (1.0f / NTC_BETA) * logf(r_ntc / NTC_R0)
    );

    out->value = t_kelvin - 273.15f;
    return 0;
}

static void ntc_deinit(void *handle)
{
    if (handle) free(handle);
}

const Sensor_Driver_API_t ntc_driver_api = {
    .init              = ntc_init,
    .read              = ntc_read,
    .deinit            = ntc_deinit,
    .supports_bus      = ntc_supports_bus,
    .supports_quantity = ntc_supports_quantity,
};
