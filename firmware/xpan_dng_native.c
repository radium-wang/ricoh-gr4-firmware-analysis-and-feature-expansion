#include "xpan_dng_native.h"
_Static_assert(sizeof(void *) == 4, "GR IV 32-bit ABI required");
typedef void (*native_fn)(void *, unsigned short *, unsigned short *,
    unsigned short *, unsigned short *, float, unsigned int, unsigned int);
static const struct gr4_xpan_dng_native_binding *binding;

void gr4_xpan_dng_native_bind(const struct gr4_xpan_dng_native_binding *next) {
    /* Caller has stopped the image worker and drained all old calls. */
    binding = next;
}

void gr4_xpan_dng_native_virtual(void *self, unsigned short *width,
    unsigned short *height, unsigned short *left, unsigned short *top,
    float crop, unsigned int aspect, unsigned int flag) {
    const struct gr4_xpan_dng_native_binding *current = binding;
    unsigned char block[0x20];
    union { float number; unsigned int bits; } factor;
    factor.number = crop;
    /* Run the original calculation first; it preserves both current-window
     * and full-source dimension queries and the original unsupported-flag
     * behavior. No global ImageResolutionCalculator slot is changed. */
    ((native_fn)0x5387E220u)(self, width, height, left, top, crop, aspect, flag);
    if (!current || current->ready != 1 || self != current->object ||
        !self || *(const unsigned int *)self != current->installed_vtable ||
        !current->plan || flag || aspect != GR4_ASPECT_3_2 ||
        factor.bits != current->plan->native_crop_factor_bits ||
        !width || !height || !left || !top ||
        !gr4_xpan_capture_dng_parameters(current->plan, block, sizeof(block))) return;
    *width = block[0x18] | ((unsigned int)block[0x19] << 8);
    *height = block[0x1A] | ((unsigned int)block[0x1B] << 8);
    *left = block[0x1C] | ((unsigned int)block[0x1D] << 8);
    *top = block[0x1E] | ((unsigned int)block[0x1F] << 8);
}
