#ifndef READER_H
#define READER_H

#include "sensor_types.h"

/* ============================================================
 *  Codes de retour
 * ============================================================ */
#define READER_OK                0
#define READER_ERR_BAD_PARAMS   -1
#define READER_ERR_NO_SLOT      -2
#define READER_ERR_SLOT_FULL    -3   /* SPI/ADC déjà occupé, ou I2C plein */
#define READER_ERR_INCOMPAT     -4   /* bus ou grandeur incompatible       */
#define READER_ERR_INIT_FAIL    -5   /* driver init a échoué               */
#define READER_ERR_NO_DEVICE    -6   /* uid introuvable                    */

/* ============================================================
 *  API publique
 * ============================================================ */
void Reader_Init(void);
void Reader_StartTask(void);

/* Fréquence globale de snapshot — configurable au runtime */
void Reader_SetPeriod(uint32_t period_ms);

/* Assignation / libération */
int  Reader_AssignSensor(uint8_t slot_id,
                         Sensor_Model_t model,
                         Physical_Quantity_t quantity,
                         const Sensor_Params_t *params,
                         uint8_t *out_uid);   /* uid attribué si OK */

int  Reader_ClearSlot(uint8_t slot_id);
int  Reader_ClearDevice(uint8_t uid);          /* libère un device par uid */
void Reader_ClearAll(void);

/* Contrôle acquisition */
void Reader_StartAcquisition(void);
void Reader_StopAcquisition(void);

/* Diagnostic */
int  Reader_GetSlotInfo(uint8_t slot_id, Slot_t *out);

#endif /* READER_H */
