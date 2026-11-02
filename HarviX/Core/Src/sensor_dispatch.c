#include "sensor_dispatch.h"
#include "bh1750_driver.h"
#include "ntc_driver.h"

/* ============================================================
 *  Table des drivers disponibles
 *
 *  Pour ajouter un capteur :
 *    1. Créer xxx_driver.h / xxx_driver.c avec un
 *       `extern const Sensor_Driver_API_t xxx_driver_api;`
 *    2. Ajouter une entrée SENSOR_XXX dans sensor_types.h
 *    3. Ajouter une ligne dans ce tableau
 *
 *  reader.c n'a pas à être modifié.
 * ============================================================ */
static const Sensor_Driver_API_t *const g_drivers[SENSOR_COUNT] = {
    [SENSOR_NONE]   = NULL,
    [SENSOR_BH1750] = &bh1750_driver_api,
	[SENSOR_NTC]=&ntc_driver_api,
    /* [SENSOR_NTC]  = &ntc_driver_api, */
};

const Sensor_Driver_API_t *SensorDispatch_Get(Sensor_Model_t model)
{
    if (model <= SENSOR_NONE || model >= SENSOR_COUNT) return NULL;
    return g_drivers[model];
}
