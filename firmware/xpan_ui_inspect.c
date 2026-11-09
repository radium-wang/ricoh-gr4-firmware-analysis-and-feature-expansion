/* Bounded read-only AppMain inspection. No GUI/property/allocator calls.
 * Loader owns handler and the 256-byte report at handler+64 until the ROM
 * completion trampoline finishes its last owned memory store.
 */
_Static_assert(sizeof(void *) == 4, "GR IV 32-bit ABI required");
typedef unsigned int word;
static int heap(word p, word bytes) {
    return !(p & 3u) && p >= 0x59600008u && p <= 0x5A5FFFF0u - bytes;
}
static word get(word p, word offset) { return *(const volatile word *)(p + offset); }
void gr4_xpan_ui_inspect(void *handler) {
    volatile word *out = (volatile word *)((word)handler + 64);
    word c, l, begin, end, capacity, image;
    for (word i = 0; i < 64; ++i) out[i] = 0;
    out[0] = 0x58504931u; /* XPI1 */
    out[2] = get(0x55082000u, 4); /* current AppMain task ID */
    if (get(0x55080D40u, 0) != 0x53D94F08u) { out[1] |= 1; return; }
    c = get(0x55080D40u, 0xB0); out[3] = c;
    image = get(0x5539FC64u, 0x14); out[13] = image;
    if (heap(image, 4)) out[14] = get(image, 0);
    if (!c) { out[1] |= 2; return; }
    if (!heap(c, 0x1E4) || get(c, 0) != 0x53DA2C70u) { out[1] |= 4; return; }
    out[4] = get(c, 0x124);
    out[5] = *(const volatile unsigned char *)(c + 0x1A4);
    if (out[4] != 0x0200008Au || out[5] != 34u) { out[1] |= 8; return; }
    l = get(c, 0x198); out[6] = l;
    if (!heap(l, 0x190) || get(l, 0) != 0x53E98468u) { out[1] |= 16; return; }
    begin = get(l, 0xF4); end = get(l, 0xF8); capacity = get(l, 0xFC);
    if (!heap(begin, 20) || end < begin + 20u || end > capacity ||
        capacity > 0x5A5FFFF0u || ((end - begin) & 3u) || ((capacity - begin) & 3u)) {
        out[1] |= 32; return;
    }
    out[7] = (end - begin) / 4; out[8] = (capacity - begin) / 4;
    out[9] = *(const volatile unsigned char *)(l + 0x108);
    out[10] = get(l, 0x170); out[11] = get(l, 0x174);
    word storage = get(l, 0x168);
    if (heap(storage, 4)) out[12] = get(storage, 0);
    else out[1] |= 64;
    for (word i = 0; i < 5; ++i) {
        word record = get(begin, i * 4), item, ascii, slot = 16 + i * 8;
        out[slot] = record;
        if (!heap(record, 8)) { out[1] |= 128; continue; }
        item = get(record, 0); out[slot+1] = item;
        out[slot+2] = *(const volatile unsigned char *)(record + 4);
        if (!heap(item, 0x108) || get(item, 0) != 0x53E98F18u) { out[1] |= 256; continue; }
        ascii = get(item, 0x100); out[slot+3] = ascii;
        if (!heap(ascii, 0x100) || get(ascii, 0) != 0x53E97FD8u) { out[1] |= 512; continue; }
        out[slot+4] = get(ascii, 0xF0);
        out[slot+5] = *(const volatile unsigned char *)(ascii + 0xED);
    }
    /* Detect changed owning slots; snapshots are not a global lock. */
    if (get(0x55080D40u, 0xB0) != c || get(c, 0x198) != l ||
        get(0x5539FC64u, 0x14) != image) out[1] |= 1024;
}
