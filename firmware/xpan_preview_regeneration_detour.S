/* Offline candidate at 0x536438A0, replacing exactly BL + LDR (8 bytes).
 * The original singleton query is retained. Recipe arrives in live r4,
 * NOT as a C argument. The owner must already be paused/drained; no lock or
 * executable-memory publication protocol is provided here.
 * Incoming LR is not a function return address for this mid-function entry.
 * Resume reproduces original BL's LR and original following LDR.
 */
.syntax unified
.arm
.text
.balign 4
.global gr4_xpan_preview_regeneration_detour
.type gr4_xpan_preview_regeneration_detour,%function
gr4_xpan_preview_regeneration_detour:
    push {r4, lr}
    ldr ip, =0x53886558
    blx ip
    push {r0, r1, r2, r3, ip, lr}
    mrs r0, APSR
    push {r0, r1}
    mov r0, r4
    bl gr4_xpan_preview_recipe_regenerated_native
    pop {r0, r1}
    msr APSR_nzcvq, r0
    pop {r0, r1, r2, r3, ip, lr}
    pop {r4, lr}
    ldr r3, [r0, #8]
    ldr lr, =0x536438A4
    ldr pc, =0x536438A8
.ltorg
.size gr4_xpan_preview_regeneration_detour, .-gr4_xpan_preview_regeneration_detour
