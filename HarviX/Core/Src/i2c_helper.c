#include "i2c_helper.h"

/* ============================================================
 *  Reset du bus I2C
 *
 *  Quand un capteur est débranché pendant une transaction,
 *  le STM32 reste en attente d'un ACK qui ne viendra jamais.
 *  Le flag BUSY du registre SR2 reste à 1 indéfiniment.
 *
 *  La seule façon de récupérer :
 *    1. Aborter la transaction en cours (si supporté)
 *    2. HAL_I2C_DeInit → reset les registres du périphérique
 *    3. HAL_I2C_Init  → reconfigure tout proprement
 *
 *  Après ça, le bus est de nouveau opérationnel.
 * ============================================================ */

bool I2C_RecoverBus(I2C_HandleTypeDef *hi2c)
{
    if (hi2c == NULL) return false;

    /* Vérifier si le bus est vraiment bloqué */
    if (hi2c->State == HAL_I2C_STATE_READY &&
        __HAL_I2C_GET_FLAG(hi2c, I2C_FLAG_BUSY) == RESET) {
        return true;  /* bus OK, rien à faire */
    }

    /* Forcer l'abort si une transaction est en cours */
    if (hi2c->State != HAL_I2C_STATE_READY) {
        HAL_I2C_Master_Abort_IT(hi2c, 0);
        uint32_t start = HAL_GetTick();
        while (hi2c->State != HAL_I2C_STATE_READY) {
            if (HAL_GetTick() - start > 50) break;
        }
    }

    /* Reset complet du périphérique I2C */
    __HAL_I2C_DISABLE(hi2c);

    /* Forcer le clear du flag BUSY par software reset */
    hi2c->Instance->CR1 |= I2C_CR1_SWRST;
    hi2c->Instance->CR1 &= ~I2C_CR1_SWRST;

    __HAL_I2C_ENABLE(hi2c);

    /* Réinitialiser via HAL */
    HAL_I2C_DeInit(hi2c);
    HAL_StatusTypeDef rc = HAL_I2C_Init(hi2c);

    return (rc == HAL_OK);
}

/* ============================================================
 *  Test de présence d'un device
 *
 *  Fait un simple envoi d'adresse sans données.
 *  Si le device répond ACK → présent.
 *  Si pas de réponse → absent.
 *  Si le bus est bloqué → reset puis réessai.
 * ============================================================ */

bool I2C_IsDevicePresent(I2C_HandleTypeDef *hi2c,
                         uint8_t addr_7bit,
                         uint32_t timeout_ms)
{
    if (hi2c == NULL) return false;

    uint16_t addr = (uint16_t)(addr_7bit << 1);

    /* Si le bus est bloqué, tenter un reset d'abord */
    if (__HAL_I2C_GET_FLAG(hi2c, I2C_FLAG_BUSY) == SET &&
        hi2c->State == HAL_I2C_STATE_READY) {
        I2C_RecoverBus(hi2c);
    }

    HAL_StatusTypeDef rc = HAL_I2C_IsDeviceReady(hi2c, addr, 1, timeout_ms);

    if (rc == HAL_OK) {
        return true;
    }

    /* Si le bus est coincé après cette tentative, reset */
    if (hi2c->State != HAL_I2C_STATE_READY) {
        I2C_RecoverBus(hi2c);
    }

    return false;
}

/* ============================================================
 *  Transmission sûre — avec récupération automatique
 * ============================================================ */

HAL_StatusTypeDef I2C_SafeTransmit(I2C_HandleTypeDef *hi2c,
                                    uint16_t addr,
                                    uint8_t *data, uint16_t size,
                                    uint32_t timeout_ms)
{
    if (hi2c == NULL) return HAL_ERROR;

    /* Vérifier et récupérer le bus si nécessaire */
    if (__HAL_I2C_GET_FLAG(hi2c, I2C_FLAG_BUSY) == SET &&
        hi2c->State == HAL_I2C_STATE_READY) {
        if (!I2C_RecoverBus(hi2c)) return HAL_ERROR;
    }

    HAL_StatusTypeDef rc = HAL_I2C_Master_Transmit(hi2c, addr, data, size, timeout_ms);

    /* Si erreur, tenter un reset pour le prochain appel */
    if (rc != HAL_OK) {
        I2C_RecoverBus(hi2c);
    }

    return rc;
}

/* ============================================================
 *  Réception sûre
 * ============================================================ */

HAL_StatusTypeDef I2C_SafeReceive(I2C_HandleTypeDef *hi2c,
                                   uint16_t addr,
                                   uint8_t *data, uint16_t size,
                                   uint32_t timeout_ms)
{
    if (hi2c == NULL) return HAL_ERROR;

    if (__HAL_I2C_GET_FLAG(hi2c, I2C_FLAG_BUSY) == SET &&
        hi2c->State == HAL_I2C_STATE_READY) {
        if (!I2C_RecoverBus(hi2c)) return HAL_ERROR;
    }

    HAL_StatusTypeDef rc = HAL_I2C_Master_Receive(hi2c, addr, data, size, timeout_ms);

    if (rc != HAL_OK) {
        I2C_RecoverBus(hi2c);
    }

    return rc;
}

/* ============================================================
 *  Lecture mémoire sûre (registre I2C)
 * ============================================================ */

HAL_StatusTypeDef I2C_SafeMemRead(I2C_HandleTypeDef *hi2c,
                                   uint16_t addr,
                                   uint16_t mem_addr,
                                   uint16_t mem_size,
                                   uint8_t *data, uint16_t size,
                                   uint32_t timeout_ms)
{
    if (hi2c == NULL) return HAL_ERROR;

    if (__HAL_I2C_GET_FLAG(hi2c, I2C_FLAG_BUSY) == SET &&
        hi2c->State == HAL_I2C_STATE_READY) {
        if (!I2C_RecoverBus(hi2c)) return HAL_ERROR;
    }

    HAL_StatusTypeDef rc = HAL_I2C_Mem_Read(hi2c, addr, mem_addr, mem_size,
                                             data, size, timeout_ms);

    if (rc != HAL_OK) {
        I2C_RecoverBus(hi2c);
    }

    return rc;
}
