#pragma once
#include <stdint.h>

/* One bounded Oriole FTM5 chip-ID attempt.  The hardware backend must use
 * explicit register allowlists and must snapshot before each write phase.
 * No storage or iOS payload operation is representable in this interface. */
enum oti_stage {
	OTI_OK = 0,
	OTI_BAD_OPS,
	OTI_PREFLIGHT,
	OTI_SHARED_SNAPSHOT,
	OTI_RAIL_READ,
	OTI_RAIL_ENABLE_25,
	OTI_RAIL_ENABLE_26,
	OTI_RAIL_VERIFY,
	OTI_MODE_SET,
	OTI_ENGINE_SNAPSHOT,
	OTI_SPI_PREPARE,
	OTI_SPI_IDENTIFY,
	OTI_ID_MISMATCH,
	OTI_ENGINE_RESTORE,
	OTI_MODE_RESTORE,
	OTI_SHARED_RESTORE,
	OTI_RAIL_RESTORE_26,
	OTI_RAIL_RESTORE_25,
	OTI_FIFO_READ
};

struct oti_ops {
	int (*preflight)(void *ctx);       /* FDT/RAM/ACPM descriptor and empty queues */
	int (*shared_snapshot)(void *ctx); /* all clock, GPIO and USI-mode words */
	int (*rail_read)(void *ctx, uint32_t reg, uint32_t *value);
	int (*rail_set)(void *ctx, uint32_t reg, int on, int *published);
	int (*mode_set)(void *ctx);        /* mode 2 write AND readback */
	int (*engine_snapshot)(void *ctx); /* only after verified mode 2 */
	int (*spi_prepare)(void *ctx);     /* one bounded setup, reset and CS */
	int (*spi_identify)(void *ctx, uint8_t id[4]); /* one FB 20 00 00 00 */
	int (*fifo_read)(void *ctx, uint8_t event[8]); /* optional: one 0x87 read, no scan */
	int (*engine_restore)(void *ctx);  /* independent attempts, even after fault */
	int (*mode_restore)(void *ctx);
	int (*shared_restore)(void *ctx);
};

struct oti_result {
	enum oti_stage first_error;
	enum oti_stage cleanup_error;
	uint8_t id[4];
	uint8_t event[8];
	unsigned attempts;
	unsigned fifo_attempts;
	unsigned rail25_restored;
	unsigned rail26_restored;
};

int oti_run(const struct oti_ops *ops, void *ctx, struct oti_result *result);
