/* One-call checks of the actual XPAN core in owned RAM. No native hooks/I/O.
 * Stack-local state and buffers only. A zero return means all cases passed;
 * bits identify the failed group. Illustrative geometry alignment values
 * remain unverified for the camera's live preview and image pipelines. */
#include "xpan_core.c"
#include "xpan_capture.c"
#include "xpan_undo.c"

/* Compiler-generated copies of stack-local structures have no RTOS binding. */
__attribute__((visibility("hidden")))
void __aeabi_memcpy(void *destination, const void *source, unsigned int length) {
    unsigned char *out = destination;
    const unsigned char *in = source;
    while (length--) *out++ = *in++;
}

__attribute__((visibility("hidden")))
unsigned int gr4_xpan_ram_check(unsigned int magic, unsigned int ratio_w,
                                 unsigned int ratio_h) {
    struct gr4_xpan_state state;
    struct gr4_xpan_effective effective;
    struct gr4_xpan_rect photo, preview;
    struct gr4_xpan_capture_plan plan;
    struct gr4_xpan_buffer_undo undo;
    unsigned char buffer[64];
    unsigned int failures = 0, crop, aspect, index;
    undo.kind = 0;
    if (magic != 0x5850414e || ratio_w != 65 || ratio_h != 24) return 0x80000000u;
    for (crop = 0; crop < 3; ++crop) {
        for (aspect = 0; aspect < 4; ++aspect) {
            state = (struct gr4_xpan_state){crop, aspect, aspect};
            if (!gr4_xpan_aspect_menu_select(&state, 4) ||
                !gr4_xpan_effective_settings(&state, &effective) ||
                effective.native_crop_mode != crop || effective.native_aspect != 0 ||
                !effective.xpan_enabled ||
                !gr4_xpan_aspect_menu_selected(&state, 4) ||
                !gr4_xpan_deactivate(&state) || state.aspect_choice != aspect)
                failures |= 1u;
        }
    }
    for (index = 0; index < 5; ++index) {
        const unsigned int native = index == 2 ? 3 : index == 3 ? 2 : index;
        state = (struct gr4_xpan_state){0, 0, 0};
        if (!gr4_xpan_aspect_menu_select(&state,index) || state.aspect_choice != native)
            failures |= 2u;
    }
    if (gr4_xpan_aspect_menu_count() != 5 || gr4_xpan_aspect_menu_select(&state,5))
        failures |= 2u;
    if (!gr4_xpan_full_width_rect(6192,4128,16,8,2,&photo) ||
        photo.left != 0 || photo.top != 920 || photo.width != 6192 || photo.height != 2288)
        failures |= 4u;
    if (!gr4_xpan_preview_rect(6192,4128,&photo,720,480,&preview) ||
        preview.left != 0 || preview.top != 106 || preview.width != 720 || preview.height != 267)
        failures |= 8u;
    state = (struct gr4_xpan_state){0,4,2};
    if (!gr4_xpan_capture_begin(&state,6192,4128,6320,4224,54,58,16,8,2,&plan))
        failures |= 16u;
    else {
        for (index = 0; index < 64; ++index) buffer[index] = 0xa5;
        if (!gr4_xpan_dng_apply_reversible(&plan,buffer,64,&undo) ||
            buffer[24] != 0x30 || buffer[25] != 0x18 ||
            buffer[26] != 0xf0 || buffer[27] != 8 ||
            buffer[28] != 54 || buffer[29] != 0 ||
            buffer[30] != 0xd2 || buffer[31] != 3 ||
            !gr4_xpan_buffer_restore(&undo,buffer,64)) failures |= 32u;
        for (index = 0; index < 64; ++index)
            if (buffer[index] != 0xa5) failures |= 64u;
    }
    return failures;
}
