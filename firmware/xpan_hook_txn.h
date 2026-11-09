/* Reversible 32-bit hook transaction. Native quiesce/cache adapters pending.
 * Calls must be serialized by the owner. Never edit/reinitialize an active
 * journal or reuse its context while guard_held; recovery needs both intact. */
#ifndef GR4_XPAN_HOOK_TXN_H
#define GR4_XPAN_HOOK_TXN_H

#define GR4_XPAN_MAX_HOOKS 16u

struct gr4_xpan_hook_site {
    unsigned int address, original, replacement;
};

struct gr4_xpan_hook_io {
    /* enter must stop new calls and wait for existing calls to leave the sites. */
    int (*enter)(void *context);
    void (*leave)(void *context);
    int (*read_word)(void *context, unsigned int address, unsigned int *value);
    int (*write_word)(void *context, unsigned int address, unsigned int value);
    /* publish must perform the target's barriers/cache and cross-core protocol. */
    int (*publish)(void *context);
};

struct gr4_xpan_hook_txn {
    unsigned int state; /* 0 = original, 1 = installed, 2 = uncertain/quiesced */
    unsigned int count;
    struct gr4_xpan_hook_site sites[GR4_XPAN_MAX_HOOKS];
    /* Zero-initialize before first use. Keep txn/context alive throughout each
     * call and while held; state=0 alone is not proof the call has returned.
     * Save the callbacks by value: recovery must not depend on the lifetime of
     * the caller's io structure. A held guard must never be entered again. */
    unsigned int guard_held;
    struct gr4_xpan_hook_io guard_io;
    void *guard_context;
};

int gr4_xpan_hook_install(struct gr4_xpan_hook_txn *txn,
                          const struct gr4_xpan_hook_site *sites, unsigned int count,
                          const struct gr4_xpan_hook_io *io, void *context);
int gr4_xpan_hook_remove(struct gr4_xpan_hook_txn *txn,
                         const struct gr4_xpan_hook_io *io, void *context);
/* Retry restoration after state 2 without reacquiring the retained guard.
 * Requires the same callbacks/context; unknown values are never overwritten.
 * Release the guard only after every original word and publication are verified.
 * On failure, retain txn/context/code/allocations and use an independent recovery
 * caller. This API alone is not a native task/cache or USB recovery adapter. */
int gr4_xpan_hook_recover_original(struct gr4_xpan_hook_txn *txn,
                                  const struct gr4_xpan_hook_io *io, void *context);
#endif
