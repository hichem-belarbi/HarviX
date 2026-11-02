#ifndef RULE_TYPES_H
#define RULE_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include "sensor_types.h"

/* ============================================================
 *  Limites du moteur de règles
 * ============================================================ */
#define MAX_RULES               20
#define MAX_COND_PER_RULE       8
#define MAX_PATTERN_TOKENS      24
#define MAX_TRIGGERS_PER_RULE   4
#define MAX_UIDS_PER_TRIGGER    8
#define MAX_HISTORY_PER_UID     20
#define MAX_TRACKED_UIDS        16

/* ============================================================
 *  Primitives de calcul sur fenêtre d'historique
 * ============================================================ */
typedef enum {
    PRIM_NONE = 0,
    PRIM_CURRENT,         /* valeur courante (window ignoré)        */
    PRIM_MEAN,            /* moyenne sur window                      */
    PRIM_SLOPE,           /* pente régression linéaire / index       */
    PRIM_STDDEV,          /* écart-type sur window                   */
    PRIM_MIN,             /* minimum sur window                      */
    PRIM_MAX,             /* maximum sur window                      */
    PRIM_MONOTONICITY,    /* proportion de différences positives     */
    PRIM_NOISE_LEVEL,     /* fréquence des changements de signe      */
    PRIM_DERIV_TIME,      /* (val[n]-val[n-k]) / (t[n]-t[n-k])       */
    PRIM_DELTA_LAST,      /* |val - last_trigger_value|              */
    PRIM_NEAR_MULTIPLE,   /* fmodf(val, base) replié sur [-base/2, base/2] */
    PRIM_COUNT
} Primitive_t;

/* ============================================================
 *  Opérateurs
 * ============================================================ */
typedef enum {
    ARITH_NONE = 0,       /* pas de second terme                     */
    ARITH_ADD,
    ARITH_SUB,
} Arith_Op_t;

typedef enum {
    CMP_GT = 0,           /* >                                       */
    CMP_LT,               /* <                                       */
    CMP_GE,               /* >=                                      */
    CMP_LE,               /* <=                                      */
    CMP_EQ,               /* ==  (avec tolérance par défaut)         */
    CMP_NEQ,              /* !=                                      */
    CMP_NEAR,             /* |x - rhs| <= tolerance                  */
} Compare_Op_t;

/* ============================================================
 *  Une condition atomique
 *
 *  Forme générique :
 *      fn_a(uid_a, window_a) [arith fn_b(uid_b, window_b)] + offset
 *      <CMP> rhs [tolérance pour NEAR]
 *
 *  Si arith == ARITH_NONE : on ignore fn_b/uid_b/window_b.
 * ============================================================ */

typedef struct {
    /* Terme de gauche */
    Primitive_t  fn_a;
    uint8_t      uid_a;
    uint8_t      window_a;        /* 2..MAX_HISTORY_PER_UID, ignoré pour CURRENT */
    float        param_a;         /* base pour NEAR_MULTIPLE, ignoré sinon       */
    float        coeff_a;         /* coefficient multiplicateur (défaut : 1.0)   */

    /* Terme de droite éventuel */
    Arith_Op_t   arith;
    Primitive_t  fn_b;
    uint8_t      uid_b;
    uint8_t      window_b;
    float        param_b;
    float        coeff_b;         /* coefficient multiplicateur (défaut : 1.0)   */

    float        offset;          /* constante ajoutée au LHS                    */

    /* Comparaison */
    Compare_Op_t cmp;
    float        rhs;
    float        tolerance;       /* utilisé par CMP_NEAR et CMP_EQ              */
} Condition_t;

/* ============================================================
 *  Pattern logique en RPN
 *
 *  Les conditions sont indexées 0..n_conditions-1.
 *  Pour évaluer "(c1 AND c2) OR c3" → RPN : c1 c2 AND c3 OR
 *  → tokens : [COND(0), COND(1), AND, COND(2), OR]
 * ============================================================ */
typedef enum {
    TOK_COND = 0,
    TOK_AND,
    TOK_OR,
    TOK_NOT,
} Token_Type_t;

typedef struct {
    Token_Type_t type;
    uint8_t      cond_index;      /* utilisé seulement si type == TOK_COND */
} Pattern_Token_t;

/* ============================================================
 *  Triggers — actions déclenchées quand la règle passe à vrai
 * ============================================================ */
typedef enum {
    TRIG_NONE = 0,
    TRIG_LOG,             /* enregistrer en mémoire les uids listés     */
    TRIG_STREAM,          /* envoyer vers desktop les uids listés       */
    TRIG_ACTION,          /* déclencher une action hardware             */
} Trigger_Type_t;

typedef struct {
    uint8_t  pin_or_servo_id;
    uint16_t param;               /* durée_ms pour pin, angle pour servo */
    uint8_t  action_code;         /* PIN_HIGH, PIN_LOW, SERVO_SET, ...   */
} Hardware_Action_t;

typedef struct {
    Trigger_Type_t type;
    union {
        struct {                  /* TRIG_LOG ou TRIG_STREAM            */
            uint8_t uids[MAX_UIDS_PER_TRIGGER];
            uint8_t n_uids;
        } payload;
        Hardware_Action_t action; /* TRIG_ACTION                        */
    } data;
} Trigger_t;

/* ============================================================
 *  Une règle complète
 * ============================================================ */
typedef struct {
    /* Identité */
    uint8_t   rule_id;
    uint8_t   priority;           /* 0 = moins prioritaire, 255 = plus  */
    bool      enabled;

    /* Logique */
    Condition_t      conditions[MAX_COND_PER_RULE];
    uint8_t          n_conditions;
    Pattern_Token_t  pattern_rpn[MAX_PATTERN_TOKENS];
    uint8_t          n_tokens;

    /* Triggers */
    Trigger_t triggers[MAX_TRIGGERS_PER_RULE];
    uint8_t   n_triggers;
} Rule_t;

#endif /* RULE_TYPES_H */