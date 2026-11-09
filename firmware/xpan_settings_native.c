#include "xpan_settings_native.h"

/* These addresses are pinned by audit_gr4_ui_native_routes.py and
 * audit_gr4_menu_widgets.py. No installer or USB caller uses this backend. */
typedef void (*label_fn)(void *, void *, unsigned int);
typedef void (*ascii_fn)(void *, const char *);
typedef void (*select_fn)(void *, unsigned int);
static const struct gr4_xpan_selection_binding *selection_binding;
void gr4_xpan_settings_bind_selection(const struct gr4_xpan_selection_binding *next) {
    selection_binding = next;
}

static int settings_row(void *controller) {
    const unsigned char *bytes = controller;
    if (!controller || ((unsigned long)controller & 3u)) return 0;
    /* Caller establishes ownership before this bounded class/row check. */
    return *(const unsigned int *)controller == 0x53DA2C70u &&
           *(const unsigned int *)(bytes + 0x124) == 0x0200008Au &&
           bytes[0x1A4] == 34u;
}

int gr4_xpan_settings_label(void *controller, void *item, unsigned int index) {
    if (!settings_row(controller) || !item || ((unsigned long)item & 3u) ||
        *(const unsigned int *)item != 0x53E98F18u || index >= 5u) return 0;
    if (index < 4u)
        ((label_fn)0x531D0CCCu)(controller, item, index);
    else
        /* Caption IDs cannot represent new text. AsciiView owns its converted
         * UTF-16 allocation; its lifetime/undo belongs to the UI installer. */
        ((ascii_fn)0x5357AE1Cu)(item, "XPAN");
    return 1;
}

int gr4_xpan_settings_selected(const struct gr4_xpan_state *state,
                                unsigned int index) {
    return gr4_xpan_aspect_menu_selected(state, index);
}

int gr4_xpan_settings_select(void *controller, struct gr4_xpan_state *state,
                              unsigned int index, unsigned int confirm) {
    struct gr4_xpan_state next;
    struct gr4_xpan_selection selection;
    const struct gr4_xpan_selection_binding *binding = selection_binding;
    if (!settings_row(controller) || !state || confirm > 1u || index >= 5u)
        return 0;
    if (binding) {
        if (binding->state != state ||
            !gr4_xpan_selection_prepare(state,index,binding->geometry,&selection) ||
            !gr4_xpan_selection_commit(binding,&selection)) return 0;
    } else {
        next = *state;
        if (!gr4_xpan_aspect_menu_select(&next, index)) return 0;
        *state = next;
    }
    /* Native property observers may execute during the setter. Under the
     * caller's state lock they must see XPAN before source aspect 3:2. */
    ((select_fn)(confirm ? 0x531D8FFCu : 0x531D2F70u))(
        controller, index == 4u ? 0u : index);
    return 1;
}
int gr4_xpan_settings_deactivate(void *controller, struct gr4_xpan_state *state,
    unsigned int confirm) {
    static const unsigned int inverse_menu[4]={0u,1u,3u,2u};
    struct gr4_xpan_effective effective;
    unsigned int aspect;
    if (!gr4_xpan_effective_settings(state,&effective)) return 0;
    aspect = effective.xpan_enabled ? state->last_regular_aspect : state->aspect_choice;
    return gr4_xpan_settings_select(controller,state,inverse_menu[aspect],confirm);
}
