/* Oriole inventory: bounded, read-only snapshot of the ACPM channel layout.
 * acpm_describe() reads the SRAM descriptor and queue indices; no IPC request
 * is sent. ORIOLE_ACPM_DESC_ONLY compiles transaction functions out of acpm.c.
 */
#include <stdint.h>
#include "acpm.h"
#include "console.h"

#ifndef ORIOLE_ACPM_DESC_ONLY
#error "acpmdesc.c requires the descriptor-only ACPM build"
#endif

void acpm_desc_dump(void)
{
	struct acpm_cfg c;
	struct acpm_chan h;
	uint32_t i, id;
	int rc;

	acpm_cfg_init(&c);
	rc = acpm_describe(&c, &h);
	con_hex2("ACPM DESC", "rc", (uint32_t)rc, "why", h.why);
	con_hex2("ACPM INIT", "n", h.n, "tab", h.tab);
	for (i = 0; i < 8; i++)
		con_hex2("ACPM INIT WORD", "index", i, "value", h.init[i]);
	if (h.why == ACPM_W_NOCH)
		for (i = 0; i < h.n && i < ACPM_MAX_AP_CH; i++)
			if (acpm_chan_id(&c, &h, i, &id))
				con_hex2("ACPM CH ID", "index", i, "id", id);
	if (!h.have_desc)
		return;
	con_hex2("ACPM CH", "index", h.idx, "length", h.qlen);
	for (i = 0; i < ACPM_DESC_WORDS; i++)
		con_hex2("ACPM DESC WORD", "index", i, "value", h.d[i]);
	con_hex2("ACPM REQ IDX", "rear", h.rr, "front", h.rf);
	con_hex2("ACPM RSP IDX", "rear", h.sr, "front", h.sf);
	con_hex2("ACPM ELEM", "raw", h.esz, "bytes", h.esz_b);
}
