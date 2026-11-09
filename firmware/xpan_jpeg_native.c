#include "xpan_jpeg_native.h"
_Static_assert(sizeof(void *) == 4, "GR IV 32-bit ABI required");
typedef void (*native_fn)(void *, unsigned int, unsigned int, float,
                          unsigned short *, unsigned short *);
static const struct gr4_xpan_jpeg_native_binding *binding;

void gr4_xpan_jpeg_native_bind(const struct gr4_xpan_jpeg_native_binding *next) {
    binding = next; /* All old users drained by the native caller. */
}

void gr4_xpan_jpeg_native_virtual(void *self, unsigned int size,
    unsigned int aspect, float crop, unsigned short *width, unsigned short *height) {
    const unsigned int caller = (unsigned int)__builtin_return_address(0);
    const struct gr4_xpan_jpeg_native_binding *current = binding;
    union { float number; unsigned int bits; } factor;
    unsigned char verified[0x20];
    struct gr4_xpan_rect destination;
    factor.number = crop;
    ((native_fn)0x538CFBF8u)(self, size, aspect, crop, width, height);
    if (!current || current->ready != 1 || !self || self != current->calculator ||
        *(const unsigned int *)self != current->installed_vtable ||
        !current->plan || !width || !height || aspect != GR4_ASPECT_3_2 ||
        factor.bits != current->plan->native_crop_factor_bits ||
        !gr4_xpan_capture_dng_parameters(current->plan, verified, sizeof(verified))) return;
    if (caller == 0x53711460u && size == current->source_size &&
        *width == current->plan->source_width && *height == current->plan->source_height) {
        *width = (unsigned short)current->plan->photo.width;
        *height = (unsigned short)current->plan->photo.height;
    } else if (caller == 0x536FB22Cu && size == current->destination_size &&
        *width <= current->plan->source_width && *height <= current->plan->source_height &&
        gr4_xpan_full_width_rect(*width, *height, current->width_alignment,
            current->height_alignment, current->origin_alignment, &destination)) {
        *width = (unsigned short)destination.width;
        *height = (unsigned short)destination.height;
    }
}
