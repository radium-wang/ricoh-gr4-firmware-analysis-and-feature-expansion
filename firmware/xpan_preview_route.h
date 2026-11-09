/* Preparation for the original crop-window selection/publication path.
 * No native object, queue, LCD or AF state is written by this interface.
 * A future native adapter must cover all consumers and prove task/cache
 * synchronization before publishing this prepared frame. */
#ifndef GR4_XPAN_PREVIEW_ROUTE_H
#define GR4_XPAN_PREVIEW_ROUTE_H
#include "xpan_preview_coordinates.h"

struct gr4_xpan_preview_frame {
    struct gr4_xpan_virtual_windows windows;
    unsigned int selector;
    struct gr4_xpan_virtual_window selected;
};
/* Original 0=full, 1=crop (including 16:9), 2=special/zoom window.
 * XPAN's native source aspect remains 0; its project menu choice is separate.
 * Prepare selector 1 even when the ordinary 3:2 route would select 0. Keep
 * special/zoom selector 2 untouched. Return 0 leaves out untouched; the caller
 * must delegate unchanged regular/special routes, never send project enum 4
 * to original aspect tables. A return of 1 is calculation success, not proof
 * that a native preview hook is installed or safe to publish. */
int gr4_xpan_preview_route_prepare(const struct gr4_xpan_capture_plan *,
                                   unsigned int native_aspect,
                                   unsigned int native_crop_q13,
                                   const struct gr4_xpan_virtual_domains *,
                                   const struct gr4_xpan_virtual_windows *,
                                   unsigned int native_selector,
                                   struct gr4_xpan_preview_frame *out);
#endif
