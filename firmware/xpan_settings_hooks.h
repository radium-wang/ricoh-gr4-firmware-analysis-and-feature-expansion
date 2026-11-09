/* Offline candidate for the pinned 01.11.10.07 native UI ABI. No installer.
 * Bind/unbind and all callbacks require stable object ownership on AppMain,
 * with UI/image readers paused/drained during state/plan publication. This
 * module supplies neither that native synchronization nor cache publication.
 */
#ifndef GR4_XPAN_SETTINGS_HOOKS_H
#define GR4_XPAN_SETTINGS_HOOKS_H
#include "xpan_settings_routes.h"
/* Bind while quiesced, before publishing entry patches. All pointers must
 * outlive every hook. Unbind only AFTER original entry words are restored,
 * caches published and in-flight callbacks drained. */
int gr4_xpan_settings_hooks_bind(struct gr4_xpan_settings_routes *);
/* Set readiness to zero, undo preview/image changes, then call while drained.
 * Restores regular selection/shared plan and original four-item presentation.
 * Failure requires retaining bindings, code and the recovery journal. */
int gr4_xpan_settings_hooks_withdraw(void);
void gr4_xpan_settings_refresh_hook(void *);
void gr4_xpan_settings_activate_hook(void *);
unsigned int gr4_xpan_settings_event_hook(void *, const void *);
void gr4_xpan_settings_list_confirm_hook(void *, unsigned int);
/* Native std::function ABI: r0 -> owner-record pointer -> controller. */
void gr4_xpan_settings_button_hook(void *);
#endif
