/* Atomic-under-owner-lock menu state and shared plan preparation.
 * Native UI/capture owner must pause/drain every reader before committing.
 * Geometry must describe the CURRENT source for the state crop choice;
 * these interfaces neither query hardware nor certify its alignment. */
#ifndef GR4_XPAN_SELECTION_H
#define GR4_XPAN_SELECTION_H
#include "xpan_capture.h"
struct gr4_xpan_selection_geometry {
    unsigned int crop_choice, source_width, source_height;
    unsigned int raw_width, raw_height, raw_left, raw_top;
    unsigned int width_alignment, height_alignment, origin_alignment;
};
struct gr4_xpan_selection_binding {
    struct gr4_xpan_state *state;
    struct gr4_xpan_capture_plan *shared_plan;
    const struct gr4_xpan_selection_geometry *geometry;
};
struct gr4_xpan_selection {
    struct gr4_xpan_state state;
    struct gr4_xpan_capture_plan plan;
    unsigned int native_menu_index;
};
/* Failure leaves out unchanged. Native menu order is preserved. */
int gr4_xpan_selection_prepare(const struct gr4_xpan_state *, unsigned int,
    const struct gr4_xpan_selection_geometry *, struct gr4_xpan_selection *);
/* Binding is owned by the native caller. Commit only while all shared-plan
 * users are paused/drained; one pointer must be used by preview/JPEG/DNG. */
int gr4_xpan_selection_commit(const struct gr4_xpan_selection_binding *,
                              const struct gr4_xpan_selection *);
#endif
