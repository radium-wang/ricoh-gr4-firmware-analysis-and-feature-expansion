#include "xpan_preview_coordinates.h"

/* Source dimensions are <=65535. Long division keeps remainder <denominator,
 * avoiding overflow and an unbound __aeabi_uldivmod dependency. */
static int scaled_edge(unsigned int span, unsigned int edge,
                       unsigned int source, unsigned int *out) {
    unsigned long long product = (unsigned long long)span * edge;
    unsigned int high = (unsigned int)(product >> 32), low = (unsigned int)product;
    unsigned int bit, remainder = 0, quotient = 0;
    if (!source || source > 65535u || edge > source) return 0;
    for (bit = 64; bit; --bit) {
        remainder = (remainder << 1) | (high >> 31);
        high = (high << 1) | (low >> 31);
        low <<= 1;
        if (remainder >= source) {
            remainder -= source;
            if (bit > 32) return 0;
            quotient |= 1u << (bit-1);
        }
    }
    *out = quotient;
    return 1;
}

static int window(const struct gr4_xpan_capture_plan *plan,
                   unsigned int full_width, unsigned int full_height,
                   const struct gr4_xpan_virtual_window *original,
                   struct gr4_xpan_virtual_window *out) {
    unsigned int top, bottom;
    if (!full_width || !full_height || full_width > 0x7FFFFFFFu ||
        full_height > 0x7FFFFFFFu || !original->width || !original->height ||
        original->left > full_width || original->top > full_height ||
        original->width > full_width-original->left ||
        original->height > full_height-original->top ||
        !scaled_edge(original->height, plan->photo.top, plan->source_height, &top) ||
        !scaled_edge(original->height, plan->photo.top+plan->photo.height,
                     plan->source_height, &bottom) || top >= bottom) return 0;
    out->width = original->width;
    out->height = bottom-top;
    out->left = original->left;
    out->top = original->top+top;
    return 1;
}

int gr4_xpan_preview_coordinates(const struct gr4_xpan_capture_plan *plan,
                                 unsigned int native_aspect,
                                 unsigned int native_crop_q13,
                                 const struct gr4_xpan_virtual_domains *domains,
                                 const struct gr4_xpan_virtual_windows *original,
                                 struct gr4_xpan_virtual_windows *out) {
    struct gr4_xpan_rect validated;
    struct gr4_xpan_virtual_windows next;
    unsigned int expected;
    if (!plan || !domains || !original || !out || native_aspect != 0 ||
        !gr4_xpan_capture_preview(plan, plan->source_width, plan->source_height,
                                  &validated)) return 0;
    expected = plan->native_crop_factor_bits == 0x3F800000u ? 8192u :
               plan->native_crop_factor_bits == 0x3FA04F89u ? 10260u : 14476u;
    if (native_crop_q13 != expected ||
        !window(plan, domains->logical_width, domains->logical_height,
                &original->logical, &next.logical) ||
        !window(plan, domains->mapped_width, domains->mapped_height,
                &original->mapped, &next.mapped)) return 0;
    /* Explicit stores keep the freestanding ABI free of memcpy helpers. */
    out->logical.width = next.logical.width;
    out->logical.height = next.logical.height;
    out->logical.left = next.logical.left;
    out->logical.top = next.logical.top;
    out->mapped.width = next.mapped.width;
    out->mapped.height = next.mapped.height;
    out->mapped.left = next.mapped.left;
    out->mapped.top = next.mapped.top;
    return 1;
}
