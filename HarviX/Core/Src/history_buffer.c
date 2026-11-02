#include "history_buffer.h"
#include <string.h>

/* ============================================================
 *  Un slot d'historique par UID actif.
 *  La table est indexée par un index interne, pas par UID
 *  (les UIDs étant attribués séquentiellement par le lecteur,
 *  on évite un tableau de 256 entrées dont la plupart vides).
 * ============================================================ */
typedef struct {
    uint8_t  uid;                                 /* 0 = slot libre        */
    uint8_t  count;                               /* valeurs valides       */
    uint8_t  head;                                /* index d'écriture      */
    float    values[MAX_HISTORY_PER_UID];
    uint32_t timestamps[MAX_HISTORY_PER_UID];
} History_Slot_t;

static History_Slot_t g_history[MAX_TRACKED_UIDS];

/* ============================================================
 *  Helpers internes
 * ============================================================ */
static History_Slot_t *find_or_create(uint8_t uid)
{
    /* Recherche existant */
    for (int i = 0; i < MAX_TRACKED_UIDS; ++i) {
        if (g_history[i].uid == uid) return &g_history[i];
    }
    /* Allocation d'un slot libre */
    for (int i = 0; i < MAX_TRACKED_UIDS; ++i) {
        if (g_history[i].uid == 0) {
            memset(&g_history[i], 0, sizeof(History_Slot_t));
            g_history[i].uid = uid;
            return &g_history[i];
        }
    }
    return NULL;  /* table pleine — l'UID ne sera pas suivi */
}

static const History_Slot_t *find(uint8_t uid)
{
    for (int i = 0; i < MAX_TRACKED_UIDS; ++i) {
        if (g_history[i].uid == uid) return &g_history[i];
    }
    return NULL;
}

/* Convertit l'index public (0=plus récent) en index physique du buffer */
static uint8_t physical_index(const History_Slot_t *s, uint8_t newest_offset)
{
    /* head pointe sur la prochaine case à écrire — la dernière écrite
     * est à (head - 1) modulo. Pour newest_offset=0 : (head-1).
     *                          newest_offset=1 : (head-2). etc. */
    int idx = (int)s->head - 1 - (int)newest_offset;
    while (idx < 0) idx += MAX_HISTORY_PER_UID;
    return (uint8_t)idx;
}

/* ============================================================
 *  API publique
 * ============================================================ */
void History_Init(void)
{
    memset(g_history, 0, sizeof(g_history));
}

void History_Reset(void)
{
    memset(g_history, 0, sizeof(g_history));
}

void History_Push(uint8_t uid, float value, uint32_t timestamp_ms)
{
    if (uid == 0) return;
    History_Slot_t *s = find_or_create(uid);
    if (s == NULL) return;

    s->values[s->head]     = value;
    s->timestamps[s->head] = timestamp_ms;
    s->head = (s->head + 1) % MAX_HISTORY_PER_UID;
    if (s->count < MAX_HISTORY_PER_UID) s->count++;
}

uint8_t History_GetCount(uint8_t uid)
{
    const History_Slot_t *s = find(uid);
    return (s != NULL) ? s->count : 0;
}

bool History_GetValue(uint8_t uid, uint8_t index, float *out_value)
{
    const History_Slot_t *s = find(uid);
    if (s == NULL || index >= s->count || out_value == NULL) return false;
    *out_value = s->values[physical_index(s, index)];
    return true;
}

bool History_GetTimestamp(uint8_t uid, uint8_t index, uint32_t *out_ts)
{
    const History_Slot_t *s = find(uid);
    if (s == NULL || index >= s->count || out_ts == NULL) return false;
    *out_ts = s->timestamps[physical_index(s, index)];
    return true;
}
