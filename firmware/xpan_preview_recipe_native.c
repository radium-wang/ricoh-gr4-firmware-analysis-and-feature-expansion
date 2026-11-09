#include "xpan_preview_recipe_native.h"
_Static_assert(sizeof(void *) == 4, "GR IV 32-bit ABI required");
typedef void (*recipe_native_fn)(void *, unsigned int, unsigned int,
                                unsigned int, unsigned int);
static const struct gr4_xpan_preview_recipe_binding *recipe_binding;
void gr4_xpan_preview_recipe_bind(const struct gr4_xpan_preview_recipe_binding *next) {
    recipe_binding = next;
}
static const struct gr4_xpan_preview_recipe_binding *checked_binding(void *self,
    unsigned int aspect, unsigned int extra, unsigned int mode, unsigned int factor) {
    const struct gr4_xpan_preview_recipe_binding *binding = recipe_binding;
    const unsigned char *owner;
    unsigned int index, member=0u;
    if (!binding || binding->ready != 1u || !self || self != binding->recipe ||
        !binding->manager || !binding->process || !binding->plan || !binding->undo ||
        !binding->collection || *(const unsigned int *)self != 0x53EB16E8u ||
        aspect || extra || mode ||
        *(const unsigned int *)binding->manager != 0x53FD19F8u ||
        ((const unsigned char *)binding->manager)[9] ||
        ((const unsigned char *)binding->manager)[11] ||
        (((const unsigned char *)binding->manager)[10] != 7u &&
         ((const unsigned char *)binding->manager)[10] != 29u &&
         ((const unsigned char *)binding->manager)[10] != 30u) ||
        *(void *const *)((const unsigned char *)self+0x334) != binding->manager)
        return 0;
    owner = (const unsigned char *)binding->process;
    if (*(const unsigned int *)owner != 0x53EB11F0u ||
        *(void *const *)(owner+0x3B0) != binding->collection ||
        *(void *const *)(owner+0x398) != binding->manager ||
        owner[0x8D] || owner[0x91] || owner[0x97A4] ||
        (*(const unsigned int *)(owner+0x6C) & 1u) ||
        *(const unsigned int *)(owner+0x94) != factor) return 0;
    for (index=0; index<8u; ++index)
        if (*(void *const *)((const unsigned char *)binding->collection+8u+index*4u)==self)
            member=1u;
    if (!member) return 0;
    return binding;
}
void gr4_xpan_preview_recipe_native(void *self, unsigned int aspect,
    unsigned int extra, unsigned int mode, unsigned int factor) {
    const struct gr4_xpan_preview_recipe_binding *binding;
    ((recipe_native_fn)0x53647498u)(self,aspect,extra,mode,factor);
    binding = checked_binding(self,aspect,extra,mode,factor);
    if (!binding) return;
    (void)gr4_xpan_preview_recipe_apply((unsigned char *)self,0xBF4u,binding->plan,
                                       factor,binding->height_alignment,binding->undo);
}
void gr4_xpan_preview_recipe_regenerated_native(void *self) {
    const struct gr4_xpan_preview_recipe_binding *binding = recipe_binding;
    unsigned int factor;
    if (!binding || binding->ready != 1u || !self || self != binding->recipe ||
        !binding->process || !binding->manager || !binding->plan ||
        !binding->undo || !binding->collection) return;
    factor = *(const unsigned int *)((const unsigned char *)binding->process+0x94);
    binding = checked_binding(self,0u,0u,0u,factor);
    if (!binding) return;
    (void)gr4_xpan_preview_recipe_reapply_after_regeneration(
        (unsigned char *)self,0xBF4u,binding->plan,factor,
        binding->height_alignment,binding->undo);
}
