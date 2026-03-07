// s9_1301_stubs.S - SX474-1301 firmware function addresses

#define NSTUB(addr,name) \
	.global name; \
	.extern name; \
	name = addr
.text

NSTUB(0x080B5AAB, lcd_write_cmd)
NSTUB(0x080B5AC1, lcd_write_data)
NSTUB(0x080B728D, gpio_set_bit)
NSTUB(0x080B7291, gpio_clear_bit)
NSTUB(0x080B7201, gpio_init)
NSTUB(0x080B5A89, lcd_rs_gpio_init)
NSTUB(0x08099FE7, delay_spin)
