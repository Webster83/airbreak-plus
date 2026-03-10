/*
 * s10_lcd_ili9325.c - Universal ILI9325/ILI9328/ILI9341 LCD driver for AirSense 10
 *
 * Reads controller ID at runtime. If ILI9325/9328, uses our driver.
 * Otherwise falls through to original ILI9341 code.
 *
 * Three patch points:
 *   Pool 0x7C020 (controller_init, r6): vtable callbacks
 *   Pool 0x7C01C (post_init, r7): FlexColor plumbing
 *   BL   0x7C030 (board_init): hardware power-on sequence
 */

#define MAIN    __attribute__((section(".text.0.main")))
#define HW_INIT __attribute__((section(".text.0.hw_init")))
#define CTRL    __attribute__((section(".text.0.ctrl_init")))
#define STATIC  static __attribute__((section(".text.x.nonmain")))

typedef unsigned int      uint32;
typedef unsigned short    uint16;
typedef unsigned char     uint8;

extern void lcd_write_cmd(uint16 index);
extern void lcd_write_data(uint16 value);
extern void flexcolor_ensure_init(void *driver);
extern void iwdg_reload(void);
extern void flexcolor_set_interface(void *ctx, int bits);

// original ILI9341 functions (called when ID != 9325/9328)
extern void original_controller_init(void *driver);
extern void original_hw_init(void *driver);
extern void original_board_init(void);

// FlexColor draw functions (controller-agnostic)
extern void flexcolor_draw_bitmap(void);
extern void flexcolor_fill_rect(void);
extern void flexcolor_draw_hline(void);
extern void flexcolor_draw_vline(void);
extern void flexcolor_cs_assert(void);
extern void flexcolor_write_data(void);

STATIC void ili_write_reg(uint16 reg, uint16 val)
{
    lcd_write_cmd(reg);
    lcd_write_data(val);
}

STATIC uint16 ili_read_data(void)
{
    return *(volatile uint16 *)0x64000002;
}

STATIC void delay_ms(int ms)
{
    volatile int i;
    for (i = 0; i < ms * 42000; i++) {
        if ((i & 0x3FFF) == 0)
            iwdg_reload();
    }
}

// Read controller ID register. Returns 0x9325, 0x9328, or something else.
STATIC uint16 read_lcd_id(void)
{
    lcd_write_cmd(0x0000);
    return ili_read_data();
}

STATIC int is_ili932x(void)
{
    uint16 id = read_lcd_id();
    return (id == 0x9325 || id == 0x9328);
}


// FlexColor vtable callbacks for ILI9325/9328

static const uint8 orient_bits[8] = {
    0x30, 0x00, 0x20, 0x10,
    0x38, 0x08, 0x28, 0x18,
};

STATIC void ili9325_set_window(void *ctx, int x0, int y0, int x1, int y1)
{
    int *p = (int *)ctx;
    int xoff = p[0x2C/4];
    int yoff = p[0x30/4];

    ili_write_reg(0x50, (uint16)(xoff + x0));
    ili_write_reg(0x51, (uint16)(xoff + x1));
    ili_write_reg(0x52, (uint16)(yoff + y0));
    ili_write_reg(0x53, (uint16)(yoff + y1));
    ili_write_reg(0x20, (uint16)(xoff + x0));
    ili_write_reg(0x21, (uint16)(yoff + y0));
    lcd_write_cmd(0x22);
}

STATIC void ili9325_set_cursor(void *ctx, int x, int y)
{
    int *p = (int *)ctx;
    int xoff = p[0x2C/4];
    int yoff = p[0x30/4];

    ili_write_reg(0x20, (uint16)(xoff + x));
    ili_write_reg(0x21, (uint16)(yoff + y));
    lcd_write_cmd(0x22);
}

STATIC void ili9325_set_orient(void *ctx)
{
    uint16 flags = *(uint16 *)((uint8 *)ctx + 0x24);
    uint16 entry = orient_bits[flags & 7]; // BGR=0 for emWin RGB565
    lcd_write_cmd(0x03);
    lcd_write_data(entry);
}

STATIC uint16 ili9325_read_pixel(void *ctx)
{
    lcd_write_cmd(0x22);
    (void)ili_read_data();
    return ili_read_data();
}

STATIC void ili9325_read_setup(void *ctx, int x0, int y0, int x1, int y1)
{
    ili9325_set_window(ctx, x0, y0, x1, y1);
}


// ILI9325 power-on sequence
STATIC void ili9325_power_on(void)
{
    ili_write_reg(0x01, 0x0000); // SS=0 (flip horizontal scan for 180°)
    ili_write_reg(0x02, 0x0700);
    ili_write_reg(0x03, 0x0030); // BGR=0 (emWin RGB565), ID1=1, ID0=1
    ili_write_reg(0x04, 0x0000);
    ili_write_reg(0x08, 0x0207);
    ili_write_reg(0x09, 0x0000);
    ili_write_reg(0x0A, 0x0000);
    ili_write_reg(0x0C, 0x0000);
    ili_write_reg(0x0D, 0x0000);
    ili_write_reg(0x0F, 0x0000);

    ili_write_reg(0x10, 0x0000);
    ili_write_reg(0x11, 0x0007);
    ili_write_reg(0x12, 0x0000);
    ili_write_reg(0x13, 0x0000);
    delay_ms(200);

    ili_write_reg(0x10, 0x1490);
    ili_write_reg(0x11, 0x0227);
    delay_ms(50);
    ili_write_reg(0x12, 0x001C);
    delay_ms(50);
    ili_write_reg(0x13, 0x1A00);
    ili_write_reg(0x29, 0x0025);
    ili_write_reg(0x2B, 0x000C);
    delay_ms(50);

    ili_write_reg(0x50, 0x0000);
    ili_write_reg(0x51, 0x00EF);
    ili_write_reg(0x52, 0x0000);
    ili_write_reg(0x53, 0x013F);

    ili_write_reg(0x60, 0x2700); // GS=0 (flip vertical scan for 180°)
    ili_write_reg(0x61, 0x0001);
    ili_write_reg(0x6A, 0x0000);

    ili_write_reg(0x80, 0x0000);
    ili_write_reg(0x81, 0x0000);
    ili_write_reg(0x82, 0x0000);
    ili_write_reg(0x83, 0x0000);
    ili_write_reg(0x84, 0x0000);
    ili_write_reg(0x85, 0x0000);

    ili_write_reg(0x90, 0x0010);
    ili_write_reg(0x92, 0x0600);
    ili_write_reg(0x93, 0x0003);
    ili_write_reg(0x95, 0x0110);
    ili_write_reg(0x97, 0x0000);
    ili_write_reg(0x98, 0x0000);

    ili_write_reg(0x30, 0x0000);
    ili_write_reg(0x31, 0x0506);
    ili_write_reg(0x32, 0x0104);
    ili_write_reg(0x35, 0x0207);
    ili_write_reg(0x36, 0x000F);
    ili_write_reg(0x37, 0x0306);
    ili_write_reg(0x38, 0x0102);
    ili_write_reg(0x39, 0x0707);
    ili_write_reg(0x3C, 0x0702);
    ili_write_reg(0x3D, 0x1604);

    ili_write_reg(0x07, 0x0133);
    delay_ms(50);
    lcd_write_cmd(0x22);
}


/*
 * Board-level init. Called after display control asserts hardware RESET.
 * Replaces BL to ILI9341 init at 0x0807BD28.
 */
HW_INIT void lcd_board_init(void)
{
    original_board_init();

    if (is_ili932x())
        ili9325_power_on();
}


/*
 * Slot r6 (runs FIRST): controller vtable callbacks.
 */
CTRL void lcd_controller_init(void *driver)
{
    if (!is_ili932x()) {
        original_controller_init(driver);
        return;
    }

    void *ctx;
    flexcolor_ensure_init(driver);
    ctx = *(void **)((uint8 *)driver + 8);

    *(void **)((uint8 *)ctx + 0x9C) = (void *)ili9325_set_window;
    *(void **)((uint8 *)ctx + 0xA0) = (void *)ili9325_set_cursor;
    *(void **)((uint8 *)ctx + 0xA4) = (void *)ili9325_set_orient;
    *(void **)((uint8 *)ctx + 0xAC) = (void *)ili9325_read_pixel;
    *(void **)((uint8 *)ctx + 0xBC) = (void *)ili9325_read_setup;
    *(void **)((uint8 *)ctx + 0x8C) = (void *)flexcolor_set_interface;

    *(uint16 *)((uint8 *)ctx + 0x26) &= ~0x0003;
}


/*
 * Slot r7 (runs SECOND): FlexColor plumbing.
 */
MAIN void lcd_post_init(void *driver)
{
    if (!is_ili932x()) {
        original_hw_init(driver);
        return;
    }

    void *ctx;
    flexcolor_ensure_init(driver);
    ctx = *(void **)((uint8 *)driver + 8);

    *(void **)((uint8 *)ctx + 0xC8) = (void *)flexcolor_draw_bitmap;
    *(void **)((uint8 *)ctx + 0xCC) = (void *)flexcolor_fill_rect;
    *(void **)((uint8 *)ctx + 0xD0) = (void *)flexcolor_draw_hline;
    *(void **)((uint8 *)ctx + 0xD4) = (void *)flexcolor_draw_vline;
    *(void **)((uint8 *)ctx + 0x94) = (void *)flexcolor_cs_assert;
    *(void **)((uint8 *)ctx + 0x98) = (void *)flexcolor_write_data;

    *(uint32 *)((uint8 *)ctx + 0xE0) = *(uint32 *)((uint8 *)ctx + 0xB8);
    flexcolor_set_interface(ctx, 0x10);
    *(uint32 *)((uint8 *)ctx + 0x38) = 0x10;
}
