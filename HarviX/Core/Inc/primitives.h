#ifndef PRIMITIVES_H
#define PRIMITIVES_H

#include "rule_types.h"

/* ============================================================
 *  Évalue une primitive sur l'historique d'un UID.
 *
 *  Pour PRIM_DELTA_LAST : last_trigger_value est la dernière
 *  valeur ayant causé un déclenchement (passée par le moteur).
 *  Pour PRIM_NEAR_MULTIPLE : param est la base.
 *
 *  Retourne true si le calcul a abouti (assez de données dans
 *  l'historique). Met le résultat dans *out.
 * ============================================================ */
bool Primitive_Eval(Primitive_t fn,
                    uint8_t     uid,
                    uint8_t     window,
                    float       param,
                    float       last_trigger_value,
                    float      *out);

#endif /* PRIMITIVES_H */
