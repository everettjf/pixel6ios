/* Oriole XNU touch handoff: retain the measured LDO25M/LDO26M enable bits
 * while XNU owns FTM5. The writer is acpm_oriole_touch_rail_set(), which
 * accepts only these two registers and bit 7 (acpm.c, docs/research/23).
 * A loader failure returns to this shim and restores in reverse order.
 */
#include <stdint.h>
#include "acpm.h"
#include "acpmrailhold.h"
#include "console.h"

#ifndef ORIOLE_ACPM_TOUCH_HOLD
#error "acpmrailhold.c is only for the Oriole XNU touch-handoff image"
#endif

static int read_exact(struct acpm_touch_hold_state *s, const struct acpm_cfg *c,
	uint32_t reg, uint32_t expected)
{
	struct acpm_trace t;
	uint32_t got = 0;
	int rc;
	t.seq = s->seq;
	rc = acpm_pmic_read(c, reg, &got, &t);
	s->seq = t.seq;
	con_hex2("TOUCH HOLD READ", "reg", reg, "value", got);
	return rc == 0 && got == expected;
}

static int set_rail(struct acpm_touch_hold_state *s, const struct acpm_cfg *c,
	uint32_t reg, int on, unsigned *held)
{
	struct acpm_trace t;
	int rc;
	t.seq = s->seq;
	rc = acpm_oriole_touch_rail_set(c, reg, on, &t);
	s->seq = t.seq;
	/* A published request may take effect even if its reply is lost. */
	if (on && (t.b.published || rc == 0))
		*held = 1;
	con_hex2("TOUCH HOLD SET", "reg", reg, "rc", (uint32_t)rc);
	return rc;
}

int acpm_touch_hold_restore(struct acpm_touch_hold_state *s)
{
	struct acpm_cfg c;
	int ok = 1, rc;
	if (!s || (!s->held25 && !s->held26))
		return 0;
	acpm_cfg_init(&c);
	if (s->held26) {
		rc = set_rail(s, &c, 0x5du, 0, &s->held26);
		if ((rc != 0 && rc != ACPM_E_ON) || !read_exact(s, &c, 0x5du, 0x3cu))
			ok = 0;
		else
			s->held26 = 0;
	}
	if (s->held25) {
		rc = set_rail(s, &c, 0x5cu, 0, &s->held25);
		if ((rc != 0 && rc != ACPM_E_ON) || !read_exact(s, &c, 0x5cu, 0x2cu))
			ok = 0;
		else
			s->held25 = 0;
	}
	s->active = 0;
	con_str("TOUCH HOLD RESTORE", ok ? "both rails off" : "FAILED; do not enter XNU");
	return ok ? 0 : -1;
}

int acpm_touch_hold_start(struct acpm_touch_hold_state *s)
{
	struct acpm_cfg c;
	struct acpm_chan h;
	int rc;
	if (!s || s->active || s->held25 || s->held26)
		return -1;
	if (!s->seq)
		s->seq = 1;
	acpm_cfg_init(&c);
	if (c.ch_id != 2 || c.pmic_addr != 1 || c.speedy != 0 ||
	    c.rail[0].reg != 0x5cu || c.rail[1].reg != 0x5du ||
	    c.layout_verified != 1 || c.elem_unit_verified != 1 ||
	    acpm_describe(&c, &h) || h.rr != h.rf || h.sr != h.sf ||
	    !read_exact(s, &c, 0x5cu, 0x2cu) || !read_exact(s, &c, 0x5du, 0x3cu)) {
		con_str("TOUCH HOLD", "preflight refused");
		return -1;
	}
	rc = set_rail(s, &c, 0x5cu, 1, &s->held25);
	if (rc || !s->held25 || !read_exact(s, &c, 0x5cu, 0xacu))
		goto failed;
	rc = set_rail(s, &c, 0x5du, 1, &s->held26);
	if (rc || !s->held26 || !read_exact(s, &c, 0x5du, 0xbcu))
		goto failed;
	s->active = 1;
	con_str("TOUCH HOLD", "both rails enabled for XNU");
	return 0;
failed:
	con_str("TOUCH HOLD", "enable refused; restoring");
	(void)acpm_touch_hold_restore(s);
	return -1;
}
