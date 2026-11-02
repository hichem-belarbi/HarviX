#include "primitives.h"
#include "history_buffer.h"
#include <math.h>

/* ============================================================
 *  Helpers : extraction de la fenêtre dans des tableaux locaux
 *  pour limiter les appels à History_GetValue.
 * ============================================================ */
static uint8_t fetch_window(uint8_t uid, uint8_t window,
                            float *vals, uint32_t *ts)
{
    uint8_t avail = History_GetCount(uid);
    if (avail == 0) return 0;
    if (window > avail) window = avail;
    if (window > MAX_HISTORY_PER_UID) window = MAX_HISTORY_PER_UID;

    /* On range du plus ancien (index 0) au plus récent (window-1)
     * pour faciliter les calculs (régression, etc.) */
    for (uint8_t i = 0; i < window; ++i) {
        uint8_t newest_offset = window - 1 - i;
        if (!History_GetValue(uid, newest_offset, &vals[i])) return 0;
        if (ts != NULL && !History_GetTimestamp(uid, newest_offset, &ts[i])) return 0;
    }
    return window;
}

/* ============================================================
 *  Implémentations des primitives
 * ============================================================ */

static bool prim_current(uint8_t uid, float *out)
{
    return History_GetValue(uid, 0, out);
}

static bool prim_mean(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n == 0) return false;

    float sum = 0.0f;
    for (uint8_t i = 0; i < n; ++i) sum += vals[i];
    *out = sum / (float)n;
    return true;
}

/* Pente par régression linéaire simple sur l'index (pas sur le temps).
 * Pour la pente vraie temps, voir prim_deriv_time. */
static bool prim_slope(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n < 2) return false;

    float sum_x = 0, sum_y = 0, sum_xy = 0, sum_xx = 0;
    for (uint8_t i = 0; i < n; ++i) {
        float x = (float)i;
        float y = vals[i];
        sum_x  += x;
        sum_y  += y;
        sum_xy += x * y;
        sum_xx += x * x;
    }
    float denom = (float)n * sum_xx - sum_x * sum_x;
    if (fabsf(denom) < 1e-9f) return false;
    *out = ((float)n * sum_xy - sum_x * sum_y) / denom;
    return true;
}

static bool prim_stddev(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n < 2) return false;

    float mean = 0.0f;
    for (uint8_t i = 0; i < n; ++i) mean += vals[i];
    mean /= (float)n;

    float var = 0.0f;
    for (uint8_t i = 0; i < n; ++i) {
        float d = vals[i] - mean;
        var += d * d;
    }
    *out = sqrtf(var / (float)n);
    return true;
}

static bool prim_min(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n == 0) return false;
    float m = vals[0];
    for (uint8_t i = 1; i < n; ++i) if (vals[i] < m) m = vals[i];
    *out = m;
    return true;
}

static bool prim_max(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n == 0) return false;
    float m = vals[0];
    for (uint8_t i = 1; i < n; ++i) if (vals[i] > m) m = vals[i];
    *out = m;
    return true;
}

/* Proportion de différences successives positives.
 * 1.0 = strictement croissant, 0.0 = strictement décroissant,
 * 0.5 = autant de hausses que de baisses. */
static bool prim_monotonicity(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n < 2) return false;

    uint8_t pos = 0;
    for (uint8_t i = 1; i < n; ++i) {
        if (vals[i] > vals[i - 1]) pos++;
    }
    *out = (float)pos / (float)(n - 1);
    return true;
}

/* Fréquence des changements de signe dans les différences successives.
 * 0.0 = signal monotone ou constant, ~1.0 = signal très bruyant. */
static bool prim_noise_level(uint8_t uid, uint8_t window, float *out)
{
    float vals[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, NULL);
    if (n < 3) return false;

    uint8_t flips = 0;
    int prev_sign = 0;
    for (uint8_t i = 1; i < n; ++i) {
        float d = vals[i] - vals[i - 1];
        int sign = (d > 0.0f) - (d < 0.0f);
        if (sign != 0 && prev_sign != 0 && sign != prev_sign) flips++;
        if (sign != 0) prev_sign = sign;
    }
    *out = (float)flips / (float)(n - 2);
    return true;
}

/* Dérivée temporelle vraie : (val[récent] - val[ancien]) / Δt en secondes */
static bool prim_deriv_time(uint8_t uid, uint8_t window, float *out)
{
    float    vals[MAX_HISTORY_PER_UID];
    uint32_t ts[MAX_HISTORY_PER_UID];
    uint8_t n = fetch_window(uid, window, vals, ts);
    if (n < 2) return false;

    uint32_t dt_ms = ts[n - 1] - ts[0];
    if (dt_ms == 0) return false;
    *out = (vals[n - 1] - vals[0]) * 1000.0f / (float)dt_ms;
    return true;
}

/* |valeur courante - valeur du dernier déclenchement| */
static bool prim_delta_last(uint8_t uid, float last_trigger_value, float *out)
{
    float current;
    if (!History_GetValue(uid, 0, &current)) return false;
    /* NaN signifie « jamais déclenché » → on retourne une grande valeur
     * pour que la condition se déclenche au premier passage. */
    if (isnan(last_trigger_value)) {
        *out = INFINITY;
    } else {
        *out = fabsf(current - last_trigger_value);
    }
    return true;
}

/* Distance au plus proche multiple de `base`.
 * Retourne fmodf replié sur [-base/2, base/2] en valeur absolue.
 * Ainsi 19.8 avec base=10 donne 0.2 (proche de 20). */
static bool prim_near_multiple(uint8_t uid, float base, float *out)
{
    if (base <= 0.0f) return false;
    float current;
    if (!History_GetValue(uid, 0, &current)) return false;

    float r = fmodf(current, base);
    if (r < 0.0f) r += base;
    if (r > base * 0.5f) r = base - r;
    *out = r;
    return true;
}

/* ============================================================
 *  Dispatcher
 * ============================================================ */
bool Primitive_Eval(Primitive_t fn,
                    uint8_t     uid,
                    uint8_t     window,
                    float       param,
                    float       last_trigger_value,
                    float      *out)
{
    if (out == NULL) return false;
    switch (fn) {
        case PRIM_CURRENT:       return prim_current(uid, out);
        case PRIM_MEAN:          return prim_mean(uid, window, out);
        case PRIM_SLOPE:         return prim_slope(uid, window, out);
        case PRIM_STDDEV:        return prim_stddev(uid, window, out);
        case PRIM_MIN:           return prim_min(uid, window, out);
        case PRIM_MAX:           return prim_max(uid, window, out);
        case PRIM_MONOTONICITY:  return prim_monotonicity(uid, window, out);
        case PRIM_NOISE_LEVEL:   return prim_noise_level(uid, window, out);
        case PRIM_DERIV_TIME:    return prim_deriv_time(uid, window, out);
        case PRIM_DELTA_LAST:    return prim_delta_last(uid, last_trigger_value, out);
        case PRIM_NEAR_MULTIPLE: return prim_near_multiple(uid, param, out);
        default:                 return false;
    }
}
