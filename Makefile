# stm32-unlocked.bin: patch-airsense
# 	./patch-airsense stm32.bin $@

SRC=patches
BUILD=build

VID_SPOOF_VERSIONS := 0401 0306 0305 0302
VID_SPOOF_BINS = $(foreach v,$(VID_SPOOF_VERSIONS),$(BUILD)/vid_spoof_$(v).bin)

all: $(BUILD)/stm32-patched.bin $(BUILD)/stm32-asv.bin

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/stm32-patched.bin: patch-airsense $(BUILD)/common_code.bin $(BUILD)/graph.bin $(VID_SPOOF_BINS)
	export PATCH_CODE=1 && ./patch-airsense stm32.bin $@

$(BUILD)/stm32-asv.bin: patch-airsense $(BUILD)/common_code.bin $(BUILD)/graph.bin $(BUILD)/squarewave.bin $(BUILD)/asv_task_wrapper.bin $(BUILD)/wrapper_limit_max_pdiff.bin $(VID_SPOOF_BINS)
	export PATCH_CODE=1 && export PATCH_S=1 && export PATCH_ASV_TASK_WRAPPER=1 && export PATCH_VAUTO_WRAPPER=1 && ./patch-airsense stm32.bin $@

binaries: $(BUILD)/common_code.bin $(BUILD)/graph.bin $(BUILD)/squarewave.bin $(BUILD)/asv_task_wrapper.bin $(BUILD)/wrapper_limit_max_pdiff.bin $(VID_SPOOF_BINS)

serve:
	mkdocs serve
deploy:
	mkdocs gh-deploy

# There are decent distances between the different patches, 
# but if you substantially increase the amount of code, beware collisions.
# I've already had several happen in the past, whoops :F

$(BUILD)/common_code.elf: $(BUILD)/common_code.o $(BUILD)/stubs.o
common_code-offset := 0x80fe000

# The graphing is too large to fit directly in the location at 0x8067d2c,
# so it is in high in the flash and the function pointer is fixed up at 0x80f9c88
$(BUILD)/graph.elf: $(BUILD)/graph.o $(BUILD)/stubs.o
graph-offset := 0x80fcd40
graph-extra := --just-symbols=$(BUILD)/common_code.elf

$(BUILD)/squarewave.elf: $(BUILD)/squarewave.o $(BUILD)/stubs.o
squarewave-offset := 0x80fd200
squarewave-extra := --just-symbols=$(BUILD)/common_code.elf

$(BUILD)/asv_task_wrapper.elf: $(BUILD)/asv_task_wrapper.o $(BUILD)/stubs.o
asv_task_wrapper-offset := 0x80fdf00
asv_task_wrapper-extra := --just-symbols=$(BUILD)/common_code.elf

$(BUILD)/wrapper_limit_max_pdiff.elf: $(BUILD)/wrapper_limit_max_pdiff.o $(BUILD)/stubs.o
wrapper_limit_max_pdiff-offset := 0x80ff000
wrapper_limit_max_pdiff-extra := --just-symbols=$(BUILD)/common_code.elf

# If there is a new version of the ghidra XML, the stubs.S
# file will be regenerated so that the addresses and functions
# are at the correct address in the ELF image.
#stubs.S: stm32.bin.xml
#	./ghidra2stubs < $< > $@


CROSS ?= arm-none-eabi-
CC := $(CROSS)gcc
AS := $(CC)
LD := $(CROSS)ld
OBJCOPY := $(CROSS)objcopy

CFLAGS ?= \
	-g \
	-Os \
	-mcpu=cortex-m4 \
	-mhard-float \
	-mfp16-format=ieee \
	-mthumb \
	-W \
	-Wall \
	-Wno-unused-result \
	-Wno-unused-parameter \
	-Wno-unused-variable \
	-nostdlib \
	-nostdinc \
	-ffreestanding \

ASFLAGS ?= $(CFLAGS)

LDFLAGS ?= \
	--nostdlib \
	--no-dynamic-linker \
	--Ttext $($*-offset) \
	$($*-extra) \
	--entry start \
	--sort-section=name \

# TODO: Sort sections by name, lay out main before the rest, to avoid inlining everything

# $(BUILD)/shared_code.o: $(BUILD)/shared_code.c
# 	$(CC) $(CFLAGS) -static -shared -c -o $@ $<
$(BUILD)/%.o: $(SRC)/%.c
	$(CC) $(CFLAGS) -c -o $@ $<
$(BUILD)/%.o: $(SRC)/%.S
	$(AS) $(ASFLAGS) -c -o $@ $<
$(BUILD)/%.elf: | $(BUILD)
	$(LD) $(LDFLAGS) -o $@ $^

$(BUILD)/%.bin: $(BUILD)/%.elf
	$(OBJCOPY) -Obinary $< $@


# eeprom_stub - standalone CDX replacement for s10 platform
#
# Build: make eeprom_stub
# Output: build/eeprom_stub_nocrc.bin (raw, for patched bootloader)
#         build/eeprom_stub_full.bin  (768KB + CRC, for stock bootloader)

EEPROM_STUB_OFFSET ?= 0x08040000

EEPROM_STUB_OBJS := $(patsubst $(SRC)/%.c,$(BUILD)/%.o,$(wildcard $(SRC)/eeprom_stub*.c))

# The stub uses its own linker script
$(BUILD)/eeprom_stub.elf: $(EEPROM_STUB_OBJS) | $(BUILD)
	$(LD) --nostdlib \
		-T $(SRC)/eeprom_stub.ld \
		--defsym=STUB_FLASH_ORIGIN=$(EEPROM_STUB_OFFSET) \
		-o $@ $(EEPROM_STUB_OBJS)

$(BUILD)/eeprom_stub_nocrc.bin: $(BUILD)/eeprom_stub.elf
	$(OBJCOPY) -Obinary $< $@

eeprom_stub: $(BUILD)/eeprom_stub_nocrc.bin $(BUILD)/eeprom_stub_full.bin
	@echo "EEPROM stub built:"
	@echo "  $(BUILD)/eeprom_stub_nocrc.bin  (raw, for patched bootloader)"
	@echo "  $(BUILD)/eeprom_stub_full.bin   (768KB + CRC, for stock bootloader)"
	@$(CROSS)size $(BUILD)/eeprom_stub.elf

# Full CDX image: pad to region size, fix CRC16 for bootloader validation
$(BUILD)/eeprom_stub_full.bin: $(BUILD)/eeprom_stub_nocrc.bin
	@python3 python/fix_crc.py $< -o $@ --pad 0xC0000


# S9 LCD patch - ILI9225 driver for SX474-09xx boards
#
# Build: make s9_lcd_ili9225
# Usage: PATCH_S9_LCD=1 ./patch-airsense-s9 stm32-s9.bin output.bin
#
# S9 is STM32F103 (Cortex-M3), different flags from S10 (Cortex-M4)
# One binary per CDX version (stub addresses differ)

S9_CFLAGS := -Os -mcpu=cortex-m3 -mthumb \
	-W -Wall -Wno-unused-variable \
	-nostdlib -nostdinc -ffreestanding

S9_LCD_OFFSET := 0x080d8000
S9_VERSIONS := 1201 1203 1301

$(BUILD)/s9_lcd_ili9225.o: $(SRC)/s9_lcd_ili9225.c | $(BUILD)
	$(CC) $(S9_CFLAGS) -c -o $@ $<

# Generate per-version stubs + link + objcopy rules
define S9_LCD_VERSION_template
$(BUILD)/s9_$(1)_stubs.o: $(SRC)/s9_$(1)_stubs.S | $(BUILD)
	$$(CC) $$(S9_CFLAGS) -c -o $$@ $$<

$(BUILD)/s9_lcd_ili9225_$(1).elf: $(BUILD)/s9_lcd_ili9225.o $(BUILD)/s9_$(1)_stubs.o | $(BUILD)
	$$(LD) --nostdlib --no-dynamic-linker \
		--Ttext $$(S9_LCD_OFFSET) --entry ili9225_lcd_init --sort-section=name \
		-o $$@ $$^

$(BUILD)/s9_lcd_ili9225_$(1).bin: $(BUILD)/s9_lcd_ili9225_$(1).elf
	$$(OBJCOPY) -Obinary $$< $$@
endef

$(foreach v,$(S9_VERSIONS),$(eval $(call S9_LCD_VERSION_template,$(v))))

s9_lcd_ili9225: $(foreach v,$(S9_VERSIONS),$(BUILD)/s9_lcd_ili9225_$(v).bin)
	@echo "S9 LCD patches built:"
	@$(foreach v,$(S9_VERSIONS),echo "  $(BUILD)/s9_lcd_ili9225_$(v).bin";)

s9: $(BUILD)/stm32-s9.bin

s9_lcd: $(BUILD)/stm32-s9-lcd.bin

$(BUILD)/stm32-s9.bin: patch-airsense-s9 | $(BUILD)
	./patch-airsense-s9 stm32-s9.bin $@

$(BUILD)/stm32-s9-lcd.bin: patch-airsense-s9 s9_lcd_ili9225 | $(BUILD)
	PATCH_S9_LCD=1 ./patch-airsense-s9 stm32-s9.bin $@


# S10 LCD patch - ILI9325/ILI9328 driver for AirSense 10
#
# Build: make s10_lcd_ili9325
# Usage: PATCH_S10_LCD=1 ./patch-airsense stm32.bin output.bin

S10_LCD_OFFSET ?= 0x080FD800
S10_LCD_VERSIONS := 0401

$(BUILD)/s10_lcd_ili9325.o: $(SRC)/s10_lcd_ili9325.c | $(BUILD)
	$(CC) $(CFLAGS) -Wno-unused-parameter -c -o $@ $<

define S10_LCD_VERSION_template
$(BUILD)/s10_$(1)_stubs.o: $(SRC)/s10_$(1)_stubs.S | $(BUILD)
	$$(AS) $$(ASFLAGS) -c -o $$@ $$<

$(BUILD)/s10_lcd_ili9325_$(1).elf: $(BUILD)/s10_lcd_ili9325.o $(BUILD)/s10_$(1)_stubs.o | $(BUILD)
	$$(LD) --nostdlib --no-dynamic-linker \
		--Ttext $$(S10_LCD_OFFSET) --entry lcd_board_init --sort-section=name \
		-o $$@ $$^

$(BUILD)/s10_lcd_ili9325_$(1).bin: $(BUILD)/s10_lcd_ili9325_$(1).elf
	$$(OBJCOPY) -Obinary $$< $$@
endef

$(foreach v,$(S10_LCD_VERSIONS),$(eval $(call S10_LCD_VERSION_template,$(v))))

s10_lcd_ili9325: $(foreach v,$(S10_LCD_VERSIONS),$(BUILD)/s10_lcd_ili9325_$(v).bin)
	@echo "S10 LCD patches built:"
	@$(foreach v,$(S10_LCD_VERSIONS),echo "  $(BUILD)/s10_lcd_ili9325_$(v).bin";)
	@echo "Inject offset: $(S10_LCD_OFFSET)"


#
# VID Spoof - MOP-based Variant ID override
#

VID_SPOOF_OFFSET := 0x80fef00

#                       ORIG        HANDLER     MOP         VTENTRY
vid_spoof_addrs_0401 := 0x0806A51D  0x20009694  0x200104A2  0xF14CC
vid_spoof_addrs_0306 := 0x0806A51D  0x20009694  0x200104A2  0xF126C
vid_spoof_addrs_0305 := 0x0806A519  0x20009694  0x20010736  0xF1350
vid_spoof_addrs_0302 := 0x08069DF5  0x20009694  0x20010736  0xF0B54

vid_spoof_ORIG     = $(word 1,$(vid_spoof_addrs_$(1)))
vid_spoof_HANDLER  = $(word 2,$(vid_spoof_addrs_$(1)))
vid_spoof_MOP      = $(word 3,$(vid_spoof_addrs_$(1)))
vid_spoof_VTABLE   = $(word 4,$(vid_spoof_addrs_$(1)))

define vid_spoof_build_template
$(BUILD)/vid_spoof_$(1).o: $(SRC)/vid_spoof.c | $(BUILD)
	$$(CC) $$(CFLAGS) \
		-DVID_SPOOF_ADDR_ORIG=$(call vid_spoof_ORIG,$(1)) \
		-DVID_SPOOF_ADDR_HANDLER=$(call vid_spoof_HANDLER,$(1)) \
		-DVID_SPOOF_ADDR_MOP=$(call vid_spoof_MOP,$(1)) \
		-c -o $$@ $$<

$(BUILD)/vid_spoof_$(1).elf: $(BUILD)/vid_spoof_$(1).o | $(BUILD)
	$$(LD) --nostdlib --no-dynamic-linker \
		--Ttext $(VID_SPOOF_OFFSET) --entry start --sort-section=name \
		-o $$@ $$^

$(BUILD)/vid_spoof_$(1).bin: $(BUILD)/vid_spoof_$(1).elf
	$$(OBJCOPY) -Obinary $$< $$@
endef

$(foreach v,$(VID_SPOOF_VERSIONS),$(eval $(call vid_spoof_build_template,$(v))))

vid_spoof: $(VID_SPOOF_BINS)
	@echo "VID spoof patches built:"
	@$(foreach v,$(VID_SPOOF_VERSIONS),echo "  $(BUILD)/vid_spoof_$(v).bin";)


clean:
	$(RM) $(BUILD)/*
