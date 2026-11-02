#ifndef COMMANDER_H
#define COMMANDER_H

#include "commander_types.h"

/* ============================================================
 *  API publique du commander
 *
 *  Le commander est la tâche d'orchestration centrale.
 *  Il consomme queue_cmds et dispatche vers les modules :
 *    - Reader (assignation/libération de capteurs)
 *    - RulesStore (ajout/suppression/modification de règles)
 *    - Flash (sauvegarde/chargement de config)
 *    - Queue TX (ACK, NACK, STATUS, SYNC vers le desktop)
 *    - Queue log (événements système)
 * ============================================================ */

/* Initialise l'état interne du commander.
 * À appeler APRÈS Reader_Init(), RulesStore_Init(), History_Init(). */
void Commander_Init(void);

/* Démarre la tâche FreeRTOS du commander.
 * À appeler après Commander_Init(). */
void Commander_StartTask(void);

#endif /* COMMANDER_H */