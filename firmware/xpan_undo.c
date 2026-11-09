#include "xpan_undo.h"

static unsigned int field_offset(unsigned int kind, unsigned int i) {
    if (kind == 1) return 0x18 + i;
    return i < 8 ? 4 + i : 0x10 + i - 8;
}

static void save_fields(const unsigned char *block, unsigned int kind,
                        unsigned char *out) {
    unsigned int i, count = kind == 1 ? 8 : 12;
    for (i = 0; i < count; ++i) out[i] = block[field_offset(kind, i)];
}

static void record_undo(struct gr4_xpan_buffer_undo *undo,
                        unsigned char *block, unsigned int kind,
                        const unsigned char *original) {
    unsigned int i, count = kind == 1 ? 8 : 12;
    for (i = 0; i < count; ++i) undo->original[i] = original[i];
    save_fields(block, kind, undo->applied);
    undo->target = block;
    undo->kind = kind;
}

int gr4_xpan_dng_apply_reversible(const struct gr4_xpan_capture_plan *plan,
                                 unsigned char *block, unsigned int bytes,
                                 struct gr4_xpan_buffer_undo *undo) {
    unsigned char original[12];
    if (!undo || undo->kind || !block || bytes < 0x20) return 0;
    save_fields(block, 1, original);
    if (!gr4_xpan_capture_dng_parameters(plan, block, bytes)) return 0;
    record_undo(undo, block, 1, original);
    return 1;
}

int gr4_xpan_ycbcr422_apply_reversible(const struct gr4_xpan_capture_plan *plan,
                                      unsigned char *block, unsigned int bytes,
                                      unsigned int y_bytes, unsigned int cbcr_bytes,
                                      struct gr4_xpan_buffer_undo *undo) {
    unsigned char original[12];
    if (!undo || undo->kind || !block || bytes < 0x1d) return 0;
    save_fields(block, 2, original);
    if (!gr4_xpan_capture_ycbcr422_source(plan, block, bytes, y_bytes, cbcr_bytes)) return 0;
    record_undo(undo, block, 2, original);
    return 1;
}

int gr4_xpan_buffer_restore(struct gr4_xpan_buffer_undo *undo,
                            unsigned char *block, unsigned int bytes) {
    unsigned int i, count;
    if (!undo) return 0;
    if (!undo->kind) return 1;
    if ((undo->kind != 1 && undo->kind != 2) || !block || undo->target != block ||
        bytes < (undo->kind == 1 ? 0x20u : 0x1du)) return 0;
    count = undo->kind == 1 ? 8 : 12;
    /* Preflight all bytes before any write; don't overwrite another task's
     * changes or restore another exposure's recycled descriptor. */
    for (i = 0; i < count; ++i)
        if (block[field_offset(undo->kind, i)] != undo->applied[i]) return 0;
    for (i = 0; i < count; ++i)
        block[field_offset(undo->kind, i)] = undo->original[i];
    undo->kind = 0;
    undo->target = 0;
    return 1;
}
