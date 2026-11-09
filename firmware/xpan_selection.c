#include "xpan_selection.h"
int gr4_xpan_selection_prepare(const struct gr4_xpan_state *state,
    unsigned int index, const struct gr4_xpan_selection_geometry *geometry,
    struct gr4_xpan_selection *out) {
    struct gr4_xpan_selection next = {0};
    struct gr4_xpan_effective effective;
    if (!state || !out || !gr4_xpan_effective_settings(state,&effective)) return 0;
    next.state = *state;
    if (!gr4_xpan_aspect_menu_select(&next.state,index)) return 0;
    next.native_menu_index = index == 4u ? 0u : index;
    if (index == 4u) {
        if (!geometry || geometry->crop_choice != next.state.crop_choice ||
            !gr4_xpan_capture_begin(&next.state,
                geometry->source_width,geometry->source_height,
                geometry->raw_width,geometry->raw_height,
                geometry->raw_left,geometry->raw_top,
                geometry->width_alignment,geometry->height_alignment,
                geometry->origin_alignment,&next.plan)) return 0;
    }
    /* Regular selections publish a zero/disabled plan, not a previous crop. */
    *out = next;
    return 1;
}
int gr4_xpan_selection_commit(const struct gr4_xpan_selection_binding *binding,
    const struct gr4_xpan_selection *next) {
    struct gr4_xpan_effective effective;
    struct gr4_xpan_rect validation;
    if (!binding || !binding->state || !binding->shared_plan || !next ||
        !gr4_xpan_effective_settings(&next->state,&effective) ||
        next->native_menu_index >= 4u ||
        next->plan.enabled != effective.xpan_enabled) return 0;
    if (effective.xpan_enabled) {
        if (next->native_menu_index ||
            next->plan.native_crop_factor_bits != effective.crop_factor_bits ||
            !gr4_xpan_capture_preview(&next->plan,720u,480u,&validation)) return 0;
    } else {
        static const unsigned int order[4]={0u,1u,3u,2u};
        if (order[next->native_menu_index] != next->state.aspect_choice) return 0;
    }
    /* No callbacks run between these copies. Native readers must already be
     * drained and held; struct copying is NOT a hardware atomic publication. */
    *binding->shared_plan = next->plan;
    *binding->state = next->state;
    return 1;
}
