/* Fixed 01.11.10.07 ABI candidate; no call-site hook/installer.
 * The original recipe helper is a direct ROM call, not a virtual slot.
 * Only use within its owning LiveViewProcess, with all binding/plan/undo
 * publication and removal serialized and image users paused/drained. The
 * collection's eight recipe slots are checked, but identity checks do not prove
 * quiescence, ownership of an active frame, or task/cache synchronization. */
#ifndef GR4_XPAN_PREVIEW_RECIPE_NATIVE_H
#define GR4_XPAN_PREVIEW_RECIPE_NATIVE_H
#include "xpan_preview_recipe.h"
struct gr4_xpan_preview_recipe_binding {
    void *recipe, *manager, *process;
    const struct gr4_xpan_capture_plan *plan;
    struct gr4_xpan_preview_recipe_undo *undo;
    unsigned int ready, height_alignment;
    void *collection;
};
void gr4_xpan_preview_recipe_bind(const struct gr4_xpan_preview_recipe_binding *);
/* Exact helper ABI: r0=recipe,r1=aspect,r2=extra,r3=mode; stack=crop Q13.
 * Calls original first, then only alters a matching still/ordinary recipe.
 * A ready binding is a caller contract, not evidence of hardware readiness. */
void gr4_xpan_preview_recipe_native(void *, unsigned int, unsigned int,
                                    unsigned int, unsigned int);
/* Post-regeneration candidate used by the fixed instruction detour. Uses
 * the same restrictive binding/owner checks; does not enable new managers.
 * Caller must hold the paused/drained-owner contract through the detour. */
void gr4_xpan_preview_recipe_regenerated_native(void *);
#endif
