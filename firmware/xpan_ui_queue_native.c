/* Native AppMain handoff for GR IV 01.11.10.07. No loader or hooks.
 * Caller pins live firmware/queue identity, owns and publishes the complete
 * message/handler/code, and retains them until consumption and return/drain.
 * This function never allocates or frees them. */
_Static_assert(sizeof(void *) == 4, "GR IV 32-bit ABI required");
typedef unsigned int word;
typedef unsigned short half;
typedef int (*mutex_lock_fn)(void *, int);
typedef int (*mutex_unlock_fn)(void *);
typedef int (*notify_fn)(void *, word);

/* Results: 0 invalid, 1 queued/notified, 2 lock busy, 3 full,
 * 4 queued/notification failed, 5 queued/unlock failed.
 * Results 1,4,5 must NEVER be replayed or treated as no live handler. */
word gr4_xpan_ui_enqueue(void *owner, const word *message, word magic) {
    unsigned char *bytes = owner;
    word *ring;
    half count, capacity, head, tail, mask;
    word result;
    if ((word)owner != 0x55087470u || !message || ((word)message & 3u) ||
        magic != 0x58505549u || message[0] != 0x17Du || !message[2]) return 0;
    /* Poll the same mutex used by all original producers and the consumer;
     * checking queue fullness before locking would race with another producer. */
    if (!((mutex_lock_fn)0x538DFE24u)(bytes + 0x24, 0)) return 2;
    ring = *(word **)(bytes + 0x14);
    count = *(half *)(bytes + 0x18);
    capacity = *(half *)(bytes + 0x1A);
    head = *(half *)(bytes + 0x1C);
    tail = *(half *)(bytes + 0x1E);
    mask = *(half *)(bytes + 0x20);
    if (capacity != 64u || mask != 63u || head >= 64u || tail >= 64u ||
        count >= 64u || ((tail - head) & 63u) != count ||
        ((word)ring & 3u) || (word)ring < 0x59600008u ||
        (word)ring > 0x5A5FFFF0u - 64u * 12u) result = 0;
    else if (count == 63u) result = 3;
    else {
        word *slot = ring + tail * 3u;
        slot[0] = message[0];
        slot[1] = message[1];
        slot[2] = message[2];
        *(half *)(bytes + 0x18) = count + 1u;
        *(half *)(bytes + 0x1E) = (tail + 1u) & mask;
        result = 1;
    }
    if (!((mutex_unlock_fn)0x538DFF78u)(bytes + 0x24))
        return result == 1u ? 5u : 0u;
    if (result == 1u && !((notify_fn)0x538DB424u)(bytes + 8, 1u)) return 4;
    return result;
}
