#ifndef RULES_ENGINE_H
#define RULES_ENGINE_H

#include <stdbool.h>

/* ============================================================
 *  API publique du moteur de règles
 *
 *  Le moteur ne crée, ne modifie, ne supprime jamais de règle.
 *  Toutes les opérations CRUD sur la table passent par le
 *  rules_store et sont effectuées par le commander.
 * ============================================================ */

void RulesEngine_Init(void);
void RulesEngine_StartTask(void);

/* Active/désactive l'évaluation. Quand désactivée, la tâche
 * continue de tourner mais ignore les snapshots reçus. */
void RulesEngine_StartEvaluation(void);
void RulesEngine_StopEvaluation(void);

#endif /* RULES_ENGINE_H */
