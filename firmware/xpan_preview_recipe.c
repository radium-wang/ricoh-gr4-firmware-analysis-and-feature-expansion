#include "xpan_preview_recipe.h"
static unsigned int recipe_u16(const unsigned char *p, unsigned int offset) {
    return (unsigned int)p[offset] | ((unsigned int)p[offset+1] << 8);
}
static void recipe_put16(unsigned char *p, unsigned int offset, unsigned int value) {
    p[offset] = (unsigned char)value;
    p[offset+1] = (unsigned char)(value >> 8);
}
static unsigned int recipe_u32(const unsigned char *p, unsigned int offset) {
    return recipe_u16(p,offset) | (recipe_u16(p,offset+2u) << 16);
}
int gr4_xpan_preview_recipe_apply(unsigned char *p, unsigned int bytes,
    const struct gr4_xpan_capture_plan *plan, unsigned int factor,
    unsigned int alignment, struct gr4_xpan_preview_recipe_undo *undo) {
    struct gr4_xpan_rect rect;
    unsigned int width, height, next_height, top, expected;
    if (!p || bytes < 0xBF4u || !plan || !undo || undo->active > 1u ||
        !alignment || alignment > 16u || (alignment & (alignment-1u)) ||
        p[0xBBE] || p[0xBC4]) return 0;
    width = recipe_u16(p, 0xBD6); height = recipe_u16(p, 0xBD8);
    if (!width || !height || recipe_u16(p, 0xBE4) != width ||
        recipe_u16(p, 0xBE6) != height || recipe_u16(p, 0xBEA) != width ||
        recipe_u16(p, 0xBEC) != height || recipe_u16(p, 0xBE0) ||
        recipe_u16(p, 0xBE2) ||
        !gr4_xpan_capture_preview(plan,width,height,&rect)) return 0;
    expected = plan->native_crop_factor_bits == 0x3F800000u ? 8192u :
               plan->native_crop_factor_bits == 0x3FA04F89u ? 10260u : 14476u;
    if (factor != expected || recipe_u32(p,0xBF0) != factor || rect.left ||
        rect.width != width) return 0;
    next_height = rect.height & ~(alignment-1u);
    if (!next_height || next_height >= height) return 0;
    top = (height-next_height)/2u;
    if (undo->active && (undo->target != p || undo->original_height != height ||
                         undo->original_top != 0u || undo->original_width != width ||
                         undo->crop_q13 != factor || undo->reserved)) return 0;
    undo->target = p;
    undo->original_height = (unsigned short)height;
    undo->original_top = 0u;
    undo->applied_height = (unsigned short)next_height;
    undo->applied_top = (unsigned short)top;
    undo->original_width = (unsigned short)width;
    undo->reserved = 0u;
    undo->crop_q13 = factor;
    undo->active = 1u;
    recipe_put16(p,0xBD8,next_height); recipe_put16(p,0xBE2,top);
    return 1;
}
int gr4_xpan_preview_recipe_restore(unsigned char *p, unsigned int bytes,
    struct gr4_xpan_preview_recipe_undo *undo) {
    unsigned int h,y;
    if (!p || bytes < 0xBF4u || !undo || undo->active > 1u) return 0;
    if (!undo->active) return 1;
    if (undo->target != p || !undo->original_height || !undo->applied_height ||
        !undo->original_width || undo->reserved || p[0xBBE] || p[0xBC4] ||
        recipe_u16(p,0xBD6) != undo->original_width || recipe_u16(p,0xBE0) ||
        recipe_u16(p,0xBE4) != undo->original_width ||
        recipe_u16(p,0xBE6) != undo->original_height ||
        recipe_u16(p,0xBEA) != undo->original_width ||
        recipe_u16(p,0xBEC) != undo->original_height ||
        recipe_u32(p,0xBF0) != undo->crop_q13 ||
        undo->applied_height >= undo->original_height || undo->original_top ||
        undo->applied_top != (undo->original_height-undo->applied_height)/2u) return 0;
    h=recipe_u16(p,0xBD8); y=recipe_u16(p,0xBE2);
    if (!((h==undo->applied_height && y==undo->applied_top) ||
           (h==undo->original_height && y==undo->original_top))) return 0;
    recipe_put16(p,0xBD8,undo->original_height);
    recipe_put16(p,0xBE2,undo->original_top);
    undo->active=0u;
    return 1;
}
int gr4_xpan_preview_recipe_reapply_after_regeneration(unsigned char *p,
    unsigned int bytes, const struct gr4_xpan_capture_plan *plan,
    unsigned int factor, unsigned int alignment,
    struct gr4_xpan_preview_recipe_undo *undo) {
    unsigned int saved_top;
    if (!p || bytes < 0xBF4u || !undo || undo->active != 1u ||
        undo->target != p || undo->reserved || undo->original_top ||
        !undo->original_width || !undo->applied_height ||
        undo->applied_height >= undo->original_height ||
        undo->applied_top != (undo->original_height-undo->applied_height)/2u ||
        undo->crop_q13 != factor ||
        recipe_u16(p,0xBD6) != undo->original_width ||
        recipe_u16(p,0xBD8) != undo->original_height ||
        recipe_u16(p,0xBE2) != undo->applied_top) return 0;
    saved_top = undo->applied_top;
    /* The caller owns a paused recipe; other consumers cannot see the
     * temporary original center. apply() performs all remaining validation
     * and leaves the undo unchanged on failure. */
    recipe_put16(p,0xBE2,0u);
    if (gr4_xpan_preview_recipe_apply(p,bytes,plan,factor,alignment,undo))
        return 1;
    recipe_put16(p,0xBE2,saved_top);
    return 0;
}
