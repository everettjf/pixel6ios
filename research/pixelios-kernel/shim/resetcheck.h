#pragma once
#include <stdint.h>

/* Existing REBOOT_BL source: docs/research/10-reboot-to-bootloader-gs101.md;
 * offsets independently match the current Oriole vendor_boot pixel-reboot
 * node: PMU17460000, reboot-cmd810, swreset-system3a00, trigger2.
 * These are volatile PMU registers, never flash/misc writes. */
#define RC_SYSIP 0x17460810UL
#define RC_SWRESET 0x17463a00UL

int resetcheck_ready(void);
uint64_t resetcheck_ticks(void);
void resetcheck_wait_ms(unsigned ms);
int resetcheck_read(uintptr_t pa, uint32_t *v);
uint64_t resetcheck_write(uintptr_t pa, uint32_t v);
void oriole_resetcheck(uint64_t connect_deadline);
