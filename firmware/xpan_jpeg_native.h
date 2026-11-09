/* Offline candidate only. Shared calculator slot +8, hard-float ARM ABI.
 * There is no installer. Binding publication/removal requires all calculator
 * users stopped and drained; active capture state must be serialized with its
 * owning image worker. Object, cloned table, plan and code remain live until
 * every call has returned. A matching ROM return address alone is NOT proof
 * of capture ownership. These native synchronization requirements are pending.
 */
#ifndef GR4_XPAN_JPEG_NATIVE_H
#define GR4_XPAN_JPEG_NATIVE_H
#include "xpan_capture.h"
struct gr4_xpan_jpeg_native_binding {
    void *calculator;
    const struct gr4_xpan_capture_plan *plan;
    unsigned int installed_vtable, ready;
    unsigned int source_size, destination_size;
    unsigned int width_alignment, height_alignment, origin_alignment;
};
void gr4_xpan_jpeg_native_bind(const struct gr4_xpan_jpeg_native_binding *);
/* r0=self,r1=size,r2=aspect,r3=width; stack=height; s0=crop.
 * Delegates every call first. Only LR=53711460 (source publisher) and
 * LR=536FB22C (BackResize destination) can replace the returned dimensions.
 * In particular LR=537114A4 and 5387E1C4 retain full-source dimensions.
 */
void gr4_xpan_jpeg_native_virtual(void *, unsigned int, unsigned int, float,
                                  unsigned short *, unsigned short *);
#endif
