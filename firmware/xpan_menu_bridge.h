/* Offline menu dispatch contract. Target callback ABIs and installation are pending. */
#ifndef GR4_XPAN_MENU_BRIDGE_H
#define GR4_XPAN_MENU_BRIDGE_H
#include "xpan_core.h"

struct gr4_xpan_menu_ops {
    /* Native callbacks must be the original unmodified functions. An adapter
     * supplies each descriptor's actual calling convention and UI context. */
    int (*native_label)(void *context, unsigned int index);
    int (*xpan_label)(void *context);
    int (*native_select)(void *context, unsigned int index);
};

int gr4_xpan_menu_render_label(unsigned int index,
                               const struct gr4_xpan_menu_ops *ops,
                               void *context);
int gr4_xpan_menu_apply(struct gr4_xpan_state *state, unsigned int index,
                         const struct gr4_xpan_menu_ops *ops, void *context);
#endif
