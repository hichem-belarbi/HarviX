#ifndef RULES_STORE_H
#define RULES_STORE_H

#include "rule_types.h"

/* Codes de retour */
#define STORE_OK              0
#define STORE_ERR_FULL       -1
#define STORE_ERR_NOT_FOUND  -2
#define STORE_ERR_BUSY       -3

/* ============================================================
 *  À appeler une fois au boot avant tout autre usage.
 * ============================================================ */
void RulesStore_Init(void);

/* ============================================================
 *  API d'écriture — utilisée par le commander uniquement
 *
 *  Toutes ces fonctions prennent le mutex interne pendant la
 *  durée de l'opération.
 * ============================================================ */
int  RulesStore_Add(const Rule_t *rule);
int  RulesStore_Remove(uint8_t rule_id);
int  RulesStore_Update(const Rule_t *rule);
void RulesStore_ClearAll(void);

/* ============================================================
 *  API de lecture — utilisée par le moteur de règles
 *
 *  Snapshot atomique : le moteur appelle Snapshot() en début
 *  de cycle pour obtenir une copie cohérente de la table, puis
 *  travaille sur cette copie sans tenir le mutex pendant
 *  l'évaluation. Cela évite de bloquer le commander.
 * ============================================================ */
typedef struct {
    Rule_t   rules[MAX_RULES];
    uint8_t  count;
    uint32_t version;        /* incrémentée à chaque modification */
} Rules_Snapshot_t;

void RulesStore_GetSnapshot(Rules_Snapshot_t *out);

/* Indique si la table a changé depuis la dernière version connue.
 * Permet au moteur d'éviter une copie complète si rien n'a bougé. */
uint32_t RulesStore_GetVersion(void);

#endif /* RULES_STORE_H */
