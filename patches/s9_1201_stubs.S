// s9_1201_stubs.S - SX474-1201 firmware function addresses

#define NSTUB(addr,name) \
	.global name; \
	.extern name; \
	name = addr
.text

NSTUB(0x0809870B, lcd_write_cmd)
NSTUB(0x08098721, lcd_write_data)
NSTUB(0x080998E1, gpio_set_bit)
NSTUB(0x080998E5, gpio_clear_bit)
NSTUB(0x08099855, gpio_init)
NSTUB(0x080986E9, lcd_rs_gpio_init)
NSTUB(0x08080AB3, delay_spin)
