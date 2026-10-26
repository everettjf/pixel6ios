/* Host-only fake APM test of the isolated Oriole touch-rail bit-7 setter.
 * No boot image links this experiment until its orchestration and source/object
 * auditors are reviewed independently. */
#define ORIOLE_ACPM_RAIL_CYCLE
#define TOUCH_RAILS_WRITE
#define main acpm_existing_host_main
#include "acpm_host_test.c"
#undef main
#include "acpmrailcycle.c"

static unsigned reports, failures, finished, nset;
static struct { uint32_t reg, on; } sets[8];
void con_str(const char *label, const char *s)
{
	(void)label;
	reports++;
	if (strstr(s, "FAILED")) failures++;
	if (strstr(s, "both rails enabled")) finished++;
}
void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb)
{
	if (!strcmp(label, "ACPM CYCLE SET") && !strcmp(a, "reg")) {
		assert(nset < 8 && !strcmp(b, "on"));
		sets[nset].reg = va;
		sets[nset++].on = vb;
	}
	if (!strcmp(label, "ACPM CYCLE END")) {
		assert(!strcmp(a, "enabled") && !strcmp(b, "restored"));
		finished = (va == 1 && vb == 2);
	}
	reports++;
}

static void expect_sets(unsigned count, uint32_t r0, uint32_t o0,
		uint32_t r1, uint32_t o1, uint32_t r2, uint32_t o2,
		uint32_t r3, uint32_t o3)
{
	uint32_t reg[] = {r0, r1, r2, r3}, on[] = {o0, o1, o2, o3};
	unsigned i;

	if (nset != count)
		fprintf(stderr, "rail-cycle set count got %u want %u (nbell %u) events: %x/%u %x/%u %x/%u %x/%u\n", nset, count, nbell,
			sets[0].reg, sets[0].on, sets[1].reg, sets[1].on,
			sets[2].reg, sets[2].on, sets[3].reg, sets[3].on);
	assert(nset == count);
	for (i = 0; i < count; i++)
		assert(sets[i].reg == reg[i] && sets[i].on == on[i]);
}

int main(void)
{
	struct acpm_cfg c;
	struct acpm_trace t = {0};
	unsigned before;

	setup(16);
	acpm_cfg_init(&c);
	pmic[0x5c] = 0x2c;
	pmic[0x5d] = 0x3c;
	assert(acpm_oriole_touch_rail_set(&c, 0x5c, 1, &t) == ACPM_OK);
	assert(pmic[0x5c] == 0xac && pmic[0x5d] == 0x3c);
	assert(t.a.had_reply && t.b.had_reply && t.b.published == 2);
	assert(acpm_oriole_touch_rail_set(&c, 0x5d, 1, &t) == ACPM_OK);
	assert(pmic[0x5d] == 0xbc);
	assert(acpm_oriole_touch_rail_set(&c, 0x5d, 0, &t) == ACPM_OK);
	assert(pmic[0x5d] == 0x3c && apm_w[1] == 0x00800002u);
	assert(acpm_oriole_touch_rail_set(&c, 0x5c, 0, &t) == ACPM_OK);
	assert(pmic[0x5c] == 0x2c && apm_w[1] == 0x00800002u);
	assert(busy_writes == 0 && replay_hazard == 0 && stray == 0);

	/* A repeat restore observes the already-off state; it never publishes an UPDATE. */
	before = nbell;
	assert(acpm_oriole_touch_rail_set(&c, 0x5c, 0, &t) == ACPM_E_ON);
	assert(nbell == before + 1 && pmic[0x5c] == 0x2c);

	setup(16);
	acpm_cfg_init(&c);
	c.layout_verified = 0;
	assert(acpm_oriole_touch_rail_set(&c, 0x5c, 1, &t) == ACPM_E_UNSURE && nw == 0);
	c.layout_verified = 1;
	assert(acpm_oriole_touch_rail_set(&c, 0x5e, 1, &t) == ACPM_E_UNSURE && nw == 0);
	c.rail[0].vsel_known = 0;
	assert(acpm_oriole_touch_rail_set(&c, 0x5c, 1, &t) == ACPM_E_UNSURE && nw == 0);

	/* A changed handoff voltage is read but never updated. */
	setup(16);
	acpm_cfg_init(&c);
	pmic[0x5c] = 0x2d;
	assert(acpm_oriole_touch_rail_set(&c, 0x5c, 1, &t) == ACPM_E_RAIL);
	assert(nbell == 1 && pmic[0x5c] == 0x2d);

	/* Full orchestrator: exact initial values, both on, reverse restore. */
	setup(16);
	pmic[0x5c] = 0x2c;
	pmic[0x5d] = 0x3c;
	reports = failures = finished = nset = 0;
	acpm_rail_cycle_run();
	assert(pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	assert(nbell == 14 && finished == 1 && failures == 0 && reports > 0);
	expect_sets(4, 0x5c, 1, 0x5d, 1, 0x5d, 0, 0x5c, 0);
	assert(busy_writes == 0 && replay_hazard == 0 && stray == 0);

	/* Changed voltage refuses before any UPDATE or second rail request. */
	setup(16);
	pmic[0x5c] = 0x2d;
	pmic[0x5d] = 0x3c;
	finished = nset = 0;
	acpm_rail_cycle_run();
	assert(nbell == 1 && finished == 0 && pmic[0x5c] == 0x2d);

	/* An acknowledged but unapplied enable fails readback and stops there. */
	setup(16);
	pmic[0x5c] = 0x2c;
	pmic[0x5d] = 0x3c;
	ignore_upd = 1;
	finished = nset = 0;
	acpm_rail_cycle_run();
	assert(nbell == 7 && finished == 0 && pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	expect_sets(2, 0x5c, 1, 0x5c, 0, 0, 0, 0, 0);

	/* The second enable is rejected by firmware; the first rail must still
	 * be restored, and neither rail remains powered. */
	setup(16);
	pmic[0x5c] = 0x2c;
	pmic[0x5d] = 0x3c;
	fail_upd_reg = 0x5d;
	finished = nset = 0;
	acpm_rail_cycle_run();
	assert(finished == 0 && pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	expect_sets(4, 0x5c, 1, 0x5d, 1, 0x5d, 0, 0x5c, 0);
	assert(busy_writes == 0 && replay_hazard == 0 && stray == 0);

	/* Every fault after the first enable is published must enter the
	 * restoration path without attempting LDO26M. The async timeout cases
	 * may prevent completion; the attempt and failure stay visible. */
	for (int fault = 0; fault < 6; fault++) {
		setup(16);
		pmic[0x5c] = 0x2c;
		pmic[0x5d] = 0x3c;
		finished = nset = 0;
		switch (fault) {
		case 0: update_mode = M_NEVER; break;
		case 1: update_mode = M_NOREPLY; break;
		case 2: update_mode = M_BADSEQ; break;
		case 3: update_mode = M_RET; break;
		case 4: update_reply_fault = 1; break;
		case 5: update_bell_fault = 1; break;
		}
		acpm_rail_cycle_run();
		assert(finished == 0);
		expect_sets(2, 0x5c, 1, 0x5c, 0, 0, 0, 0, 0);
		assert(stray == 0 && busy_writes == 0 && replay_hazard == 0);
	}

	/* A front-write fault is conservatively marked as uncertain publication,
	 * so the caller still attempts a read-and-restore. */
	setup(16);
	pmic[0x5c] = 0x2c;
	pmic[0x5d] = 0x3c;
	finished = nset = 0;
	update_front_fault = 1;
	acpm_rail_cycle_run();
	assert(finished == 0 && pmic[0x5c] == 0x2c && pmic[0x5d] == 0x3c);
	expect_sets(2, 0x5c, 1, 0x5c, 0, 0, 0, 0, 0);
	puts("PASS Oriole exact touch-rail enable and restore");
	return 0;
}
