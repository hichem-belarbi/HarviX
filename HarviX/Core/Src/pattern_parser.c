#include "pattern_parser.h"
#include <ctype.h>
#include <string.h>

/* ============================================================
 *  Pile d'opérateurs interne au shunting-yard
 * ============================================================ */
#define OP_STACK_MAX  16

typedef enum {
    OP_LPAREN,
    OP_AND,
    OP_OR,
    OP_NOT,
} Op_Stack_Entry_t;

/* Précédence : NOT > AND > OR  (standard logique booléenne) */
static int op_prec(Op_Stack_Entry_t op)
{
    switch (op) {
        case OP_NOT: return 3;
        case OP_AND: return 2;
        case OP_OR:  return 1;
        default:     return 0;
    }
}

/* Conversion opérateur de pile → token RPN */
static Token_Type_t op_to_token(Op_Stack_Entry_t op)
{
    switch (op) {
        case OP_AND: return TOK_AND;
        case OP_OR:  return TOK_OR;
        case OP_NOT: return TOK_NOT;
        default:     return TOK_AND;  /* unreachable */
    }
}

/* ============================================================
 *  Tokenizer + shunting-yard combinés
 *
 *  Lit le texte caractère par caractère, produit les tokens RPN
 *  à la volée.
 * ============================================================ */
static int append_token(Pattern_Token_t *out, uint8_t *len,
                        Token_Type_t type, uint8_t cond_index)
{
    if (*len >= MAX_PATTERN_TOKENS) return PATTERN_ERR_TOO_LONG;
    out[*len].type       = type;
    out[*len].cond_index = cond_index;
    (*len)++;
    return PATTERN_OK;
}

static bool match_word(const char *p, const char *word, uint8_t *consumed)
{
    uint8_t i = 0;
    while (word[i] != '\0') {
        if (toupper((unsigned char)p[i]) != word[i]) return false;
        i++;
    }
    /* Le mot ne doit pas être suivi d'un caractère alphanumérique
     * (sinon "ANDREW" matcherait "AND") */
    if (isalnum((unsigned char)p[i])) return false;
    *consumed = i;
    return true;
}

int Pattern_Compile(const char     *text,
                    uint8_t         n_conditions,
                    Pattern_Token_t *out_rpn,
                    uint8_t        *out_len)
{
    if (text == NULL || out_rpn == NULL || out_len == NULL) {
        return PATTERN_ERR_SYNTAX;
    }

    Op_Stack_Entry_t op_stack[OP_STACK_MAX];
    uint8_t          op_top = 0;
    *out_len = 0;

    const char *p = text;
    while (*p != '\0') {
        /* Espaces */
        if (isspace((unsigned char)*p)) { p++; continue; }

        /* Parenthèse ouvrante */
        if (*p == '(') {
            if (op_top >= OP_STACK_MAX) return PATTERN_ERR_TOO_LONG;
            op_stack[op_top++] = OP_LPAREN;
            p++;
            continue;
        }

        /* Parenthèse fermante : dépile jusqu'à la LPAREN correspondante */
        if (*p == ')') {
            bool found = false;
            while (op_top > 0) {
                Op_Stack_Entry_t op = op_stack[--op_top];
                if (op == OP_LPAREN) { found = true; break; }
                int rc = append_token(out_rpn, out_len, op_to_token(op), 0);
                if (rc != PATTERN_OK) return rc;
            }
            if (!found) return PATTERN_ERR_BAD_PARENS;
            p++;
            continue;
        }

        /* Condition cN — c suivi d'un nombre */
        if (*p == 'c' || *p == 'C') {
            const char *q = p + 1;
            if (!isdigit((unsigned char)*q)) return PATTERN_ERR_SYNTAX;
            uint16_t n = 0;
            while (isdigit((unsigned char)*q)) {
                n = n * 10 + (*q - '0');
                q++;
                if (n > 255) return PATTERN_ERR_SYNTAX;
            }
            if (n < 1 || n > n_conditions) return PATTERN_ERR_UNKNOWN_COND;
            int rc = append_token(out_rpn, out_len, TOK_COND, (uint8_t)(n - 1));
            if (rc != PATTERN_OK) return rc;
            p = q;
            continue;
        }

        /* Opérateurs textuels */
        uint8_t consumed = 0;
        Op_Stack_Entry_t new_op;

        if (match_word(p, "AND", &consumed))      new_op = OP_AND;
        else if (match_word(p, "OR",  &consumed)) new_op = OP_OR;
        else if (match_word(p, "NOT", &consumed)) new_op = OP_NOT;
        else return PATTERN_ERR_SYNTAX;

        /* Dépile tous les opérateurs de précédence >= au nouveau */
        while (op_top > 0) {
            Op_Stack_Entry_t top = op_stack[op_top - 1];
            if (top == OP_LPAREN) break;
            if (op_prec(top) < op_prec(new_op)) break;
            op_top--;
            int rc = append_token(out_rpn, out_len, op_to_token(top), 0);
            if (rc != PATTERN_OK) return rc;
        }

        if (op_top >= OP_STACK_MAX) return PATTERN_ERR_TOO_LONG;
        op_stack[op_top++] = new_op;
        p += consumed;
    }

    /* Vide la pile restante */
    while (op_top > 0) {
        Op_Stack_Entry_t op = op_stack[--op_top];
        if (op == OP_LPAREN) return PATTERN_ERR_BAD_PARENS;
        int rc = append_token(out_rpn, out_len, op_to_token(op), 0);
        if (rc != PATTERN_OK) return rc;
    }

    return (*out_len > 0) ? PATTERN_OK : PATTERN_ERR_SYNTAX;
}

/* ============================================================
 *  Évaluateur RPN — pile de booléens
 * ============================================================ */
#define EVAL_STACK_MAX  16

bool Pattern_Evaluate(const Pattern_Token_t *rpn,
                      uint8_t                n_tokens,
                      const bool            *cond_values)
{
    bool    stack[EVAL_STACK_MAX];
    uint8_t top = 0;

    for (uint8_t i = 0; i < n_tokens; ++i) {
        const Pattern_Token_t *tok = &rpn[i];

        switch (tok->type) {
            case TOK_COND:
                if (top >= EVAL_STACK_MAX) return false;
                stack[top++] = cond_values[tok->cond_index];
                break;

            case TOK_NOT:
                if (top < 1) return false;
                stack[top - 1] = !stack[top - 1];
                break;

            case TOK_AND:
                if (top < 2) return false;
                stack[top - 2] = stack[top - 2] && stack[top - 1];
                top--;
                break;

            case TOK_OR:
                if (top < 2) return false;
                stack[top - 2] = stack[top - 2] || stack[top - 1];
                top--;
                break;
        }
    }

    return (top == 1) ? stack[0] : false;
}
