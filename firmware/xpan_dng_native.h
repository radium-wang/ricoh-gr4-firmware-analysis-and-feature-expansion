/* Kb636 virtual +0x34 adapter; not installed. Requires hard-float ARM ABI.
 * Install/remove and binding updates require image-worker quiescence. Capture
 * plan, bound object, vtable and this code must survive every in-flight call.
 */
#ifndef GR4_XPAN_DNG_NATIVE_H
#define GR4_XPAN_DNG_NATIVE_H
#include "xpan_capture.h"
struct gr4_xpan_dng_native_binding {
    void *object;
    const struct gr4_xpan_capture_plan *plan;
    unsigned int installed_vtable, ready;
};
void gr4_xpan_dng_native_bind(const struct gr4_xpan_dng_native_binding *);
/* r0=self,r1=width,r2=height,r3=left; stack=top,aspect,flag; s0=crop.
 * This ABI is DIFFERENT from the direct leaf 0x5387E108 (r0=width).
 * Default delegates to the original 0x5387E220 including every argument.
 */
void gr4_xpan_dng_native_virtual(void *, unsigned short *, unsigned short *,
    unsigned short *, unsigned short *, float, unsigned int, unsigned int);
#endif
