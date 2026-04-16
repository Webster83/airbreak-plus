/*
 * backlight_adapt.c - Continuous steady-state backlight adaptation
 *
 * Replaces the "bl backlight_state_machine" call from the backlight tick.
 *
 * State 0 is the steady "screen on" loop. Nonzero states handle wake,
 * timeout dim, and off transitions - those are passed to stock firmware.
 *
 * Uses firmware variables for all brightness levels:
 *   0x00FC ASF - ambient sensor filtered
 *   0x00FD ATH - ambient threshold
 *   0x00FE LBL - button backlight low
 *   0x00FF LLL - LCD backlight low
 *   0x0100 LBH - button backlight high
 *   0x0101 LLH - LCD backlight high
 */

#define STEP      2
#define MIN_HYST  0x10

extern int variable_get_g8(int var_id);
extern void backlight_state_machine(void *ctx);

// backlight context struct (partial, offsets match firmware layout)
struct bl_ctx {
    unsigned char state;         // 0x00: 0=steady, nonzero=transition
    char _pad0[0x35];
    unsigned char mode;          // 0x36: 0=bright, 1=dark
    unsigned char _pad1;
    void *ch_lcd;                // 0x38
    void *ch_btn0;               // 0x3C
    void *ch_btn1;               // 0x40
    void *ch_btn2;               // 0x44
    void *ch_btn3;               // 0x48
};

static void __attribute__((noinline, section(".text.x.apply_step"))) apply_step(void *channel, int target)
{
    if (!channel)
        return;

    unsigned char *ch = (unsigned char *)channel;
    int current = ch[5];

    if (current == target)
        return;

    int next;
    if (current > target) {
        next = current - STEP;
        if (next < target) next = target;
    } else {
        next = current + STEP;
        if (next > target) next = target;
    }

    ch[5] = (unsigned char)next;

    // call channel->vtable[7] (set_brightness)
    typedef void (*set_fn_t)(void *, int);
    unsigned int *vtable = *(unsigned int **)channel;
    set_fn_t set = (set_fn_t)vtable[7];
    set(channel, next);

    // prevent tail call, compiler must return here
    __asm volatile ("" ::: "memory");
}

void start(struct bl_ctx *ctx)
{
    // only override steady-state; transitions use stock logic
    if (ctx->state != 0) {
        backlight_state_machine(ctx);
        return;
    }

    int asf = variable_get_g8(0xFC);
    int ath = variable_get_g8(0xFD);

    // hysteresis deadband = max(ATH >> 5, MIN_HYST)
    int hyst = ath >> 5;
    if (hyst < MIN_HYST)
        hyst = MIN_HYST;

    int mode = ctx->mode;
    if (mode == 0) {
        // bright
        if (asf + hyst < ath)
            mode = 1;
    } else {
        // dark
        if (asf > ath + hyst)
            mode = 0;
    }
    ctx->mode = (unsigned char)mode;

    unsigned char lcd_target, btn_target;
    if (mode == 0) {
        lcd_target = (unsigned char)variable_get_g8(0x101);  // LLH
        btn_target = (unsigned char)variable_get_g8(0x100);  // LBH
    } else {
        lcd_target = (unsigned char)variable_get_g8(0xFF);   // LLL
        btn_target = (unsigned char)variable_get_g8(0xFE);   // LBL
    }

    apply_step(ctx->ch_lcd,  lcd_target);
    apply_step(ctx->ch_btn0, btn_target);
    apply_step(ctx->ch_btn1, btn_target);
    apply_step(ctx->ch_btn2, btn_target);
    apply_step(ctx->ch_btn3, btn_target);

    // prevent tail call
    __asm volatile ("" ::: "memory");
}
