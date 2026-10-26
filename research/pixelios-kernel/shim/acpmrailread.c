/* Oriole-only touch-rail inventory. The two FUNC_READ operations send bounded
 * ACPM IPC requests; they never issue a PMIC update or touch SPI/pad write.
 * Registers are S2MPG10 LDO25M/26M from soc.json (docs/research/23).
 */
#include <stdint.h>
#include "acpm.h"
#include "console.h"

#ifndef ORIOLE_ACPM_RAILS_READ
#error "acpmrailread.c is only for the Oriole rail-read inventory"
#endif

void acpm_rail_read_dump(void)
{
	struct acpm_cfg c;
	struct acpm_chan h;
	struct acpm_trace t = {0};
	uint32_t value = 0;
	int rc;
	unsigned i;

	acpm_cfg_init(&c);
	/* Fail closed if a board configuration changes before this experiment. */
	if (c.ch_id != 2 || c.rail[0].reg != 0x5cu ||
	    c.rail[1].reg != 0x5du || c.layout_verified != 1 ||
	    c.elem_unit_verified != 1) {
		con_str("ACPM RAIL", "configuration refused");
		return;
	}
	rc = acpm_describe(&c, &h);
	con_hex2("ACPM RAIL DESC", "rc", (uint32_t)rc, "why", h.why);
	if (rc || h.rr != h.rf || h.sr != h.sf) {
		con_str("ACPM RAIL", "descriptor or queue refused");
		return;
	}
	for (i = 0; i < 2; i++) {
		t.seq = i + 1;
		value = 0;
		rc = acpm_pmic_read(&c, c.rail[i].reg, &value, &t);
		con_hex2("ACPM RAIL READ", "reg", c.rail[i].reg, "rc", (uint32_t)rc);
		con_hex2("ACPM RAIL RESULT", "raw", value, "why", t.a.why);
		con_hex2("ACPM RAIL IPC", "published", t.a.published, "reply", t.a.had_reply);
		con_hex2("ACPM RAIL STATE", "ret", t.a.ret, "writes", t.a.n);
		if (rc)
			return; /* never make a second request after an uncertain first */
	}
}
