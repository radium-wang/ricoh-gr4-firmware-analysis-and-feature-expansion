/* Undo for the project's buffer adapters; no camera patch installer. */
#ifndef GR4_XPAN_UNDO_H
#define GR4_XPAN_UNDO_H
#include "xpan_capture.h"
struct gr4_xpan_buffer_undo {
    unsigned char *target;
    unsigned int kind; /* Zero-initialize. 1=DNG fields, 2=422 descriptor. */
    unsigned char original[12], applied[12];
};
/* Caller owns a stable, non-overlapping buffer and journal, under its native
 * lock. A live journal cannot be overwritten. Buffer lifetime must extend
 * through restore; journal and buffer are not persisted or dereferenced by
 * any camera command in this module. */
int gr4_xpan_dng_apply_reversible(const struct gr4_xpan_capture_plan *,
                                 unsigned char *, unsigned int,
                                 struct gr4_xpan_buffer_undo *);
int gr4_xpan_ycbcr422_apply_reversible(const struct gr4_xpan_capture_plan *,
                                      unsigned char *, unsigned int,
                                      unsigned int, unsigned int,
                                      struct gr4_xpan_buffer_undo *);
/* Restores only owned fields, after checking that every field still matches
 * this journal's applied value. Conflict/wrong target/short buffer: no write.
 * Already inactive: success, no write. This cannot undo an encoded photo. */
int gr4_xpan_buffer_restore(struct gr4_xpan_buffer_undo *,
                            unsigned char *, unsigned int);
#endif
