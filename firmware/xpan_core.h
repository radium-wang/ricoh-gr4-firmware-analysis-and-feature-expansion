/* Project XPAN logic; native RTOS adapters and camera installation are pending. */
#ifndef GR4_XPAN_CORE_H
#define GR4_XPAN_CORE_H

enum gr4_crop_choice { GR4_CROP_OFF, GR4_CROP_35, GR4_CROP_50 };
enum gr4_aspect { GR4_ASPECT_3_2, GR4_ASPECT_4_3, GR4_ASPECT_16_9,
                  GR4_ASPECT_1_1, GR4_ASPECT_XPAN };
/* Zero-initialize. last_regular_aspect is kept for safe XPAN deactivation. */
struct gr4_xpan_state {
    unsigned int crop_choice, aspect_choice, last_regular_aspect;
};
struct gr4_xpan_effective {
    unsigned int native_crop_mode, native_aspect, crop_factor_bits, xpan_enabled;
};
struct gr4_xpan_rect { unsigned int left, top, width, height; };

int gr4_xpan_select_crop(struct gr4_xpan_state *, unsigned int);
int gr4_xpan_select_aspect(struct gr4_xpan_state *, unsigned int);
int gr4_xpan_deactivate(struct gr4_xpan_state *);
int gr4_xpan_effective_settings(const struct gr4_xpan_state *, struct gr4_xpan_effective *);
const char *gr4_xpan_crop_label(unsigned int);
const char *gr4_xpan_aspect_label(unsigned int);
/* Native menu order is 3:2, 4:3, 1:1, 16:9; XPAN is appended. These
 * functions keep menu indices separate from native aspect IDs. */
unsigned int gr4_xpan_aspect_menu_count(void);
const char *gr4_xpan_aspect_menu_label(unsigned int);
int gr4_xpan_aspect_menu_selected(const struct gr4_xpan_state *, unsigned int);
int gr4_xpan_aspect_menu_select(struct gr4_xpan_state *, unsigned int);
/* Alignment values must come from the validated native adapter, not a guess. */
int gr4_xpan_full_width_rect(unsigned int, unsigned int, unsigned int,
                            unsigned int, unsigned int, struct gr4_xpan_rect *);
int gr4_xpan_preview_rect(unsigned int, unsigned int, const struct gr4_xpan_rect *,
                         unsigned int, unsigned int, struct gr4_xpan_rect *);
#endif
