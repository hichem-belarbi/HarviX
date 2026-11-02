#ifndef HISTORY_BUFFER_H
#define HISTORY_BUFFER_H

#include "rule_types.h"

/* ============================================================
 *  Historique par UID
 *
 *  Maintient les MAX_HISTORY_PER_UID dernières mesures de chaque
 *  UID suivi. Alimenté par le moteur de règles à chaque snapshot
 *  reçu, lu par les primitives de calcul.
 *
 *  L'index 0 retourné par les fonctions get correspond à la
 *  valeur la PLUS RÉCENTE. L'index window-1 est la plus ancienne.
 * ============================================================ */

void History_Init(void);

/* Pousse une nouvelle mesure dans le buffer du UID.
 * Si l'UID n'est pas encore suivi, lui alloue un slot. */
void History_Push(uint8_t uid, float value, uint32_t timestamp_ms);

/* Renvoie le nombre de valeurs disponibles pour ce UID (0..MAX). */
uint8_t History_GetCount(uint8_t uid);

/* Récupère la valeur à l'index demandé (0 = plus récente).
 * Retourne false si l'index dépasse les valeurs disponibles. */
bool History_GetValue(uint8_t uid, uint8_t index, float *out_value);

/* Récupère le timestamp associé. */
bool History_GetTimestamp(uint8_t uid, uint8_t index, uint32_t *out_ts);

/* Vide tous les historiques (utilisé au démarrage d'une expérience). */
void History_Reset(void);

#endif /* HISTORY_BUFFER_H */
