/* Coordinate calculation only: no LCD or AF hook is installed by this API.
 * The native caller must establish that both windows describe the same full
 * 3:2 source/crop as the plan, and copy/publish them under verified native locks.
 * Do not enable PREVIEW_READY from these calculations alone. */
#ifndef GR4_XPAN_PREVIEW_COORDINATES_H
#define GR4_XPAN_PREVIEW_COORDINATES_H
#include "xpan_capture.h"

/* Exact W,H,X,Y order observed at LiveViewInformation +24/+34. */
struct gr4_xpan_virtual_window {
    unsigned int width, height, left, top;
};
struct gr4_xpan_virtual_windows {
    struct gr4_xpan_virtual_window logical, mapped;
};
struct gr4_xpan_virtual_domains {
    unsigned int logical_width, logical_height, mapped_width, mapped_height;
};
/* Apply the JPEG/DNG plan's actual aligned photo edges to both native windows.
 * Preserve original horizontal crop/origin. Compute each vertical edge before
 * subtraction, not a separate approximate 65:24 rectangle. On failure out is
 * untouched. original may alias out. Domains are caller-supplied evidence,
 * not proof that these windows control actual display pixels. */
int gr4_xpan_preview_coordinates(const struct gr4_xpan_capture_plan *plan,
                                 unsigned int native_aspect,
                                 unsigned int native_crop_q13,
                                 const struct gr4_xpan_virtual_domains *domains,
                                 const struct gr4_xpan_virtual_windows *original,
                                 struct gr4_xpan_virtual_windows *out);
#endif
