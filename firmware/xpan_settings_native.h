/* GR IV 01.11.10.07 row callback backend; installation is not included.
 * Invoke only on the original UI thread with stable controller/item lifetimes
 * and the project's state lock held. Publish image hooks before enabling this
 * row. The original refresh, navigation and all three confirmation routes
 * still require wrappers; this file alone cannot add a functional menu item.
 */
#ifndef GR4_XPAN_SETTINGS_NATIVE_H
#define GR4_XPAN_SETTINGS_NATIVE_H
#include "xpan_core.h"
#include "xpan_selection.h"

/* Optional state/plan publication for every existing confirmation route.
 * Binding/geometry/plan must remain live. Publish/remove while every image
 * and UI reader is stopped/drained, not merely while a UI state lock is held.
 * Geometry is caller-supplied and tied to the current crop choice. */
void gr4_xpan_settings_bind_selection(const struct gr4_xpan_selection_binding *);

/* Exact native register order: label r0=controller,r1=item,r2=index. */
int gr4_xpan_settings_label(void *controller, void *item, unsigned int index);
/* Original selected callback is a predicate, not an index getter. */
int gr4_xpan_settings_selected(const struct gr4_xpan_state *, unsigned int index);
/* confirm selects the original confirm-and-refresh path; otherwise setter.
 * A successful result means dispatch completed, not capture verification. */
int gr4_xpan_settings_select(void *controller, struct gr4_xpan_state *,
                              unsigned int index, unsigned int confirm);
/* After local preview/image undo completes with readers paused/drained,
 * return to last_regular_aspect through the same native property dispatch.
 * With a selection binding this also clears the shared plan BEFORE observers.
 * Then withdraw the fifth presentation, unbind adapters and release code only
 * after native hooks are restored and no callback remains in flight. */
int gr4_xpan_settings_deactivate(void *, struct gr4_xpan_state *, unsigned int);

#endif
