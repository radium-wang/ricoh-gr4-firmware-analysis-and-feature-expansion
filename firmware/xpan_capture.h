/* Per-capture plan and verified DNG parameter layout; hook installation pending. */
#ifndef GR4_XPAN_CAPTURE_H
#define GR4_XPAN_CAPTURE_H
#include "xpan_core.h"
struct gr4_xpan_capture_plan {
    unsigned int enabled, source_width, source_height;
    unsigned int raw_width, raw_height, raw_left, raw_top;
    unsigned int native_crop_factor_bits;
    struct gr4_xpan_rect photo;
};
/* Caller must hold its native state lock while providing this state snapshot. */
int gr4_xpan_capture_begin(const struct gr4_xpan_state *, unsigned int, unsigned int,
                          unsigned int, unsigned int, unsigned int, unsigned int,
                          unsigned int, unsigned int, unsigned int,
                          struct gr4_xpan_capture_plan *);
int gr4_xpan_capture_preview(const struct gr4_xpan_capture_plan *, unsigned int,
                            unsigned int, struct gr4_xpan_rect *);
/* Pure buffer operation: writes four verified little-endian ushort fields.
 * This is a native image-map parameter block, not a TIFF/DNG file editor. */
int gr4_xpan_capture_dng_parameters(const struct gr4_xpan_capture_plan *,
                                   unsigned char *, unsigned int);
/* Pure descriptor operation for verified native format 1 (YCbCr 422).
 * The caller supplies independently verified allocation lengths for both
 * planes. No pixels are read/written here. Native task/cache synchronization
 * and matching destination dimensions remain integration requirements. */
int gr4_xpan_capture_ycbcr422_source(const struct gr4_xpan_capture_plan *,
                                    unsigned char *, unsigned int,
                                    unsigned int, unsigned int);
#endif
