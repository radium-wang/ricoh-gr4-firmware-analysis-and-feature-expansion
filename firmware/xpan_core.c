/* Freestanding calculation/state core. No device I/O, hooks, allocation or persistence. */
#include "xpan_core.h"
_Static_assert(sizeof(unsigned int) == 4, "32-bit unsigned int required");

int gr4_xpan_select_crop(struct gr4_xpan_state *state, unsigned int choice) {
    if (!state || choice > GR4_CROP_50) return 0;
    state->crop_choice = choice;
    return 1;
}

int gr4_xpan_select_aspect(struct gr4_xpan_state *state, unsigned int aspect) {
    if (!state || aspect > GR4_ASPECT_XPAN ||
        state->last_regular_aspect > GR4_ASPECT_1_1) return 0;
    state->aspect_choice = aspect;
    if (aspect != GR4_ASPECT_XPAN) state->last_regular_aspect = aspect;
    return 1;
}

int gr4_xpan_deactivate(struct gr4_xpan_state *state) {
    if (!state || state->last_regular_aspect > GR4_ASPECT_1_1 ||
        state->aspect_choice > GR4_ASPECT_XPAN) return 0;
    if (state->aspect_choice == GR4_ASPECT_XPAN)
        state->aspect_choice = state->last_regular_aspect;
    return 1;
}

int gr4_xpan_effective_settings(const struct gr4_xpan_state *state,
                               struct gr4_xpan_effective *out) {
    static const unsigned int factors[] = {0x3f800000, 0x3fa04f89, 0x3fe23119};
    if (!state || !out || state->crop_choice > GR4_CROP_50 ||
        state->aspect_choice > GR4_ASPECT_XPAN ||
        state->last_regular_aspect > GR4_ASPECT_1_1) return 0;
    out->xpan_enabled = state->aspect_choice == GR4_ASPECT_XPAN;
    out->native_crop_mode = state->crop_choice;
    /* Native aspect consumers only accept 0..3. A separate guarded XPAN
     * state owns the 65:24 window; the underlying image source is 3:2. */
    out->native_aspect = out->xpan_enabled ? GR4_ASPECT_3_2 : state->aspect_choice;
    out->crop_factor_bits = factors[out->native_crop_mode];
    return 1;
}

const char *gr4_xpan_crop_label(unsigned int choice) {
    static const char *const labels[] = {"OFF", "35mm", "50mm"};
    return choice <= GR4_CROP_50 ? labels[choice] : 0;
}

const char *gr4_xpan_aspect_label(unsigned int aspect) {
    static const char *const labels[] = {"3:2", "4:3", "16:9", "1:1", "XPAN"};
    return aspect <= GR4_ASPECT_XPAN ? labels[aspect] : 0;
}

static const unsigned int aspect_menu_order[] = {
    GR4_ASPECT_3_2, GR4_ASPECT_4_3, GR4_ASPECT_1_1,
    GR4_ASPECT_16_9, GR4_ASPECT_XPAN
};

unsigned int gr4_xpan_aspect_menu_count(void) { return 5; }

const char *gr4_xpan_aspect_menu_label(unsigned int index) {
    return index < gr4_xpan_aspect_menu_count() ?
        gr4_xpan_aspect_label(aspect_menu_order[index]) : 0;
}

int gr4_xpan_aspect_menu_selected(const struct gr4_xpan_state *state,
                                  unsigned int index) {
    return state && state->crop_choice <= GR4_CROP_50 &&
        state->last_regular_aspect <= GR4_ASPECT_1_1 &&
        state->aspect_choice <= GR4_ASPECT_XPAN &&
        index < gr4_xpan_aspect_menu_count() &&
        state->aspect_choice == aspect_menu_order[index];
}

int gr4_xpan_aspect_menu_select(struct gr4_xpan_state *state, unsigned int index) {
    return index < gr4_xpan_aspect_menu_count() &&
        gr4_xpan_select_aspect(state, aspect_menu_order[index]);
}

static int valid_alignment(unsigned int value) {
    return value && value <= 256 && !(value & (value - 1));
}

int gr4_xpan_full_width_rect(unsigned int width, unsigned int height,
                            unsigned int width_alignment, unsigned int height_alignment,
                            unsigned int origin_alignment, struct gr4_xpan_rect *out) {
    unsigned int candidate, best = 0, best_error = ~0u;
    if (!out || !width || !height || width > 65535 || height > 65535 ||
        !valid_alignment(width_alignment) || !valid_alignment(height_alignment) ||
        !valid_alignment(origin_alignment) || (width & (width_alignment - 1)) ||
        width * 24 > height * 65) return 0;
    for (candidate = height_alignment; candidate <= height; candidate += height_alignment) {
        unsigned int target, actual, error;
        if ((height - candidate) & (2 * origin_alignment - 1)) continue;
        target = width * 24;
        actual = candidate * 65;
        error = actual > target ? actual - target : target - actual;
        if (error <= best_error) { best = candidate; best_error = error; }
    }
    if (!best) return 0;
    out->left = 0;
    out->top = (height - best) / 2;
    out->width = width;
    out->height = best;
    return 1;
}

/* Avoid a dependency on an unbound ARM runtime division helper. */
static unsigned int divide(unsigned int numerator, unsigned int denominator) {
    unsigned int quotient = 0, remainder = 0;
    int bit;
    for (bit = 31; bit >= 0; --bit) {
        remainder = (remainder << 1) | ((numerator >> bit) & 1);
        if (remainder >= denominator) {
            remainder -= denominator;
            quotient |= 1u << bit;
        }
    }
    return quotient;
}

int gr4_xpan_preview_rect(unsigned int source_width, unsigned int source_height,
                         const struct gr4_xpan_rect *crop,
                         unsigned int preview_width, unsigned int preview_height,
                         struct gr4_xpan_rect *out) {
    unsigned int left, top, right, bottom;
    if (!crop || !out || !source_width || !source_height || !preview_width ||
        !preview_height || source_width > 65535 || source_height > 65535 ||
        preview_width > 65535 || preview_height > 65535 || !crop->width || !crop->height ||
        crop->left > source_width || crop->top > source_height ||
        crop->width > source_width-crop->left || crop->height > source_height-crop->top)
        return 0;
    /* Map both edges from the same photo rectangle, then derive the dimensions. */
    left = divide(crop->left * preview_width, source_width);
    top = divide(crop->top * preview_height, source_height);
    right = divide((crop->left + crop->width) * preview_width, source_width);
    bottom = divide((crop->top + crop->height) * preview_height, source_height);
    if (right == left || bottom == top) return 0;
    out->left = left;
    out->top = top;
    out->width = right - left;
    out->height = bottom - top;
    return 1;
}
