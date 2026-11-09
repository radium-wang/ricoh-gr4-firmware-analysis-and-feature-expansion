/* Binding for the verified Kb636 leaf ABI. No hook installation is performed. */
#ifndef GR4_XPAN_DNG_BRIDGE_H
#define GR4_XPAN_DNG_BRIDGE_H
#include "xpan_capture.h"
typedef void (*gr4_dng_original_fn)(unsigned short *, unsigned short *,
                                    unsigned short *, unsigned short *, float, unsigned int);
/* original must be the unmodified function or an installer-verified trampoline.
 * plan is immutable until this capture finishes. Native task synchronization,
 * complete preview/JPEG integration and safe unloading are installer duties.
 * ready must remain 0 until those conditions are actually verified. */
void gr4_xpan_dng_bind(gr4_dng_original_fn, const struct gr4_xpan_capture_plan *, unsigned int);
/* First rollback step: stop XPAN overrides but retain the original delegate.
 * Caller must synchronize native tasks. This does not remove a hook, drain
 * in-flight calls or make the module safe to unload. */
void gr4_xpan_dng_disable(void);
void gr4_xpan_dng_leaf(unsigned short *, unsigned short *, unsigned short *,
                      unsigned short *, float, unsigned int);
#endif
