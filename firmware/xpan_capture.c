#include "xpan_capture.h"

static int valid_plan(const struct gr4_xpan_capture_plan *plan) {
    if (!plan || plan->enabled != 1 || !plan->source_width || !plan->source_height ||
        !plan->raw_width || !plan->raw_height || plan->raw_width > 65535 ||
        plan->raw_height > 65535 || plan->raw_left > plan->raw_width ||
        plan->raw_top > plan->raw_height ||
        plan->source_width > plan->raw_width - plan->raw_left ||
        plan->source_height > plan->raw_height - plan->raw_top ||
        plan->photo.left != 0 || plan->photo.width != plan->source_width ||
        !plan->photo.height || plan->photo.top > plan->source_height ||
        plan->photo.height > plan->source_height - plan->photo.top ||
        plan->photo.top * 2 != plan->source_height - plan->photo.height ||
        (plan->native_crop_factor_bits != 0x3f800000u &&
         plan->native_crop_factor_bits != 0x3fa04f89u &&
         plan->native_crop_factor_bits != 0x3fe23119u)) return 0;
    return 1;
}

int gr4_xpan_capture_begin(const struct gr4_xpan_state *state,
                          unsigned int source_width, unsigned int source_height,
                          unsigned int raw_width, unsigned int raw_height,
                          unsigned int raw_left, unsigned int raw_top,
                          unsigned int width_alignment, unsigned int height_alignment,
                          unsigned int origin_alignment,
                          struct gr4_xpan_capture_plan *out) {
    struct gr4_xpan_capture_plan next;
    if (!out) return 0;
    /* Never leave a previous XPAN capture active when the new input fails. */
    out->enabled = 0;
    if (!state || state->crop_choice > GR4_CROP_50 ||
        state->aspect_choice != GR4_ASPECT_XPAN ||
        state->last_regular_aspect > GR4_ASPECT_1_1) return 0;
    next.enabled = 1;
    next.source_width = source_width;
    next.source_height = source_height;
    next.raw_width = raw_width;
    next.raw_height = raw_height;
    next.raw_left = raw_left;
    next.raw_top = raw_top;
    next.native_crop_factor_bits = state->crop_choice == GR4_CROP_OFF ? 0x3f800000u :
        state->crop_choice == GR4_CROP_35 ? 0x3fa04f89u : 0x3fe23119u;
    if (!gr4_xpan_full_width_rect(source_width, source_height, width_alignment,
                                 height_alignment, origin_alignment, &next.photo) ||
        (raw_left & (origin_alignment - 1)) ||
        ((raw_top + next.photo.top) & (origin_alignment - 1)) ||
        !valid_plan(&next)) return 0;
    *out = next;
    return 1;
}

int gr4_xpan_capture_preview(const struct gr4_xpan_capture_plan *plan,
                            unsigned int width, unsigned int height,
                            struct gr4_xpan_rect *out) {
    if (!valid_plan(plan)) return 0;
    return gr4_xpan_preview_rect(plan->source_width, plan->source_height,
                                 &plan->photo, width, height, out);
}

static void put16(unsigned char *data, unsigned int offset, unsigned int value) {
    data[offset] = (unsigned char)value;
    data[offset+1] = (unsigned char)(value >> 8);
}

static unsigned int get16(const unsigned char *data, unsigned int offset) {
    return data[offset] | ((unsigned int)data[offset+1] << 8);
}

static unsigned int get32(const unsigned char *data, unsigned int offset) {
    return get16(data, offset) | (get16(data, offset+2) << 16);
}

static void put32(unsigned char *data, unsigned int offset, unsigned int value) {
    put16(data, offset, value);
    put16(data, offset+2, value >> 16);
}

int gr4_xpan_capture_ycbcr422_source(const struct gr4_xpan_capture_plan *plan,
                                    unsigned char *block, unsigned int bytes,
                                    unsigned int y_bytes, unsigned int cbcr_bytes) {
    unsigned int pitch, required, offset, y, cbcr;
    if (!block || bytes < 0x1d || !valid_plan(plan) || block[0] != 1 ||
        get16(block, 0x10) != plan->source_width ||
        get16(block, 0x12) != plan->source_height ||
        (plan->source_width & 1)) return 0;
    /* 0x538D336C copies this descriptor. 0x536FB040 adjusts both planes by
     * the same pitch for the main source; 0x53702DA4 + its assertion text
     * identifies format 1 as 422. Format 2 (420) must not use this operation. */
    pitch = get16(block, 0x14);
    if (pitch < plan->source_width) return 0;
    required = (plan->source_height - 1) * pitch + plan->source_width;
    offset = plan->photo.top * pitch;
    y = get32(block, 4);
    cbcr = get32(block, 8);
    if (!y || !cbcr || y_bytes < required || cbcr_bytes < required ||
        y > 0xffffffffu - (required - 1) ||
        cbcr > 0xffffffffu - (required - 1)) return 0;
    /* Validate everything before writing. Preserve pitch, global dimensions,
     * allocation metadata and flags. Reapplying the plan fails the original
     * source-height check, preventing a second offset on the same descriptor. */
    put32(block, 4, y + offset);
    put32(block, 8, cbcr + offset);
    put16(block, 0x10, plan->photo.width);
    put16(block, 0x12, plan->photo.height);
    return 1;
}

int gr4_xpan_capture_dng_parameters(const struct gr4_xpan_capture_plan *plan,
                                   unsigned char *block, unsigned int bytes) {
    if (!block || bytes < 0x20 || !valid_plan(plan)) return 0;
    /* Kb636 stores: 0x5387E3F0..0x5387E3FC. Kb588 has a matching layout,
     * but a different origin; the caller must select the correct variant.
     * The full sensor dimensions and all other fields remain unchanged. */
    put16(block, 0x18, plan->photo.width);
    put16(block, 0x1a, plan->photo.height);
    put16(block, 0x1c, plan->raw_left + plan->photo.left);
    put16(block, 0x1e, plan->raw_top + plan->photo.top);
    return 1;
}
