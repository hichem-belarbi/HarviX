#ifndef BH1750_DRIVER_H
#define BH1750_DRIVER_H

#include "sensor_types.h"

/* Driver BH1750 — illuminance, I2C uniquement.
 *
 * Grandeur supportée :
 *   QUANTITY_LIGHT_LUX  →  lx
 *
 * Adresse I2C : 0x23 (ADDR=LOW) ou 0x5C (ADDR=HIGH).
 * Passer l'adresse choisie dans Sensor_Params_t.i2c_address.
 * period_ms >= 120 (temps de mesure en mode continu).
 */
extern const Sensor_Driver_API_t bh1750_driver_api;

#endif /* BH1750_DRIVER_H */
