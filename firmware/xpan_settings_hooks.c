#include "xpan_settings_hooks.h"
typedef unsigned int word;
extern void gr4_xpan_settings_refresh_original(void *);
extern void gr4_xpan_settings_activate_original(void *);
extern word gr4_xpan_settings_event_original(void *, const void *);
extern void gr4_xpan_settings_list_confirm_original(void *, word);
extern void gr4_xpan_settings_button_original(void *);
static struct gr4_xpan_settings_routes *binding;
static int heap(word pointer, word bytes) {
    return !(pointer & 3u) && pointer >= 0x59600008u &&
        bytes <= 0x10000u && pointer <= 0x5A5FFFF0u - bytes;
}
static int owned(void *controller) {
    const unsigned char *c = controller;
    return binding && binding->state && binding->controller == controller &&
        heap((word)c,0x1E4u) && *(const word *)c == 0x53DA2C70u &&
        *(const word *)(c+0x124) == 0x0200008Au;
}
static int aspect(void *controller) {
    return owned(controller) && ((unsigned char *)controller)[0x1A4] == 34u;
}
int gr4_xpan_settings_hooks_bind(struct gr4_xpan_settings_routes *next) {
    if (next && binding && next != binding) return 0;
    /* The owner, not this local function, supplies quiescence/lifetime proof. */
    binding = next;
    return 1;
}
void gr4_xpan_settings_refresh_hook(void *controller) {
    gr4_xpan_settings_refresh_original(controller);
    if (aspect(controller)) gr4_xpan_settings_present(binding);
}
void gr4_xpan_settings_activate_hook(void *controller) {
    gr4_xpan_settings_activate_original(controller);
    if (aspect(controller)) gr4_xpan_settings_present(binding);
}
word gr4_xpan_settings_event_hook(void *controller, const void *event) {
    word code;
    if (!aspect(controller) || !event)
        return gr4_xpan_settings_event_original(controller,event);
    code = *(const unsigned short *)event;
    if (code != 0xD6u && code != 0xD7u && code != 0xDAu &&
        code != 0xDBu && code != 0xE0u)
        return gr4_xpan_settings_event_original(controller,event);
    /* Never forward a failed/unfinished XPAN route to four-entry ROM tables.
     * The original event ABI returns zero even for a consumed operation. */
    gr4_xpan_settings_event(binding,event);
    return 0;
}
void gr4_xpan_settings_list_confirm_hook(void *controller, word index) {
    if (!aspect(controller)) {
        gr4_xpan_settings_list_confirm_original(controller,index);
        return;
    }
    gr4_xpan_settings_list_confirm(binding,index);
}
void gr4_xpan_settings_button_hook(void *storage) {
    word holder, controller;
    /* A real native invocation already requires readable std::function
     * storage. Only follow the owner record after checking its heap bounds. */
    holder = storage ? *(const word *)storage : 0;
    controller = heap(holder,4) ? *(const word *)holder : 0;
    if (!aspect((void *)controller)) {
        gr4_xpan_settings_button_original(storage);
        return;
    }
    /* The helper includes the one native close. Do not execute the original
     * invoker afterwards: it would confirm and close a second time. */
    gr4_xpan_settings_button_confirm(binding);
}
int gr4_xpan_settings_hooks_withdraw(void) {
    unsigned char *c, *l;
    if (!binding || binding->capture_ready || !owned(binding->controller)) return 0;
    c = binding->controller;
    if (!gr4_xpan_settings_deactivate(c,binding->state,0)) return 0;
    gr4_xpan_settings_refresh_original(c);
    l = *(unsigned char **)(c+0x198);
    return heap((word)l,0x190u) && *(word *)l == 0x53E98468u &&
        l[0x108] == 4u && *(const unsigned short *)(l+0x110) < 4u &&
        binding->state->aspect_choice < 4u;
}
