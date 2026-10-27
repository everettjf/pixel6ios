#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "orioletouchid_flow.h"

/* Include the actual freestanding writer, not a model of it.  Stubs below
 * provide a deterministic fake ACPM and SPI11 register window. */
#define ORIOLE_TOUCH_ID_HW 1
#include "orioletouchid_hw.c"
#include "orioletouchid_flow.c"

struct reg { uintptr_t pa; uint32_t val; };
static struct reg regs[32];
static unsigned nr, writes, reads, fail_write_at, apply_fail_write_at;
static unsigned fail_read_at, forbidden_reads, tx_n, burst_n, rx_pos, reset_n;
static uint8_t tx_bytes[12];
static uint32_t rail25, rail26;
static uint64_t ticks;
static int force_timeout, uncertain_enable26, restore_error25;
static int disturb_engine_on_reset;
static int corrupt_quiet_on_reset;
static int live_board_ok, live_ram_ok;
static enum oti_stage reported_first, reported_cleanup;

static struct reg *reg(uintptr_t pa)
{
	unsigned i;
	for (i = 0; i < nr; i++) if (regs[i].pa == pa) return &regs[i];
	assert(nr < sizeof(regs) / sizeof(regs[0]));
	regs[nr].pa = pa;
	regs[nr].val = 0;
	return &regs[nr++];
}

static void seed(uintptr_t pa, uint32_t value) { reg(pa)->val = value; }
static uint32_t value(uintptr_t pa) { return reg(pa)->val; }

static void reset_fake(void)
{
	nr = writes = reads = fail_write_at = apply_fail_write_at = fail_read_at = 0;
	forbidden_reads = tx_n = burst_n = rx_pos = reset_n = 0;
	force_timeout = uncertain_enable26 = restore_error25 = 0;
	disturb_engine_on_reset = 1; corrupt_quiet_on_reset = 0;
	live_board_ok = live_ram_ok = 1;
	rail25 = 0x2c; rail26 = 0x3c; ticks = 1;
	reported_first = reported_cleanup = OTI_OK;
	seed(TOUCH_PIN_CLK_BANK, 0);
	seed(TOUCH_PIN_CLK_BANK + 4u, 0);
	seed(TOUCH_PIN_CLK_BANK + 8u, 0x1111u);
	seed(TOUCH_PIN_RESET_BANK, 0);
	seed(TOUCH_PIN_RESET_BANK + 4u, 0);
	seed(TOUCH_PIN_RESET_BANK + 8u, 0x11u);
	seed(TOUCH_USI_MODE_REG, 0);
	seed(TOP + TOUCH_CMUTOP_GATE, 0x200000u);
	seed(CMU + TOUCH_CMU_MUX_USI, 0x10u);
	seed(CMU + TOUCH_CMU_DIV, 0);
	seed(CMU + TOUCH_CMU_GATE_IPCLK, 0x200000u);
	seed(CMU + TOUCH_CMU_GATE_PCLK, 0x200000u);
	seed(CMU + TOUCH_CMU_GATE_RSTN, 0x200000u);
	seed(SPI + TP_SPI_CS_REG, 1);
}

static int burst_ready(void)
{
	unsigned i;
	static const uint8_t cmd[5] = { 0xfb, 0x20, 0, 0, 0 };
	if (rail25 != 0xac || rail26 != 0xbc ||
	    (value(TOUCH_USI_MODE_REG) & TOUCH_USI_MODE_MASK) != TOUCH_USI_MODE_SPI ||
	    value(USI + TP_USI_CON) != 0 ||
	    (value(SPI + TP_SPI_CH_CFG) & (TP_CH_RXCH_ON | TP_CH_TXCH_ON)) !=
	    (TP_CH_RXCH_ON | TP_CH_TXCH_ON) ||
	    value(SPI + TP_SPI_PACKET_CNT) != (5u | TP_PKT_CNT_EN) ||
	    value(SPI + TP_SPI_CS_REG) != 0 ||
	    (value(TOUCH_PIN_CLK_BANK + 4u) & (1u << TOUCH_PIN_CS_NR)) != 0 ||
	    (value(TOUCH_PIN_RESET_BANK + 4u) & 1u) == 0 || tx_n != 5)
		return 0;
	for (i = 0; i < 5; i++)
		if (tx_bytes[burst_n * 5u + i] != (burst_n == 0 ? cmd[i] : 0))
			return 0;
	return 1;
}

int try_read32(uintptr_t pa, uint32_t *v)
{
	reads++;
	if (reads == fail_read_at) return 0;
	if ((pa >= SPI && pa < SPI + 0x30u) || (pa >= USI && pa < USI + 0x10u)) {
		if ((value(TOUCH_USI_MODE_REG) & TOUCH_USI_MODE_MASK) != TOUCH_USI_MODE_SPI) {
			forbidden_reads++;
			return 0;
		}
	}
	if (pa == SPI + TP_SPI_STATUS) {
		*v = force_timeout || !burst_ready() ? 0u : 5u << 15;
	} else if (pa == SPI + TP_SPI_RX_DATA) {
		static const uint8_t reply[5] = { 0, 0x36, 0x48, 0, 0 };
		*v = burst_n == 1 ? reply[rx_pos] : 0;
		if (++rx_pos == 5) { burst_n++; tx_n = rx_pos = 0; }
	} else {
		*v = value(pa);
	}
	return 1;
}

int try_write32(uintptr_t pa, uint32_t v)
{
	writes++;
	if (writes == fail_write_at) return 0;
	if (pa == USI + TP_USI_CON && (v & TP_USI_CON_RESET) && disturb_engine_on_reset) {
		/* Model a destructive USI reset.  Untouched engine words must
		 * already be zero or the preflight should have refused. */
		seed(SPI + TP_SPI_CH_CFG, 0);
		seed(SPI + TP_SPI_CLK_CFG, 0);
		seed(SPI + TP_SPI_MODE_CFG, 0);
		seed(SPI + TP_SPI_CS_REG, 0);
		seed(SPI + TP_SPI_INT_EN, 0);
		seed(SPI + TP_SPI_PACKET_CNT, 0);
		seed(SPI + TP_SPI_SWAP_CFG, 0);
		seed(SPI + TP_SPI_FB_CLK, 0);
		if (corrupt_quiet_on_reset) seed(SPI + TP_SPI_MODE_CFG, 1);
	}
	if (pa == SPI + TP_SPI_TX_DATA) {
		assert(tx_n < 5u);
		assert(tx_n + burst_n * 5u < sizeof(tx_bytes));
		tx_bytes[tx_n + burst_n * 5u] = (uint8_t)v;
		tx_n++;
		return writes == apply_fail_write_at ? 0 : 1;
	}
	if (pa == SPI + TP_SPI_CH_CFG && (v & TP_CH_SW_RST)) {
		reset_n++;
		/* RX consumption advances the burst; reset drains any remaining FIFO. */
		rx_pos = 0;
	}
	seed(pa, v);
	return writes == apply_fail_write_at ? 0 : 1;
}

uint64_t touch_ticks(void) { ticks += 1000u; return ticks; }
uint64_t counter_freq(void) { return 24576000u; }

int fdt_root_compatible(uintptr_t dtb, const char *name)
{
	assert(dtb == 1 && strcmp(name, "google,GS101 Oriole") == 0);
	return live_board_ok;
}
int fdt_memory_contains(uintptr_t dtb, uint64_t base, uint64_t size)
{
	assert(dtb == 1 && base == 0x80000000u && size == 0x1000u);
	return live_ram_ok;
}

void acpm_cfg_init(struct acpm_cfg *c)
{
	*c = (struct acpm_cfg){0};
	c->ch_id = 2; c->rail[0].reg = 0x5c; c->rail[1].reg = 0x5d;
	c->layout_verified = c->elem_unit_verified = 1;
}
int acpm_describe(const struct acpm_cfg *c, struct acpm_chan *ch)
{
	(void)c;
	*ch = (struct acpm_chan){0};
	return 0;
}
int acpm_pmic_read(const struct acpm_cfg *c, uint32_t reg, uint32_t *v, struct acpm_trace *t)
{
	(void)c;
	assert(reg == 0x5c || reg == 0x5d);
	*v = reg == 0x5c ? rail25 : rail26;
	t->seq++;
	return 0;
}
int acpm_oriole_touch_rail_set(const struct acpm_cfg *c, uint32_t reg, int on, struct acpm_trace *t)
{
	(void)c;
	assert(reg == 0x5c || reg == 0x5d);
	t->b.published = 1;
	t->seq++;
	if (reg == 0x5c) rail25 = on ? 0xac : 0x2c;
	else rail26 = on ? 0xbc : 0x3c;
	if (reg == 0x5d && on && uncertain_enable26) return ACPM_E_TIMEOUT;
	if (reg == 0x5c && !on && restore_error25) return ACPM_E_TIMEOUT;
	return 0;
}

void con_hex2(const char *tag, const char *a, uint32_t av, const char *b, uint32_t bv)
{
	(void)a; (void)b;
	if (strcmp(tag, "ORIOLE TOUCH ID") == 0 && strcmp(a, "first") == 0) {
		reported_first = (enum oti_stage)av;
		reported_cleanup = (enum oti_stage)bv;
	}
}
void con_str(const char *tag, const char *s) { (void)tag; (void)s; }

static void assert_restored(void)
{
	assert(rail25 == 0x2c && rail26 == 0x3c);
	assert(value(TOUCH_USI_MODE_REG) == 0);
	assert((value(TOUCH_PIN_CLK_BANK) & 0xffffu) == 0);
	assert((value(TOUCH_PIN_RESET_BANK) & 0xffu) == 0);
	assert((value(CMU + TOUCH_CMU_MUX_USI) & 0x10u) == 0x10u);
	assert((value(CMU + TOUCH_CMU_DIV) & 0xfu) == 0);
	assert(value(TOUCH_PIN_CLK_BANK + 8u) == 0x1111u);
	assert(value(TOUCH_PIN_RESET_BANK + 8u) == 0x11u);
	assert(value(SPI + TP_SPI_CH_CFG) == 0);
	assert(value(SPI + TP_SPI_CLK_CFG) == 0);
	assert(value(SPI + TP_SPI_MODE_CFG) == 0);
	assert(value(SPI + TP_SPI_CS_REG) == 1);
	assert(value(SPI + TP_SPI_INT_EN) == 0);
	assert(value(SPI + TP_SPI_PACKET_CNT) == 0);
	assert(value(SPI + TP_SPI_SWAP_CFG) == 0);
	assert(value(SPI + TP_SPI_FB_CLK) == 0);
	assert(value(TOP + TOUCH_CMUTOP_GATE) == 0x200000u);
	assert(value(CMU + TOUCH_CMU_GATE_IPCLK) == 0x200000u);
	assert(value(CMU + TOUCH_CMU_GATE_PCLK) == 0x200000u);
	assert(value(CMU + TOUCH_CMU_GATE_RSTN) == 0x200000u);
	assert(forbidden_reads == 0);
}

int main(void)
{
	unsigned step, baseline_writes, baseline_reads;
	reset_fake();
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) == 0);
	assert(reported_first == OTI_OK && reported_cleanup == OTI_OK);
	assert(burst_n == 2 && tx_bytes[0] == 0xfb && tx_bytes[1] == 0x20);
	assert_restored();
	baseline_writes = writes;
	baseline_reads = reads;
	assert(reset_n >= 3);
	/* Fail each possible MMIO write once.  A failure before a mode switch
	 * must never cause an unsafe SPI read, and cleanup keeps both rails off. */
	for (step = 1; step <= baseline_writes; step++) {
		reset_fake();
		fail_write_at = step;
		assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0);
		assert(rail25 == 0x2c && rail26 == 0x3c && forbidden_reads == 0);
		if (reported_cleanup == OTI_OK) assert_restored();
	}
	/* A bus fault may be reported after the write reached the controller.
	 * The uncertain value must still be restored or reported as a failure. */
	for (step = 1; step <= baseline_writes; step++) {
		reset_fake();
		apply_fail_write_at = step;
		assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0);
		assert(rail25 == 0x2c && rail26 == 0x3c && forbidden_reads == 0);
		if (reported_cleanup == OTI_OK) assert_restored();
	}
	for (step = 1; step <= baseline_reads; step++) {
		reset_fake();
		fail_read_at = step;
		assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0);
		assert(rail25 == 0x2c && rail26 == 0x3c && forbidden_reads == 0);
		if (reported_cleanup == OTI_OK) assert_restored();
	}
	reset_fake(); force_timeout = 1;
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 && reported_first == OTI_SPI_IDENTIFY);
	assert_restored();
	reset_fake(); uncertain_enable26 = 1;
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 && reported_first == OTI_RAIL_ENABLE_26);
	assert_restored();
	reset_fake(); restore_error25 = 1;
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 && reported_cleanup == OTI_RAIL_RESTORE_25);
	assert_restored();
	reset_fake(); seed(SPI + TP_SPI_MODE_CFG, 1);
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 && reported_first == OTI_ENGINE_SNAPSHOT);
	assert(rail25 == 0x2c && rail26 == 0x3c && tx_n == 0);
	reset_fake(); corrupt_quiet_on_reset = 1;
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 && reported_first == OTI_SPI_PREPARE);
	assert(reported_cleanup == OTI_ENGINE_RESTORE && rail25 == 0x2c && rail26 == 0x3c);
	reset_fake(); live_board_ok = 0;
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 &&
	       reported_first == OTI_PREFLIGHT && writes == 0);
	reset_fake(); live_ram_ok = 0;
	assert(oriole_touch_id_run(1, 0x80000000u, 0x1000u) != 0 &&
	       reported_first == OTI_PREFLIGHT && writes == 0);
	puts("oriole touch ID hardware backend: fake MMIO/ACPM passed");
	return 0;
}
