/* Pinned first two A32 instructions, then resume the immutable original body.
 * No PC-relative loads/branches are relocated. LDR PC consumes no scratch
 * register. Original prologues containing PUSH PC retain its original saved
 * instruction address; executing PUSH PC in the module would change it.
 */
.syntax unified
.arm
.text
.macro ENTRY name
.balign 4
.global \name
.type \name,%function
\name:
.endm
.macro RESUME address
    ldr pc, [pc, #-4]
    .word \address
.endm
.macro SAVED_PROLOGUE savedpc
    mov ip, sp
    sub sp, sp, #24
    stmia sp, {r3,r4,fp,ip,lr}
    ldr r3, 1f
    str r3, [sp, #20]
    ldr r3, [sp]
    b 2f
1:  .word \savedpc
2:
.endm
ENTRY gr4_xpan_settings_refresh_original
    mov ip, sp
    movw r3, #0x49bc
    RESUME 0x531DA9DC
ENTRY gr4_xpan_settings_activate_original
    SAVED_PROLOGUE 0x531DAD98
    RESUME 0x531DAD94
ENTRY gr4_xpan_settings_event_original
    ldrh r3, [r1]
    mov ip, sp
    RESUME 0x531DACB4
ENTRY gr4_xpan_settings_list_confirm_original
    ldrb r2, [r0, #0x1a4]
    mov ip, sp
    RESUME 0x531D7128
ENTRY gr4_xpan_settings_button_original
    SAVED_PROLOGUE 0x531D6B5C
    RESUME 0x531D6B58
