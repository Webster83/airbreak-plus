/*
 * vid_spoof.c - MOP-based Variant ID override
 *
 * Hooks the g[8] persistent writeback (vtable+0xE4) to update VID
 * whenever MOP (therapy mode) is committed to handler table storage.
 *
 */

#ifndef VID_SPOOF_ADDR_ORIG
#error "VID_SPOOF_ADDR_ORIG not defined"
#endif
#ifndef VID_SPOOF_ADDR_HANDLER
#error "VID_SPOOF_ADDR_HANDLER not defined"
#endif
#ifndef VID_SPOOF_ADDR_MOP
#error "VID_SPOOF_ADDR_MOP not defined"
#endif

static int (* const orig_writeback)(void *) =
    (int (*)(void *))VID_SPOOF_ADDR_ORIG;

static volatile unsigned int  * const vid_handler  = (void *)VID_SPOOF_ADDR_HANDLER;
static volatile unsigned char * const mop_byte     = (void *)VID_SPOOF_ADDR_MOP;

static const unsigned char vid_lut[12] = {
    0x1A,   // CPAP
    0x1A,   // AutoSet
    0x1A,   // APAP
    0x0B,   // S
    0x07,   // ST
    0x07,   // T
    0x09,   // VAuto
    0x13,   // ASV
    0x13,   // ASVAuto
    0x2E,   // iVAPS
    0x07,   // PAC
    0x19    // AutoSet For Her
};

int __attribute__((section(".text.0.main")))
start(void *obj)
{
    int ret = orig_writeback(obj);

    unsigned char idx = ((unsigned char *)obj)[0x14];
    if (idx == 0) {
        unsigned char mop = *mop_byte;
        if (mop <= 11) {
            unsigned int v = vid_lut[mop];
            *vid_handler  = v;
        }
    }

    return ret;
}
