/* Routing helpers, not installed hooks. Call only on AppMain, with stable
 * original objects and the shared XPAN state lock held. A future installer
 * must supply ABI adapters and cover all callers, destruction and removal.
 */
#ifndef GR4_XPAN_SETTINGS_ROUTES_H
#define GR4_XPAN_SETTINGS_ROUTES_H
#include "xpan_settings_native.h"

enum gr4_xpan_capture_ready {
    GR4_XPAN_PREVIEW_READY = 1,
    GR4_XPAN_JPEG_READY = 2,
    GR4_XPAN_DNG_READY = 4,
    GR4_XPAN_ICON_READY = 8,
    GR4_XPAN_ALL_READY = 15
};
struct gr4_xpan_settings_routes {
    void *controller;
    struct gr4_xpan_state *state;
    /* Set only after real pipeline hooks and their rollback are verified. */
    unsigned int capture_ready;
};
/* Return 1 only when a complete five-item presentation was applied. */
/* Post-original refresh: never calls the hooked refresh/activation entry. */
int gr4_xpan_settings_present(struct gr4_xpan_settings_routes *);
int gr4_xpan_settings_refresh(struct gr4_xpan_settings_routes *);
int gr4_xpan_settings_activate(struct gr4_xpan_settings_routes *);
/* Route helpers consume only aspect-row operations. An ABI adapter retains
 * the original std::function storage/manager and delegates other rows.
 * A zero result does NOT authorize forwarding an aspect index >=4 to ROM.
 * On readiness loss the installer must withdraw the fifth presentation before
 * allowing original handlers; failure must refuse confirmation, never fall
 * through to the four-entry descriptor. These helpers do not implement that
 * installation/removal lifecycle or support a cloned controller vtable yet. */
int gr4_xpan_settings_list_confirm(struct gr4_xpan_settings_routes *, unsigned int);
int gr4_xpan_settings_button_confirm(struct gr4_xpan_settings_routes *);
int gr4_xpan_settings_event(struct gr4_xpan_settings_routes *, const void *);
#endif
