#ifndef I2C_HELPER_H
#define I2C_HELPER_H

#include "stm32f4xx_hal.h"
#include <stdbool.h>

/* ============================================================
 *  I2C Helper — bus robuste avec récupération d'erreurs
 *
 *  Problème : quand un capteur I2C est débranché en cours de
 *  communication, le bus reste dans l'état BUSY. Le périphérique
 *  I2C du STM32 ne récupère jamais tout seul — il faut le
 *  réinitialiser (DeInit + Init).
 *
 *  Ce helper encapsule toutes les opérations I2C avec :
 *    1. Vérification du bus avant chaque opération
 *    2. Reset automatique si le bus est bloqué
 *    3. Timeout court pour ne pas bloquer les autres capteurs
 *    4. Test de présence rapide (ping I2C)
 * ============================================================ */

/* Vérifie si un device I2C est présent sur le bus.
 * Fait un simple ping (envoi de l'adresse, attend le ACK).
 * Retourne true si le device répond, false sinon.
 * Ne bloque jamais plus de timeout_ms millisecondes. */
bool I2C_IsDevicePresent(I2C_HandleTypeDef *hi2c,
                         uint8_t addr_7bit,
                         uint32_t timeout_ms);

/* Vérifie si le bus I2C est bloqué (BUSY coincé).
 * Si oui, fait un reset complet du périphérique.
 * Retourne true si le bus est opérationnel après. */
bool I2C_RecoverBus(I2C_HandleTypeDef *hi2c);

/* Transmission I2C avec vérification et récupération.
 * Si le bus est bloqué, tente un reset puis réessaie.
 * Retourne HAL_OK ou HAL_ERROR/HAL_TIMEOUT. */
HAL_StatusTypeDef I2C_SafeTransmit(I2C_HandleTypeDef *hi2c,
                                    uint16_t addr,
                                    uint8_t *data, uint16_t size,
                                    uint32_t timeout_ms);

/* Réception I2C avec vérification et récupération. */
HAL_StatusTypeDef I2C_SafeReceive(I2C_HandleTypeDef *hi2c,
                                   uint16_t addr,
                                   uint8_t *data, uint16_t size,
                                   uint32_t timeout_ms);

/* Écriture mémoire I2C (registre) avec récupération. */
HAL_StatusTypeDef I2C_SafeMemRead(I2C_HandleTypeDef *hi2c,
                                   uint16_t addr,
                                   uint16_t mem_addr,
                                   uint16_t mem_size,
                                   uint8_t *data, uint16_t size,
                                   uint32_t timeout_ms);

#endif /* I2C_HELPER_H */
