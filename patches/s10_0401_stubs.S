// SX567-0401 firmware function addresses

#define NSTUB(addr,name) \
	.global name; \
	.extern name; \
	name = addr
.text

// GUI / LCD
NSTUB(0x0807B5E5, GUI_SetColor)
NSTUB(0x0807B809, LCD_FillRect)
NSTUB(0x0807BB0F, LCD_SetClipRectMax)
NSTUB(0x0807B661, LCD_DrawPixel)
NSTUB(0x0806D499, snprintf)
NSTUB(0x08072D49, GUI_SetFont)
NSTUB(0x0806B243, GUI_SetFont_default)
NSTUB(0x08072D89, GUI_SetTextMode)
NSTUB(0x08072DA1, GUI_SetTextAlign)
NSTUB(0x0807BCE9, GUI_GotoXY)
NSTUB(0x08072F6D, GUI_DispStringAt)
NSTUB(0x08060DB4, font_16)
NSTUB(0x680000A0, gui_context)

NSTUB(0x08063D5D, malloc)
NSTUB(0x08082097, tim_read_tim5)

NSTUB(0x080BC993, pressure_limit_max_difference)
NSTUB(0x2000E948, fvars)
NSTUB(0x2000E750, ivars)
NSTUB(0x2000E808, isNotBreathingPtr)
NSTUB(0x2000EA9C, breathPercentagePtr)
NSTUB(0x080E3465, asv_task_function)

NSTUB(0x20000BE0, magic_ptr)

// Backlight adaptation
NSTUB(0x08066FC6, variable_get_g8)
NSTUB(0x0807A2A4, backlight_state_machine)

// LCD driver
NSTUB(0x08080E37, lcd_write_cmd)
NSTUB(0x08080E3F, lcd_write_data)
NSTUB(0x080814E3, flexcolor_ensure_init)
NSTUB(0x080E2EF1, flexcolor_set_interface)
NSTUB(0x080E2F17, original_controller_init)
NSTUB(0x080D9287, original_hw_init)
NSTUB(0x0807BD29, original_board_init)
NSTUB(0x080D9171, flexcolor_draw_bitmap)
NSTUB(0x080D9093, flexcolor_fill_rect)
NSTUB(0x0808143B, flexcolor_draw_hline)
NSTUB(0x08081389, flexcolor_draw_vline)
NSTUB(0x080D8C03, flexcolor_cs_assert)
NSTUB(0x080D8C0D, flexcolor_write_data)
NSTUB(0x080875BB, iwdg_reload)
NSTUB(0x08080CDB, lcd_get_device)
