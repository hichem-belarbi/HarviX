#include "rules_store.h"
#include "cmsis_os2.h"
#include <string.h>

/* ============================================================
 *  État du store
 * ============================================================ */
static Rule_t       g_rules[MAX_RULES];
static uint8_t      g_count   = 0;
static uint32_t     g_version = 0;
static osMutexId_t  g_mutex;

/* ============================================================
 *  Helpers internes
 * ============================================================ */
static int find_index(uint8_t rule_id)
{
    for (int i = 0; i < g_count; ++i) {
        if (g_rules[i].rule_id == rule_id) return i;
    }
    return -1;
}

/* Trie la table par priorité croissante après chaque modification.
 * Le moteur évalue dans cet ordre, donc les règles plus prioritaires
 * (priority haute) sont évaluées en dernier et leurs effets persistent. */
static void sort_by_priority(void)
{
    /* Insertion sort — suffisant pour 20 éléments */
    for (int i = 1; i < g_count; ++i) {
        Rule_t key = g_rules[i];
        int j = i - 1;
        while (j >= 0 && g_rules[j].priority > key.priority) {
            g_rules[j + 1] = g_rules[j];
            j--;
        }
        g_rules[j + 1] = key;
    }
}

/* ============================================================
 *  Init
 * ============================================================ */
void RulesStore_Init(void)
{
    memset(g_rules, 0, sizeof(g_rules));
    g_count   = 0;
    g_version = 0;

    const osMutexAttr_t attr = { .name = "rules_store" };
    g_mutex = osMutexNew(&attr);
}

/* ============================================================
 *  API d'écriture
 * ============================================================ */
int RulesStore_Add(const Rule_t *rule)
{
    if (rule == NULL) return STORE_ERR_NOT_FOUND;

    osMutexAcquire(g_mutex, osWaitForever);

    int rc;
    if (find_index(rule->rule_id) >= 0) {
        /* Même ID déjà présent → on remplace (équivalent à update) */
        rc = RulesStore_Update(rule);
        osMutexRelease(g_mutex);
        return rc;
    }
    if (g_count >= MAX_RULES) {
        osMutexRelease(g_mutex);
        return STORE_ERR_FULL;
    }

    g_rules[g_count++] = *rule;
    sort_by_priority();
    g_version++;

    osMutexRelease(g_mutex);
    return STORE_OK;
}

int RulesStore_Remove(uint8_t rule_id)
{
    osMutexAcquire(g_mutex, osWaitForever);

    int idx = find_index(rule_id);
    if (idx < 0) {
        osMutexRelease(g_mutex);
        return STORE_ERR_NOT_FOUND;
    }

    /* Compactage */
    for (int i = idx; i < g_count - 1; ++i) {
        g_rules[i] = g_rules[i + 1];
    }
    g_count--;
    memset(&g_rules[g_count], 0, sizeof(Rule_t));
    g_version++;

    osMutexRelease(g_mutex);
    return STORE_OK;
}

int RulesStore_Update(const Rule_t *rule)
{
    if (rule == NULL) return STORE_ERR_NOT_FOUND;

    osMutexAcquire(g_mutex, osWaitForever);

    int idx = find_index(rule->rule_id);
    if (idx < 0) {
        osMutexRelease(g_mutex);
        return STORE_ERR_NOT_FOUND;
    }

    g_rules[idx] = *rule;
    sort_by_priority();
    g_version++;

    osMutexRelease(g_mutex);
    return STORE_OK;
}

void RulesStore_ClearAll(void)
{
    osMutexAcquire(g_mutex, osWaitForever);
    memset(g_rules, 0, sizeof(g_rules));
    g_count = 0;
    g_version++;
    osMutexRelease(g_mutex);
}

/* ============================================================
 *  API de lecture
 * ============================================================ */
void RulesStore_GetSnapshot(Rules_Snapshot_t *out)
{
    if (out == NULL) return;

    osMutexAcquire(g_mutex, osWaitForever);
    memcpy(out->rules, g_rules, sizeof(g_rules));
    out->count   = g_count;
    out->version = g_version;
    osMutexRelease(g_mutex);
}

uint32_t RulesStore_GetVersion(void)
{
    /* Lecture atomique d'un uint32 — pas besoin de mutex sur Cortex-M4 */
    return g_version;
}
