#include "xpan_hook_txn.h"

static int io_ready(const struct gr4_xpan_hook_io *io) {
    return io && io->enter && io->leave && io->read_word &&
           io->write_word && io->publish;
}

static int same_io(const struct gr4_xpan_hook_io *a,
                   const struct gr4_xpan_hook_io *b) {
    return a->enter == b->enter && a->leave == b->leave &&
           a->read_word == b->read_word && a->write_word == b->write_word &&
           a->publish == b->publish;
}

static void release_guard(struct gr4_xpan_hook_txn *txn) {
    txn->guard_io.leave(txn->guard_context);
    txn->guard_held = 0;
    txn->guard_context = 0;
    txn->guard_io = (struct gr4_xpan_hook_io){0};
}

static int valid_sites(const struct gr4_xpan_hook_site *sites, unsigned int count) {
    unsigned int i, j;
    if (!sites || !count || count > GR4_XPAN_MAX_HOOKS) return 0;
    for (i = 0; i < count; ++i) {
        if ((sites[i].address & 3u) || !sites[i].address ||
            sites[i].original == sites[i].replacement) return 0;
        for (j = 0; j < i; ++j)
            if (sites[i].address == sites[j].address) return 0;
    }
    return 1;
}

static int all_words(const struct gr4_xpan_hook_txn *txn,
                     const struct gr4_xpan_hook_io *io, void *context,
                     int installed) {
    unsigned int i, value;
    for (i = 0; i < txn->count; ++i) {
        if (!io->read_word(context, txn->sites[i].address, &value) ||
            value != (installed ? txn->sites[i].replacement : txn->sites[i].original))
            return 0;
    }
    return 1;
}

/* With callers quiesced, roll back only a word still equal to one of our two
 * known values. A third-party value or read failure leaves state uncertain. */
static int restore(const struct gr4_xpan_hook_txn *txn,
                   const struct gr4_xpan_hook_io *io, void *context,
                   int installed) {
    unsigned int i, value, target;
    int good = 1;
    for (i = txn->count; i > 0; --i) {
        const struct gr4_xpan_hook_site *site = &txn->sites[i-1];
        target = installed ? site->replacement : site->original;
        if (!io->read_word(context, site->address, &value) ||
            (value != site->original && value != site->replacement)) {
            good = 0;
            continue;
        }
        if (value != target && !io->write_word(context, site->address, target))
            good = 0;
        if (!io->read_word(context, site->address, &value) || value != target)
            good = 0;
    }
    if (!io->publish(context) || !all_words(txn, io, context, installed))
        good = 0;
    return good;
}

static int transition(struct gr4_xpan_hook_txn *txn,
                      const struct gr4_xpan_hook_io *io, void *context,
                      int to_installed) {
    unsigned int i, target, value;
    int good = 1;
    if (!io->enter(context)) return 0;
    txn->guard_held = 1;
    txn->guard_io = *io;
    txn->guard_context = context;
    if (!all_words(txn, io, context, !to_installed)) {
        /* Removal starts with live hooks. An unexpected word may leave a
         * mixed set, so keep callers stopped even before the first write. */
        if (!to_installed) txn->state = 2;
        else release_guard(txn);
        return 0;
    }
    txn->state = 2;
    for (i = 0; i < txn->count; ++i) {
        target = to_installed ? txn->sites[i].replacement : txn->sites[i].original;
        if (!io->write_word(context, txn->sites[i].address, target) ||
            !io->read_word(context, txn->sites[i].address, &value) ||
            value != target) {
            good = 0;
            break;
        }
    }
    if (good && (!io->publish(context) ||
                 !all_words(txn, io, context, to_installed))) good = 0;
    if (good) txn->state = to_installed ? 1u : 0u;
    else if (restore(txn, io, context, !to_installed))
        txn->state = to_installed ? 0u : 1u;
    /* A mixed or unverified hook set must not resume normal callers. The
     * independent recovery path must resolve state 2 while still quiesced. */
    if (txn->state != 2) release_guard(txn);
    return good;
}

int gr4_xpan_hook_install(struct gr4_xpan_hook_txn *txn,
                          const struct gr4_xpan_hook_site *sites, unsigned int count,
                          const struct gr4_xpan_hook_io *io, void *context) {
    unsigned int i;
    if (!txn || txn->state || txn->guard_held || !io_ready(io) ||
        !valid_sites(sites, count)) return 0;
    txn->count = count;
    for (i = 0; i < count; ++i) txn->sites[i] = sites[i];
    return transition(txn, io, context, 1);
}

int gr4_xpan_hook_remove(struct gr4_xpan_hook_txn *txn,
                         const struct gr4_xpan_hook_io *io, void *context) {
    if (!txn || txn->state != 1 || txn->guard_held ||
        !valid_sites(txn->sites, txn->count) || !io_ready(io)) return 0;
    return transition(txn, io, context, 0);
}

int gr4_xpan_hook_recover_original(struct gr4_xpan_hook_txn *txn,
                                  const struct gr4_xpan_hook_io *io, void *context) {
    if (!txn || txn->state != 2 || txn->guard_held != 1 || !io_ready(io) ||
        !io_ready(&txn->guard_io) || context != txn->guard_context ||
        !same_io(io, &txn->guard_io) || !valid_sites(txn->sites, txn->count))
        return 0;
    if (!restore(txn, &txn->guard_io, txn->guard_context, 0)) return 0;
    txn->state = 0;
    release_guard(txn);
    return 1;
}
