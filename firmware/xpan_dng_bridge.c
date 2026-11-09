#include "xpan_dng_bridge.h"
_Static_assert(sizeof(unsigned short) == 2, "16-bit output required");
_Static_assert(sizeof(float) == 4, "32-bit crop factor required");
static gr4_dng_original_fn original_window;
static const struct gr4_xpan_capture_plan *active_capture;
static unsigned int pipeline_ready;

void gr4_xpan_dng_bind(gr4_dng_original_fn original,
                       const struct gr4_xpan_capture_plan *plan, unsigned int ready) {
    pipeline_ready = 0;
    original_window = original;
    active_capture = plan;
    pipeline_ready = ready == 1 && original && plan;
}

void gr4_xpan_dng_disable(void) {
    pipeline_ready = 0;
    active_capture = 0;
    /* Keep original_window alive until native hooks have been restored and
     * all calls have drained. Clearing it here would break ordinary DNG. */
}

void gr4_xpan_dng_leaf(unsigned short *width, unsigned short *height,
                      unsigned short *left, unsigned short *top,
                      float crop_factor, unsigned int aspect) {
    unsigned char fields[0x20];
    union { float value; unsigned int bits; } factor;
    factor.value = crop_factor;
    if (pipeline_ready && width && height && left && top &&
        active_capture && factor.bits == active_capture->native_crop_factor_bits &&
        aspect == GR4_ASPECT_3_2 &&
        gr4_xpan_capture_dng_parameters(active_capture, fields, sizeof(fields))) {
        *width = (unsigned short)(fields[0x18] | ((unsigned int)fields[0x19] << 8));
        *height = (unsigned short)(fields[0x1a] | ((unsigned int)fields[0x1b] << 8));
        *left = (unsigned short)(fields[0x1c] | ((unsigned int)fields[0x1d] << 8));
        *top = (unsigned short)(fields[0x1e] | ((unsigned int)fields[0x1f] << 8));
        return;
    }
    if (original_window) original_window(width, height, left, top, crop_factor, aspect);
}
