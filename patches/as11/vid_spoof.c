/*
 * vid_spoof.c - MOP-based VariantIdentifier (VID) override
 *
 * Hooks the persistent writeback to update VID whenever MOP (therapy mode) is committed
 *
 * The Python patcher resolves firmware-specific addresses and patches the
 * parameter block before injecting this hook.
 */

#define AS11_VID_SPOOF_MAGIC 0x56313141u

struct as11_vid_spoof_params {
    unsigned int magic;
    unsigned int orig_writeback;
    unsigned int vid_addr;
    unsigned int mop_addr;
    unsigned int mop_index;
};

static volatile const struct as11_vid_spoof_params params
    __attribute__((used, section(".rodata.params"))) = {
        AS11_VID_SPOOF_MAGIC,
        0x11111111u,
        0x22222222u,
        0x33333333u,
        0x44444444u,
    };

/*
 * AS11 dump-backed mode groups:
 *   VID  3: CPAP, AutoSet, AutoSet For Her
 *   VID  7: Spont, VAuto
 *   VID 10: ST, Timed
 *   VID 12: ASV, ASVAuto
 *
 * iVAPS and PAC are not mapped for now;
 */
static const unsigned char vid_lut[11] = {
    3,   // CPAP
    3,   // AutoSet
    3,   // AutoSet For Her
    7,   // Spont
    10,  // ST
    10,  // Timed
    7,   // VAuto
    12,  // ASV
    12,  // ASVAuto
    0,   // iVAPS
    0,   // PAC
};

void __attribute__((section(".text.0.main")))
start(void *obj)
{
    ((void (*)(void *))params.orig_writeback)(obj);

    if (*(short *)((unsigned char *)obj + 0x14) == (short)params.mop_index) {
        unsigned char mop = *(volatile unsigned char *)params.mop_addr;
        if (mop < sizeof(vid_lut)) {
            unsigned int vid = vid_lut[mop];
            if (vid != 0) {
                *(volatile unsigned int *)params.vid_addr = vid;
            }
        }
    }
}
