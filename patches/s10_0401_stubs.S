// SX567-0401 firmware function addresses

#define NSTUB(addr,name) \
	.global name; \
	.extern name; \
	name = addr
.text

// FSMC LCD bus writes
NSTUB(0x08080E37, lcd_write_cmd)
NSTUB(0x08080E3F, lcd_write_data)

// emWin FlexColor
NSTUB(0x080814E3, flexcolor_ensure_init)
NSTUB(0x080E2EF1, flexcolor_set_interface)

// Original ILI9341 functions (fallback when ID != 9325/9328)
NSTUB(0x080E2F17, original_controller_init)
NSTUB(0x080D9287, original_hw_init)
NSTUB(0x0807BD29, original_board_init)

// FlexColor drawing (controller-agnostic)
NSTUB(0x080D9171, flexcolor_draw_bitmap)
NSTUB(0x080D9093, flexcolor_fill_rect)
NSTUB(0x0808143B, flexcolor_draw_hline)
NSTUB(0x08081389, flexcolor_draw_vline)

// CS/data wrappers
NSTUB(0x080D8C03, flexcolor_cs_assert)
NSTUB(0x080D8C0D, flexcolor_write_data)

// IWDG watchdog reload
NSTUB(0x080875BB, iwdg_reload)
