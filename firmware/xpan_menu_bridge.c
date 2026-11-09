#include "xpan_menu_bridge.h"

int gr4_xpan_menu_render_label(unsigned int index,
                               const struct gr4_xpan_menu_ops *ops,
                               void *context) {
    if (!ops || index >= gr4_xpan_aspect_menu_count()) return 0;
    if (index == 4) return ops->xpan_label && ops->xpan_label(context);
    return ops->native_label && ops->native_label(context, index);
}

int gr4_xpan_menu_apply(struct gr4_xpan_state *state, unsigned int index,
                         const struct gr4_xpan_menu_ops *ops, void *context) {
    struct gr4_xpan_state next;
    if (!state || !ops || !ops->native_select ||
        index >= gr4_xpan_aspect_menu_count()) return 0;
    next = *state;
    if (!gr4_xpan_aspect_menu_select(&next, index)) return 0;
    /* Project ID 4 never reaches the native four-entry table or property.
     * Its underlying source must be native 3:2 at menu index 0. */
    if (!ops->native_select(context, index == 4 ? 0 : index)) return 0;
    *state = next;
    return 1;
}
