/* Fake ACPM transport: exercise the XNU rail handoff and loader-return path. */
#define ORIOLE_ACPM_RAIL_CYCLE
#define ORIOLE_ACPM_TOUCH_HOLD
#define TOUCH_RAILS_WRITE
#define main acpm_existing_host_main
#include "acpm_host_test.c"
#undef main
#include "acpmrailhold.c"

static struct acpm_touch_hold_state state;

void con_str(const char *label, const char *s)
{
	(void)label;
	(void)s;
}

void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb)
{
	(void)label;
	(void)a;
	(void)va;
	(void)b;
	(void)vb;
}

static void reset_case(void)
{
	setup(16);
	pmic[0x5c] = 0x2c;
	pmic[0x5d] = 0x3c;
	state = (struct acpm_touch_hold_state){ .seq = 1 };
}

int main(void)
{
	unsigned before;
	reset_case();
	assert(acpm_touch_hold_start(&state) == 0);
	assert(state.active && state.held25 && state.held26);
	assert(pmic[0x5c] == 0xac && pmic[0x5d] == 0xbc);
	before = nbell;
	assert(acpm_touch_hold_start(&state) != 0 && nbell == before);
	assert(acpm_touch_hold_restore(&state) == 0);
	assert(!state.active && !state.held25 && !state.held26);
	assert(pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	before = nbell;
	assert(acpm_touch_hold_restore(&state) == 0 && nbell == before);
	assert(busy_writes == 0 && replay_hazard == 0 && stray == 0);

	reset_case();
	pmic[0x5c] = 0x2d;
	assert(acpm_touch_hold_start(&state) != 0 && nbell == 1);
	assert(pmic[0x5c] == 0x2d && !state.held25 && !state.held26);

	reset_case();
	pmic[0x5d] = 0x3d;
	assert(acpm_touch_hold_start(&state) != 0);
	assert(pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3d);
	assert(!state.held25 && !state.held26);

	reset_case();
	fail_upd_reg = 0x5c;
	assert(acpm_touch_hold_start(&state) != 0);
	assert(pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	assert(!state.held25 && !state.held26);

	reset_case();
	fail_upd_reg = 0x5d;
	assert(acpm_touch_hold_start(&state) != 0);
	assert(pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	assert(!state.held25 && !state.held26 && !state.active);
	assert(busy_writes == 0 && replay_hazard == 0 && stray == 0);

	reset_case();
	assert(acpm_touch_hold_start(&state) == 0);
	fail_upd_reg = 0x5d;
	assert(acpm_touch_hold_restore(&state) != 0);
	assert(!state.active && !state.held25 && state.held26);
	assert(acpm_touch_hold_start(&state) != 0);
	fail_upd_reg = -1;
	assert(acpm_touch_hold_restore(&state) == 0);
	assert(!state.held25 && !state.held26 && pmic[0x5d] == 0x3c);
	puts("PASS Oriole XNU touch rail hold/restore");
	return 0;
}
