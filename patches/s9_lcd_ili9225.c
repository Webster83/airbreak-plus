/*
 * s9_lcd_ili9225.c - ILI9225 LCD driver for SX474-0905 hardware
 *
 * Replaces HX8347-D driver in SX474-12xx firmware.
 * Both LCDs are 176x220 16-bit color on FSMC bank 2 (0x64000000).
 *
 * Patched functions:
 *   lcd_init    - replaces 0x08080EC8
 *   set_window  - replaces 0x08045290
 *   set_cursor  - replaces 0x0804526A
 */

#define MAIN    __attribute__((section(".text.0.main")))
#define STATIC  static __attribute__((section(".text.x.nonmain")))

typedef unsigned int      uint32;
typedef unsigned short    uint16;
typedef unsigned char     uint8;

extern void lcd_write_cmd(uint16 index);
extern void lcd_write_data(uint16 value);
extern void gpio_set_bit(uint32 gpio_base, uint16 bit);
extern void gpio_clear_bit(uint32 gpio_base, uint16 bit);
extern void gpio_init(uint32 gpio_base, void *init_struct);
extern void lcd_rs_gpio_init(void);
extern void delay_spin(void);

typedef struct {
    uint16 pin;
    uint8  mode;
    uint8  speed;
} gpio_init_t;

STATIC void ili_write_reg(uint16 reg, uint16 val)
{
    lcd_write_cmd(reg);
    lcd_write_data(val);
}

// ~1ms per unit. delay_spin is ~0.1ms at 72MHz.
STATIC void ili_delay_ms(int ms)
{
    int i;
    for (i = 0; i < ms * 10; i++)
        delay_spin();
}

// ILI9225 init - register values from SX474-0905 firmware at 0x08050030
MAIN void ili9225_lcd_init(void)
{
    uint32 gpioe = 0x40011800;
    uint16 pin4  = 0x10;

    // GPIOG.15 (RS/DC) - push-pull output
    lcd_rs_gpio_init();

    // GPIOG.9 (FSMC_NE2) - chip select for bank 2 (0x64000000)
    // 0905 board routes LCD CS through PG9; 1203 ties CS low
    {
        gpio_init_t cfg = { 0x0200, 0x0B, 0x10 };
        gpio_init(0x40012000, &cfg);
    }

    // GPIOE.4 (RESET) - push-pull output
    {
        gpio_init_t cfg = { 0x0010, 0x03, 0x10 };
        gpio_init(gpioe, &cfg);
    }

    // hardware reset
    gpio_clear_bit(gpioe, pin4);
    ili_delay_ms(10);
    gpio_set_bit(gpioe, pin4);
    ili_delay_ms(50);

    // power-on sequence
    ili_write_reg(0x28, 0x00FF);  ili_delay_ms(5);
    ili_write_reg(0x07, 0x0000);
    ili_write_reg(0x11, 0x0000);  ili_delay_ms(5);

    ili_write_reg(0x11, 0x001A);
    ili_write_reg(0x12, 0x3121);
    ili_write_reg(0x13, 0x004C);
    ili_write_reg(0x14, 0x5C69);
    ili_write_reg(0x10, 0x0800);  ili_delay_ms(10);

    // step-up ramp
    ili_write_reg(0x11, 0x011A);  ili_delay_ms(50);
    ili_write_reg(0x11, 0x031A);  ili_delay_ms(50);
    ili_write_reg(0x11, 0x071A);  ili_delay_ms(50);
    ili_write_reg(0x11, 0x0F1A);  ili_delay_ms(50);
    ili_write_reg(0x11, 0x0F3A);  ili_delay_ms(50);

    // display control
    ili_write_reg(0x01, 0x011C);  // driver output: SS=1, NL=0x1C (176 lines)
    ili_write_reg(0x02, 0x0100);  // line inversion
    ili_write_reg(0x03, 0x0018);  // entry mode: BGR=0 (emWin=RGB565), ID0=1, AM=1
    ili_write_reg(0x07, 0x0000);
    ili_write_reg(0x08, 0x0808);
    ili_write_reg(0x0B, 0x1100);
    ili_write_reg(0x0C, 0x0000);
    ili_write_reg(0x0F, 0x1401);
    ili_write_reg(0x15, 0x0000);

    // full-screen window
    ili_write_reg(0x30, 0x0000);
    ili_write_reg(0x36, 0x00AF);  // H end = 175
    ili_write_reg(0x37, 0x0000);
    ili_write_reg(0x38, 0x00DB);  // V end = 219
    ili_write_reg(0x39, 0x0000);

    // gamma
    ili_write_reg(0x50, 0x0001);
    ili_write_reg(0x51, 0x020B);
    ili_write_reg(0x52, 0x0805);
    ili_write_reg(0x53, 0x0404);
    ili_write_reg(0x54, 0x0C0C);
    ili_write_reg(0x55, 0x000C);
    ili_write_reg(0x56, 0x0101);
    ili_write_reg(0x57, 0x0400);
    ili_write_reg(0x58, 0x1108);
    ili_write_reg(0x59, 0x0006);

    // display on
    ili_write_reg(0x0F, 0x0A01);
    ili_write_reg(0x07, 0x1012);  ili_delay_ms(50);
    ili_write_reg(0x20, 0x0000);
    ili_write_reg(0x21, 0x0000);
    ili_write_reg(0x07, 0x1017);  ili_delay_ms(100);
    lcd_write_cmd(0x22);
}


/*
 * Set drawing window.
 * emWin sends landscape coords (x=0..219, y=0..175).
 * ILI9225 is portrait (H=0..175, V=0..219), so we swap x<->y
 * and invert V (219-x) to fix the left-right mirror.
 * AM=1 in entry mode makes pixel fill match emWin's x-major scan.
 */
__attribute__((section(".text.1.set_window"), used, noinline))
void ili9225_set_window(int x0, int y0, int x1, int y1)
{
    // emWin window cache
    *(volatile uint32 *)0x200164F4 = x0;
    *(volatile uint32 *)0x200164F8 = y0;
    *(volatile uint32 *)0x200164FC = x1;
    *(volatile uint32 *)0x20016500 = y1;

    ili_write_reg(0x37, (uint16)y0);            // H start
    ili_write_reg(0x36, (uint16)y1);            // H end
    ili_write_reg(0x39, (uint16)(219 - x1));    // V start
    ili_write_reg(0x38, (uint16)(219 - x0));    // V end
    ili_write_reg(0x20, (uint16)y0);            // cursor H
    ili_write_reg(0x21, (uint16)(219 - x0));    // cursor V
    lcd_write_cmd(0x22);
}


// Set GRAM cursor + enter write mode.
__attribute__((section(".text.2.set_cursor"), used, noinline))
void ili9225_set_cursor(int x, int y)
{
    ili_write_reg(0x20, (uint16)y);
    ili_write_reg(0x21, (uint16)(219 - x));
    lcd_write_cmd(0x22);
}
