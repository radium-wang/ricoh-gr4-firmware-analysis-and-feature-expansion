#include "xpan_settings_routes.h"
_Static_assert(sizeof(void *) == 4, "GR IV 32-bit ABI required");
typedef unsigned int word;
typedef unsigned short half;
typedef void (*unary_fn)(void *);
typedef void (*binary_fn)(void *, word);
typedef void (*move_fn)(void *, int, word);
typedef void (*rect_fn)(void *, const void *);

static int heap(word pointer, word length) {
    return !(pointer & 3u) && pointer >= 0x59600008u &&
           length <= 0x10000u && pointer <= 0x5A5FFFF0u - length;
}
static int row(const struct gr4_xpan_settings_routes *routes) {
    const unsigned char *c;
    if (!routes || !routes->state || !heap((word)routes->controller, 0x1E4)) return 0;
    c = routes->controller;
    return *(const word *)c == 0x53DA2C70u &&
           *(const word *)(c + 0x124) == 0x0200008Au && c[0x1A4] == 34u;
}
static unsigned char *list(const struct gr4_xpan_settings_routes *routes) {
    unsigned char *l;
    word begin, end;
    if (!row(routes) || routes->capture_ready != GR4_XPAN_ALL_READY) return 0;
    l = *(unsigned char **)((unsigned char *)routes->controller + 0x198);
    if (!heap((word)l, 0x190) || *(word *)l != 0x53E98468u) return 0;
    begin = *(word *)(l + 0xF4);
    end = *(word *)(l + 0xF8);
    /* End denotes CONSTRUCTED records, not vector allocation capacity. */
    if (!heap(begin, 20) || end < begin + 20u || end > 0x5A5FFFF0u ||
        ((end - begin) & 3u)) return 0;
    for (word i = 0; i < 5; ++i) {
        word record = ((word *)begin)[i], item;
        if (!heap(record, 8)) return 0;
        item = *(word *)record;
        if (!heap(item, 0x108) || *(word *)item != 0x53E98F18u) return 0;
        if (i == 4) {
            word ascii = *(word *)(item + 0x100);
            if (!heap(ascii, 0x100) || *(word *)ascii != 0x53E97FD8u) return 0;
        }
    }
    return l;
}
int gr4_xpan_settings_present(struct gr4_xpan_settings_routes *routes) {
    unsigned char *l = list(routes), *c = routes->controller;
    word begin, selected = 5, rect[4];
    if (!l) return 0;
    /* Validate state before any GUI writes. */
    for (word i = 0; i < 5; ++i)
        if (gr4_xpan_settings_selected(routes->state, i)) selected = i;
    if (selected == 5) return 0;
    begin = *(word *)(l + 0xF4);
    if (!gr4_xpan_settings_label(c, *(void **)((word *)begin)[4], 4)) return 0;
    ((binary_fn)0x535711E4u)(l, 5);
    for (word i = 0; i < 5; ++i)
        ((binary_fn)0x5357AD40u)(*(void **)((word *)begin)[i], i == selected);
    c[0x1A6] = selected;
    /* Original refresh fits only four rows. Grow its own rectangle to five
     * 60-pixel rows, using the same native geometry methods and virtual ABI. */
    ((rect_fn)0x535893CCu)(rect, l);
    ((binary_fn)0x538E9B6Cu)(rect, 60);
    ((binary_fn)0x538E9C2Cu)(rect, 300);
    ((rect_fn)(*(word *)(*(word *)l + 0x18)))(l, rect);
    ((binary_fn)0x53571788u)(l, selected);
    return 1;
}
int gr4_xpan_settings_refresh(struct gr4_xpan_settings_routes *routes) {
    if (!row(routes)) return 0;
    /* No fifth item is enabled until all capture adapters are ready. */
    ((unary_fn)0x531DA9D4u)(routes->controller);
    return gr4_xpan_settings_present(routes);
}
int gr4_xpan_settings_activate(struct gr4_xpan_settings_routes *routes) {
    if (!row(routes)) return 0;
    ((unary_fn)0x531DAD8Cu)(routes->controller);
    return gr4_xpan_settings_present(routes);
}
int gr4_xpan_settings_list_confirm(struct gr4_xpan_settings_routes *routes, word index) {
    if (!list(routes) || index >= 5) return 0;
    if (!gr4_xpan_settings_select(routes->controller, routes->state, index, 1)) return 0;
    return gr4_xpan_settings_present(routes);
}
int gr4_xpan_settings_button_confirm(struct gr4_xpan_settings_routes *routes) {
    unsigned char *l = list(routes);
    word index;
    if (!l) return 0;
    index = *(half *)(l + 0x110);
    if (index >= 5 || !gr4_xpan_settings_select(routes->controller, routes->state, index, 0)) return 0;
    /* Preserve the original button's close/return operation. */
    ((unary_fn)0x53182E9Cu)(routes->controller);
    return 1;
}
int gr4_xpan_settings_event(struct gr4_xpan_settings_routes *routes, const void *event) {
    unsigned char *l = list(routes);
    word code, index;
    int direction;
    if (!l || !event) return 0;
    code = *(const half *)event;
    index = *(half *)(l + 0x110);
    if (l[0x108] != 5 || index >= 5) return 0;
    if (code == 0xE0)
        return gr4_xpan_settings_select(routes->controller, routes->state, index, 0);
    if (code == 0xD6 || code == 0xDA) direction = -1;
    else if (code == 0xD7 || code == 0xDB) direction = 1;
    else return 0; /* The ABI adapter delegates unrelated events. */
    /* Native row 34 permits edge wrap only for the initial key event.
     * Repeat events DA/DB stop at the boundary, matching original behavior. */
    if ((code == 0xDA && !index) || (code == 0xDB && index == 4)) return 1;
    ((move_fn)0x535715B8u)(l, direction, 1);
    return 1;
}
