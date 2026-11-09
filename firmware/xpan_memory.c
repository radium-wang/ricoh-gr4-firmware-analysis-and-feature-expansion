/* Freestanding ARM EABI helpers for compiler-generated structure copies.
 * Caller supplies valid owned objects. Volatile byte stores prevent these
 * loops from being lowered back into the same runtime helper. No allocation,
 * firmware address or external libc dependency. */
void __aeabi_memcpy(void *destination, const void *source, unsigned int bytes) {
    volatile unsigned char *out = destination;
    const unsigned char *in = source;
    for (unsigned int i=0u; i<bytes; ++i) out[i] = in[i];
}
void __aeabi_memclr4(void *destination, unsigned int bytes) {
    volatile unsigned char *out = destination;
    for (unsigned int i=0u; i<bytes; ++i) out[i] = 0u;
}
