#pragma once
#include <stdint.h>

/* Owned by the caller; the rail helper has no writable global state. */
struct acpm_touch_hold_state {
	uint32_t seq;
	unsigned held25, held26, active;
};

int acpm_touch_hold_start(struct acpm_touch_hold_state *s);
int acpm_touch_hold_restore(struct acpm_touch_hold_state *s);
