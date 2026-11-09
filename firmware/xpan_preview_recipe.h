/* Candidate native recipe fields, not an installer or display-ready flag.
 * Native owner must serialize/drain users and keep the plan/record live.
 * No allocation or pixel-buffer dimensions are changed by these operations. */
#ifndef GR4_XPAN_PREVIEW_RECIPE_H
#define GR4_XPAN_PREVIEW_RECIPE_H
#include "xpan_capture.h"
struct gr4_xpan_preview_recipe_undo {
    unsigned char *target;
    unsigned int active;
    unsigned short original_height, original_top, applied_height, applied_top;
    unsigned short original_width, reserved;
    unsigned int crop_q13;
};
/* Input is the original aspect=0 recipe after 0x53647498 returns. Alignment
 * is supplied by the owner; hardware alignment requirements remain unverified.
 * Writes only +BD8 (active H) and +BE2 (center Y), preserving full references.
 * Failure leaves both recipe and undo untouched. Repeated native regeneration
 * is accepted only for the same target and saved original fields. */
int gr4_xpan_preview_recipe_apply(unsigned char *, unsigned int bytes,
                                  const struct gr4_xpan_capture_plan *,
                                  unsigned int crop_q13, unsigned int alignment,
                                  struct gr4_xpan_preview_recipe_undo *);
/* Call with owner paused. Unknown/new native fields are not overwritten.
 * This is local recipe restoration, not LCD/AF/property notification recovery. */
int gr4_xpan_preview_recipe_restore(unsigned char *, unsigned int bytes,
                                    struct gr4_xpan_preview_recipe_undo *);
/* After the original 0x53643800..0x536438A0 regeneration slice rewrites H
 * but leaves the known XPAN Y behind. Owner MUST pause/drain users first.
 * Accept only the same undo/width/factor and exactly that mixed state. This
 * is a portable reconciliation candidate, not a call-site hook/installer. */
int gr4_xpan_preview_recipe_reapply_after_regeneration(unsigned char *,
    unsigned int bytes, const struct gr4_xpan_capture_plan *,
    unsigned int crop_q13, unsigned int alignment,
    struct gr4_xpan_preview_recipe_undo *);
#endif
