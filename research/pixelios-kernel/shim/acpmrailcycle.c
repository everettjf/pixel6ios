/* Oriole-only, opt-in touch power cycle. No SPI/pad, storage, XNU or payload.
 * Initial register values are the 2026-10-26 Pixel 6 measurement; mismatch
 * refuses before any PMIC UPDATE. Every started enable gets a reverse-order
 * restore attempt, including an update with an uncertain reply. */
#include <stdint.h>
#include "acpm.h"
#include "console.h"

#ifndef ORIOLE_ACPM_RAIL_CYCLE
#error "acpmrailcycle.c must only be built for the isolated Oriole rail-cycle profile"
#endif

static int read_exact(const struct acpm_cfg *c, uint32_t reg, uint32_t expected, uint32_t *seq)
{
	struct acpm_trace t;
	uint32_t v = 0;
	int rc;

	t.seq = *seq;
	rc = acpm_pmic_read(c, reg, &v, &t);
	*seq = t.seq;
	con_hex2("ACPM CYCLE READ", "reg", reg, "value", v);
	con_hex2("ACPM CYCLE READ", "rc", (uint32_t)rc, "want", expected);
	return rc == 0 && v == expected;
}

static int set_rail(const struct acpm_cfg *c, uint32_t reg, int on, int *published, uint32_t *seq)
{
	struct acpm_trace t;
	int rc;

	t.seq = *seq;
	rc = acpm_oriole_touch_rail_set(c, reg, on, &t);
	*seq = t.seq;
	if (t.b.published)
		*published = 1;
	con_hex2("ACPM CYCLE SET", "reg", reg, "on", (uint32_t)on);
	con_hex2("ACPM CYCLE SET", "rc", (uint32_t)rc, "published", t.b.published);
	return rc;
}

void acpm_rail_cycle_run(void)
{
	struct acpm_cfg c;
	struct acpm_chan h;
	int a = 0, b = 0, done = 0, restored = 0, rc;
	uint32_t seq = 1;

	acpm_cfg_init(&c);
	if (c.ch_id != 2 || c.rail[0].reg != 0x5cu || c.rail[1].reg != 0x5du ||
	    c.layout_verified != 1 || c.elem_unit_verified != 1) {
		con_str("ACPM CYCLE", "configuration refused");
		return;
	}
	rc = acpm_describe(&c, &h);
	if (rc || h.rr != h.rf || h.sr != h.sf) {
		con_str("ACPM CYCLE", "descriptor or queue refused");
		return;
	}
	if (!read_exact(&c, 0x5cu, 0x2cu, &seq) || !read_exact(&c, 0x5du, 0x3cu, &seq)) {
		con_str("ACPM CYCLE", "initial values refused");
		return;
	}
	if (set_rail(&c, 0x5cu, 1, &a, &seq) || !read_exact(&c, 0x5cu, 0xacu, &seq))
		goto restore;
	if (set_rail(&c, 0x5du, 1, &b, &seq) || !read_exact(&c, 0x5du, 0xbcu, &seq))
		goto restore;
	done = 1;
	con_str("ACPM CYCLE", "both rails enabled and read back");

restore:
	if (b) {
		rc = set_rail(&c, 0x5du, 0, &b, &seq);
		if (rc && rc != ACPM_E_ON)
			con_str("ACPM CYCLE", "RESTORE FAILED LDO26M");
		else if (!read_exact(&c, 0x5du, 0x3cu, &seq))
			con_str("ACPM CYCLE", "RESTORE READBACK FAILED LDO26M");
		else
			restored++;
	}
	if (a) {
		rc = set_rail(&c, 0x5cu, 0, &a, &seq);
		if (rc && rc != ACPM_E_ON)
			con_str("ACPM CYCLE", "RESTORE FAILED LDO25M");
		else if (!read_exact(&c, 0x5cu, 0x2cu, &seq))
			con_str("ACPM CYCLE", "RESTORE READBACK FAILED LDO25M");
		else
			restored++;
	}
	con_hex2("ACPM CYCLE END", "enabled", (uint32_t)done, "restored", (uint32_t)restored);
}
