#ifndef SENSOR_DISPATCH_H
#define SENSOR_DISPATCH_H

#include "sensor_types.h"

/* Retourne le driver associé à un modèle, ou NULL si inconnu.
 * C'est le SEUL point de couplage entre reader.c et la
 * bibliothèque de drivers : pour ajouter un capteur, il suffit
 * d'ajouter une entrée dans g_drivers[] (sensor_dispatch.c). */
const Sensor_Driver_API_t *SensorDispatch_Get(Sensor_Model_t model);

#endif /* SENSOR_DISPATCH_H */
