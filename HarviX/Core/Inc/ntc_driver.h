#ifndef NTC_DRIVER_H
#define NTC_DRIVER_H

#include "sensor_types.h"

/* Driver NTC — thermistance sur entrée ADC.
 *
 * Câblage : pont diviseur
 *   3.3V --- [R_fixe 10k] --- PA1 --- [NTC 10k] --- GND
 *
 * Formule Steinhart-Hart simplifiée (bêta) :
 *   R_ntc = R_fixe * adc / (4095 - adc)
 *   T(K) = 1 / (1/T0 + (1/B) * ln(R_ntc/R0))
 *   T(°C) = T(K) - 273.15
 *
 * Valeurs typiques NTC 10k :
 *   R0 = 10000 Ω à T0 = 25°C (298.15 K)
 *   B = 3950 (coefficient bêta)
 */
extern const Sensor_Driver_API_t ntc_driver_api;

#endif /* NTC_DRIVER_H */
