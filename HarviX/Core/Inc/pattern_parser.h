#ifndef PATTERN_PARSER_H
#define PATTERN_PARSER_H

#include "rule_types.h"

/* Codes de retour */
#define PATTERN_OK                 0
#define PATTERN_ERR_SYNTAX        -1
#define PATTERN_ERR_UNKNOWN_COND  -2
#define PATTERN_ERR_TOO_LONG      -3
#define PATTERN_ERR_BAD_PARENS    -4

/* ============================================================
 *  Compile un pattern texte ("c1 AND c2 OR c3") en RPN.
 *
 *  Convention du texte :
 *    - Conditions notées cN avec N entre 1 et n_conditions
 *    - Opérateurs : AND, OR, NOT (insensibles à la casse)
 *    - Parenthèses : ( et )
 *    - Séparateurs : espaces (recommandés mais pas obligatoires)
 *
 *  Stocke le RPN dans out_rpn[] et la longueur dans *out_len.
 *  Vérifie que tous les cN référencent un index < n_conditions.
 * ============================================================ */
int Pattern_Compile(const char     *text,
                    uint8_t         n_conditions,
                    Pattern_Token_t *out_rpn,
                    uint8_t        *out_len);

/* ============================================================
 *  Évalue une expression RPN à partir des valeurs booléennes
 *  des conditions.
 * ============================================================ */
bool Pattern_Evaluate(const Pattern_Token_t *rpn,
                      uint8_t                n_tokens,
                      const bool            *cond_values);

#endif /* PATTERN_PARSER_H */
