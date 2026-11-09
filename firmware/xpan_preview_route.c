#include "xpan_preview_route.h"

int gr4_xpan_preview_route_prepare(const struct gr4_xpan_capture_plan *plan,
                                   unsigned int native_aspect,
                                   unsigned int native_crop_q13,
                                   const struct gr4_xpan_virtual_domains *domains,
                                   const struct gr4_xpan_virtual_windows *original,
                                   unsigned int native_selector,
                                   struct gr4_xpan_preview_frame *out) {
    struct gr4_xpan_virtual_windows next;
    if (!out || native_selector > 1u ||
        !gr4_xpan_preview_coordinates(plan, native_aspect, native_crop_q13,
                                       domains, original, &next)) return 0;
    out->windows.logical.width = next.logical.width;
    out->windows.logical.height = next.logical.height;
    out->windows.logical.left = next.logical.left;
    out->windows.logical.top = next.logical.top;
    out->windows.mapped.width = next.mapped.width;
    out->windows.mapped.height = next.mapped.height;
    out->windows.mapped.left = next.mapped.left;
    out->windows.mapped.top = next.mapped.top;
    out->selector = 1u;
    out->selected.width = next.logical.width;
    out->selected.height = next.logical.height;
    out->selected.left = next.logical.left;
    out->selected.top = next.logical.top;
    return 1;
}
