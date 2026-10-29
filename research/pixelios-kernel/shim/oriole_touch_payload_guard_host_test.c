/* Exercise the exact runtime guard against the hash-pinned private payload. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "ufsroot_guard.h"

int main(int argc, char **argv)
{
	FILE *f;
	uint8_t *buf;
	long len;
	assert(argc == 2);
	f = fopen(argv[1], "rb");
	assert(f);
	assert(fseek(f, 0, SEEK_END) == 0);
	len = ftell(f);
#ifdef ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_HID_DIAG_0128
    assert(len == 16753760L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETIF_0126)
    assert(len == 16753584L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETROUTE_RESOURCE_0125)
    assert(len == 16713744L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETROUTE_0124)
    assert(len == 16730160L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_GUI_0121)
    assert(len == 16713664L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_GUI)
    assert(len == 16716864L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID_SYSINFO)
	assert(len == 16716832L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID_RAILHOLD)
	assert(len == 16716800L);
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID_RAILCYCLE)
	assert(len == 16716768L);
#else
	assert(len == 16716528L);
#endif
	assert(fseek(f, 0, SEEK_SET) == 0);
	buf = malloc((size_t)len);
	assert(buf);
	assert(fread(buf, 1, (size_t)len, f) == (size_t)len);
	assert(fclose(f) == 0);
	assert(ufsroot_payload_ok((const struct payload *)buf, (uint64_t)len));
	assert(!ufsroot_payload_ok((const struct payload *)buf, (uint64_t)len - 1));
	free(buf);
	puts("PASS Oriole touch payload through runtime UFS-root guard");
	return 0;
}
