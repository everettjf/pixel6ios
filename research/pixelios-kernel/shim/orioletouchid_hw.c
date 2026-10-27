/* Pixel 6-only, one-shot FTM5 ID backend.  UNLINKED until the allowlist,
 * fake-MMIO fault tests and independent review pass.  Register provenance:
 * xnu/patches/0088 (GS101 SPI/GPIO), 0089/0092 (CMU), Google's GS101 touch
 * device tree and ABL SPI sequence in docs/research/21.  Initial values are
 * the real Oriole read-only capture touch-inventory-2026-10-26.txt. */
#include <stdint.h>
#include "acpm.h"
#include "console.h"
#include "fdt.h"
#include "touchprobe.h"
#include "orioletouchid_flow.h"

#if !defined(ORIOLE_TOUCH_ID_HW) || !SOC_GS101
#error "this backend is only for an isolated Oriole touch-ID image"
#endif

#define SPI TOUCH_SPI_BASE
#define USI (TOUCH_SPI_BASE + TOUCH_USI_OFF)
#define CMU TOUCH_CMU_BASE
#define TOP TOUCH_CMUTOP_BASE
#define POLL_MAX 2000000u
/* ABL's manual-burst sequence writes bit 0 at USI_OPTION.  The Linux
 * controller driver uses bit 1; this profile follows the ABL path. */
#define OTI_USI_OPTION_ABL 1u

enum shared_reg {
	S_SPI_CON, S_SPI_DAT, S_SPI_PUD, S_CTRL_CON, S_CTRL_DAT,
	S_CTRL_PUD, S_MODE, S_TOP_GATE, S_MUX, S_DIV,
	S_IPCLK, S_PCLK, S_RSTN, S_COUNT
};
enum engine_reg {
	E_USI_CON, E_USI_OPTION, E_CH, E_CS, E_PKT, E_FB, E_COUNT
};
/* These words are read after mode 2 is verified.  USI reset may clear the
 * engine, so only an idle default handoff is accepted before asserting it. */
static const uint32_t quiet_offsets[] = {
	TP_SPI_CLK_CFG, TP_SPI_MODE_CFG, TP_SPI_INT_EN, TP_SPI_SWAP_CFG
};
struct cell {
	uintptr_t pa;
	uint32_t old, mask;
	int changed;
};
struct hw {
	struct acpm_cfg acpm;
	uint32_t seq;
	uintptr_t dtb;
	uint64_t image_base, image_size;
	struct cell s[S_COUNT], e[E_COUNT];
};

static int rd(uintptr_t pa, uint32_t *v)
{
	return try_read32(pa, v) ? 0 : -1;
}

/* An independent address+bit allowlist, not supplied by the caller.  No
 * arbitrary poke; TX_DATA accepts only the ID command bytes or dummy zero. */
static uint32_t allowed_mask(uintptr_t pa)
{
	if (pa == TOUCH_PIN_CLK_BANK) return 0xffffu;
	if (pa == TOUCH_PIN_CLK_BANK + 4u) return 1u << TOUCH_PIN_CS_NR;
	if (pa == TOUCH_PIN_CLK_BANK + 8u) return 0xffffu;
	if (pa == TOUCH_PIN_RESET_BANK) return 0xffu;
	if (pa == TOUCH_PIN_RESET_BANK + 4u) return 0x3u;
	if (pa == TOUCH_PIN_RESET_BANK + 8u) return 0xfu;
	if (pa == TOUCH_USI_MODE_REG) return TOUCH_USI_MODE_MASK;
	if (pa == TOP + TOUCH_CMUTOP_GATE) return 1u << TOUCH_CMUTOP_GATE_BIT;
	if (pa == CMU + TOUCH_CMU_MUX_USI) return 1u << TOUCH_CMU_BIT_MUX_SEL;
	if (pa == CMU + TOUCH_CMU_DIV) return 0xfu;
	if (pa == CMU + TOUCH_CMU_GATE_IPCLK || pa == CMU + TOUCH_CMU_GATE_PCLK ||
	    pa == CMU + TOUCH_CMU_GATE_RSTN) return TP_GATE_CHECK_MASK;
	if (pa == USI + TP_USI_CON) return TP_USI_CON_RESET;
	if (pa == USI + TP_USI_OPTION) return OTI_USI_OPTION_ABL;
	if (pa == SPI + TP_SPI_CH_CFG) return TP_CH_SW_RST | TP_CH_RXCH_ON | TP_CH_TXCH_ON;
	if (pa == SPI + TP_SPI_CS_REG) return 1u;
	if (pa == SPI + TP_SPI_PACKET_CNT) return TP_PKT_CNT_EN | 0xffffu;
	if (pa == SPI + TP_SPI_FB_CLK) return 3u;
	if (pa == SPI + TP_SPI_TX_DATA) return 0xffffffffu;
	return 0;
}

__attribute__((noinline)) static int guarded_write(uintptr_t pa, uint32_t old, uint32_t val, uint32_t mask)
{
	uint32_t allowed = allowed_mask(pa);
	if (!allowed || !mask || (mask & ~allowed) || ((old ^ val) & ~mask))
		return -1;
	if (pa == SPI + TP_SPI_TX_DATA && (mask != 0xffffffffu ||
	    (val != 0u && val != 0xfbu && val != 0x20u)))
		return -1;
	return try_write32(pa, val) ? 0 : -1;
}

static void init_cell(struct cell *c, uintptr_t pa, uint32_t mask)
{
	c->pa = pa; c->mask = mask; c->old = 0; c->changed = 0;
}

static int snapshot(struct cell *c)
{
	if ((c->mask & ~allowed_mask(c->pa)) || !c->mask)
		return -1;
	return rd(c->pa, &c->old);
}

static int set(struct cell *c, uint32_t bits)
{
	uint32_t now, after, want;
	if (rd(c->pa, &now)) return -1;
	want = (now & ~c->mask) | (bits & c->mask);
	if (want == now) return 0;
	c->changed = 1; /* even an uncertain write must receive a restore */
	if (guarded_write(c->pa, now, want, c->mask) || rd(c->pa, &after)) return -1;
	return (after & c->mask) == (want & c->mask) ? 0 : -1;
}

static int restore(struct cell *c)
{
	uint32_t now, after, want;
	if (!c->changed) return 0;
	if (rd(c->pa, &now)) return -1;
	want = (now & ~c->mask) | (c->old & c->mask);
	if (guarded_write(c->pa, now, want, c->mask) || rd(c->pa, &after)) return -1;
	if ((after & c->mask) != (c->old & c->mask)) return -1;
	c->changed = 0;
	return 0;
}

static int bounded_delay(unsigned usec)
{
	uint64_t f = counter_freq(), start, delta;
	unsigned n;
	if (!f || f > 1000000000ull) return -1;
	start = touch_ticks();
	delta = f * usec / 1000000u;
	for (n = 0; n < POLL_MAX; n++)
		if (touch_ticks() - start >= delta) return 0;
	return -1;
}

static int wait_idle(uintptr_t pa)
{
	uint64_t f = counter_freq(), start = touch_ticks();
	unsigned n;
	uint32_t v;
	if (!f) return -1;
	for (n = 0; n < POLL_MAX; n++) {
		if (rd(pa, &v)) return -1;
		if (!(v & (1u << TOUCH_CMU_BIT_MUX_BUSY))) return 0;
		if ((touch_ticks() - start) * 1000000ull / f > 1000u) return -1;
	}
	return -1;
}

static int preflight(void *p)
{
	struct hw *h = p;
	struct acpm_chan ch;
	acpm_cfg_init(&h->acpm);
	h->seq = 1;
	/* Google Oriole DT overlay root compatible (gs101-oriole*.dts) and the
	 * live /memory range must both agree before any ACPM or MMIO write. */
	if (!fdt_root_compatible(h->dtb, "google,GS101 Oriole") ||
	    !fdt_memory_contains(h->dtb, h->image_base, h->image_size) ||
	    !counter_freq() || h->acpm.ch_id != 2 || h->acpm.rail[0].reg != 0x5cu ||
	    h->acpm.rail[1].reg != 0x5du || h->acpm.layout_verified != 1 ||
	    h->acpm.elem_unit_verified != 1)
		return -1;
	if (acpm_describe(&h->acpm, &ch)) return -1;
	return ch.rr == ch.rf && ch.sr == ch.sf ? 0 : -1;
}

static int shared_snapshot(void *p)
{
	struct hw *h = p;
	uint32_t v;
	unsigned i;
	init_cell(&h->s[S_SPI_CON], TOUCH_PIN_CLK_BANK, 0xffffu);
	init_cell(&h->s[S_SPI_DAT], TOUCH_PIN_CLK_BANK + 4u, 1u << TOUCH_PIN_CS_NR);
	init_cell(&h->s[S_SPI_PUD], TOUCH_PIN_CLK_BANK + 8u, 0xffffu);
	init_cell(&h->s[S_CTRL_CON], TOUCH_PIN_RESET_BANK, 0xffu);
	init_cell(&h->s[S_CTRL_DAT], TOUCH_PIN_RESET_BANK + 4u, 0x3u);
	init_cell(&h->s[S_CTRL_PUD], TOUCH_PIN_RESET_BANK + 8u, 0xfu);
	init_cell(&h->s[S_MODE], TOUCH_USI_MODE_REG, TOUCH_USI_MODE_MASK);
	init_cell(&h->s[S_TOP_GATE], TOP + TOUCH_CMUTOP_GATE, 1u << TOUCH_CMUTOP_GATE_BIT);
	init_cell(&h->s[S_MUX], CMU + TOUCH_CMU_MUX_USI, 1u << TOUCH_CMU_BIT_MUX_SEL);
	init_cell(&h->s[S_DIV], CMU + TOUCH_CMU_DIV, 0xfu);
	init_cell(&h->s[S_IPCLK], CMU + TOUCH_CMU_GATE_IPCLK, TP_GATE_CHECK_MASK);
	init_cell(&h->s[S_PCLK], CMU + TOUCH_CMU_GATE_PCLK, TP_GATE_CHECK_MASK);
	init_cell(&h->s[S_RSTN], CMU + TOUCH_CMU_GATE_RSTN, TP_GATE_CHECK_MASK);
	for (i = 0; i < S_COUNT; i++) if (snapshot(&h->s[i])) return -1;
	/* [observed hardware] Exact touched fields at the known ABL handoff.
	 * An unexpected already-configured bus is not safe to take over. */
	if ((h->s[S_SPI_CON].old & 0xffffu) || (h->s[S_CTRL_CON].old & 0xffu) ||
	    (h->s[S_MODE].old & TOUCH_USI_MODE_MASK) ||
	    (h->s[S_SPI_PUD].old & 0xffffu) != 0x1111u ||
	    (h->s[S_CTRL_PUD].old & 0xfu) != 1u ||
	    (h->s[S_MUX].old & (1u << TOUCH_CMU_BIT_MUX_SEL)) == 0 ||
	    (h->s[S_DIV].old & 0xfu) != 0 ||
	    (h->s[S_CTRL_DAT].old & 0x3u) != 0)
		return -1;
	v = h->s[S_SPI_DAT].old & (1u << TOUCH_PIN_CS_NR);
	return v == 0 ? 0 : -1;
}

static int rail_read(void *p, uint32_t reg, uint32_t *v)
{
	struct hw *h = p;
	struct acpm_trace t;
	int rc;
	if (reg != 0x5cu && reg != 0x5du) return -1;
	t.seq = h->seq;
	rc = acpm_pmic_read(&h->acpm, reg, v, &t);
	h->seq = t.seq;
	if (!rc) con_hex2("ORIOLE TOUCH RAIL", "reg", reg, "value", *v);
	return rc;
}

static int rail_set(void *p, uint32_t reg, int on, int *published)
{
	struct hw *h = p;
	struct acpm_trace t;
	int rc;
	if ((reg != 0x5cu && reg != 0x5du) || (on != 0 && on != 1)) return -1;
	t.seq = h->seq;
	rc = acpm_oriole_touch_rail_set(&h->acpm, reg, on, &t);
	h->seq = t.seq;
	*published = !!t.b.published;
	return !on && rc == ACPM_E_ON ? 0 : rc;
}

static int mode_set(void *p)
{
	struct hw *h = p;
	uint32_t g;
	if (set(&h->s[S_CTRL_DAT], 0) || /* AP/AOC mux DAT low first */
	    set(&h->s[S_CTRL_CON], 1u << (TOUCH_PIN_MUX_NR * 4u)) ||
	    set(&h->s[S_TOP_GATE], 1u << TOUCH_CMUTOP_GATE_BIT) ||
	    set(&h->s[S_MUX], 0) || wait_idle(h->s[S_MUX].pa) ||
	    set(&h->s[S_DIV], 5u) || wait_idle(h->s[S_DIV].pa)) return -1;
	g = tp_gate_open(h->s[S_IPCLK].old);
	if (set(&h->s[S_IPCLK], g) ||
	    set(&h->s[S_PCLK], tp_gate_open(h->s[S_PCLK].old)) ||
	    set(&h->s[S_RSTN], tp_gate_open(h->s[S_RSTN].old)) ||
	    set(&h->s[S_MODE], TOUCH_USI_MODE_SPI)) return -1;
	return 0; /* set() already checked the mode-2 readback */
}

static int engine_snapshot(void *p)
{
	struct hw *h = p;
	unsigned i;
	uint32_t mode, v;
	int bad = 0;
	if (rd(TOUCH_USI_MODE_REG, &mode) ||
	    (mode & TOUCH_USI_MODE_MASK) != TOUCH_USI_MODE_SPI) return -1;
	init_cell(&h->e[E_USI_CON], USI + TP_USI_CON, TP_USI_CON_RESET);
	init_cell(&h->e[E_USI_OPTION], USI + TP_USI_OPTION, OTI_USI_OPTION_ABL);
	init_cell(&h->e[E_CH], SPI + TP_SPI_CH_CFG, TP_CH_SW_RST | TP_CH_RXCH_ON | TP_CH_TXCH_ON);
	init_cell(&h->e[E_CS], SPI + TP_SPI_CS_REG, 1u);
	init_cell(&h->e[E_PKT], SPI + TP_SPI_PACKET_CNT, TP_PKT_CNT_EN | 0xffffu);
	init_cell(&h->e[E_FB], SPI + TP_SPI_FB_CLK, 3u);
	for (i = 0; i < E_COUNT; i++) if (snapshot(&h->e[i])) return -1;
	/* Fail closed on a live or non-default engine.  There is no defensible
	 * way to restore unknown out-of-mask bits after USI reset. */
	/* This Oriole arrived with USI_OPTION bit 0 and USI_CON reset bit 0
	 * set (physical 2026-10-26 captures).  ABL sets both, then releases
	 * USI_CON reset; Linux also releases an asserted reset at probe.  Log
	 * every captured word before rejecting another unfamiliar default. */
	for (i = 0; i < E_COUNT; i++) {
		v = h->e[i].old;
		con_hex2("ORIOLE TOUCH ENGINE", "pa", h->e[i].pa, "value", v);
		if (v != ((i == E_CS || i == E_USI_OPTION || i == E_USI_CON) ? 1u : 0u)) bad = 1;
	}
	for (i = 0; i < sizeof(quiet_offsets) / sizeof(quiet_offsets[0]); i++) {
		if (rd(SPI + quiet_offsets[i], &v)) return -1;
		con_hex2("ORIOLE TOUCH ENGINE", "pa", SPI + quiet_offsets[i], "value", v);
		if (v != 0) bad = 1;
	}
	if (bad) con_str("ORIOLE TOUCH ENGINE", "REFUSED non-default snapshot");
	return bad ? -1 : 0;
}

static int engine_quiet(void)
{
	uint32_t v;
	unsigned i;
	for (i = 0; i < sizeof(quiet_offsets) / sizeof(quiet_offsets[0]); i++)
		if (rd(SPI + quiet_offsets[i], &v) || v != 0) return -1;
	return 0;
}

static int spi_prepare(void *p)
{
	struct hw *h = p;
	unsigned i;
	uint32_t func = 1u << (TOUCH_PIN_CS_NR * 4u) |
	                TOUCH_SPI_FUNC << (TOUCH_PIN_CLK_NR * 4u) |
	                TOUCH_SPI_FUNC << (TOUCH_PIN_MOSI_NR * 4u) |
	                TOUCH_SPI_FUNC << (TOUCH_PIN_MISO_NR * 4u);
	/* The USI reset can change cells without going through set().  Mark every
	 * captured engine cell for cleanup before issuing any reset write. */
	for (i = 0; i < E_COUNT; i++) h->e[i].changed = 1;
	if (set(&h->s[S_SPI_DAT], 1u << TOUCH_PIN_CS_NR) ||
	    set(&h->s[S_SPI_PUD], 0) ||
	    set(&h->s[S_CTRL_PUD], 0) ||
	    set(&h->s[S_SPI_CON], func) ||
	    set(&h->e[E_USI_CON], TP_USI_CON_RESET) ||
	    engine_quiet() ||
	    set(&h->e[E_USI_OPTION], OTI_USI_OPTION_ABL) ||
	    set(&h->e[E_FB], 1u) ||
	    set(&h->e[E_USI_CON], 0) ||
	    engine_quiet() ||
	    set(&h->e[E_CH], 0) ||
	    set(&h->e[E_PKT], 0) ||
	    set(&h->e[E_CS], 1u) ||
	    set(&h->s[S_CTRL_DAT], 0) ||
	    set(&h->s[S_CTRL_CON],
	        (1u << (TOUCH_PIN_RESET_NR * 4u)) |
	        (1u << (TOUCH_PIN_MUX_NR * 4u))) ||
	    bounded_delay(10000u) ||
	    set(&h->s[S_CTRL_DAT], 1u << TOUCH_PIN_RESET_NR) ||
	    bounded_delay(100000u)) return -1;
	return 0;
}

static int tx(uint32_t byte)
{
	return guarded_write(SPI + TP_SPI_TX_DATA, 0, byte, 0xffffffffu);
}

/* One ABL-style 5-byte burst.  The second burst clocks a dummy byte and four
 * ID bytes while GPIO CS stays low.  No DMA, no address scan, no retries. */
static int burst(struct hw *h, const uint8_t txbuf[5], uint8_t rxbuf[5])
{
	uint64_t f = counter_freq(), start;
	uint32_t status, data;
	unsigned i, polls;
	int failed = 0;
	if (set(&h->e[E_CH], 0) || set(&h->e[E_PKT], 5u | TP_PKT_CNT_EN)) return -1;
	for (i = 0; i < 5; i++) if (tx(txbuf ? txbuf[i] : 0u)) return -1;
	if (set(&h->e[E_CH], TP_CH_RXCH_ON | TP_CH_TXCH_ON)) return -1;
	start = touch_ticks();
	for (polls = 0; polls < POLL_MAX; polls++) {
		if (rd(SPI + TP_SPI_STATUS, &status)) { failed = 1; break; }
		if (TP_ST_RX_LVL(status) >= 5u) break;
		if ((touch_ticks() - start) * 1000000ull / f > TP_BURST_TIMEOUT_US) { failed = 1; break; }
	}
	if (polls == POLL_MAX) failed = 1;
	if (!failed) {
		for (i = 0; i < 5; i++) {
			if (rd(SPI + TP_SPI_RX_DATA, &data)) { failed = 1; break; }
			if (rxbuf) rxbuf[i] = (uint8_t)data;
		}
		start = touch_ticks();
		for (polls = 0; polls < POLL_MAX; polls++) {
			if (rd(SPI + TP_SPI_STATUS, &status)) { failed = 1; break; }
			if (TP_ST_TX_LVL(status) == 0) break;
			if ((touch_ticks() - start) * 1000000ull / f > 1000u) { failed = 1; break; }
		}
		if (polls == POLL_MAX) failed = 1;
	}
	if (set(&h->e[E_CH], 0) || set(&h->e[E_PKT], 0)) failed = 1;
	/* ABL clears its FIFO with SW_RST after each burst, including the first
	 * five-byte command; the second burst runs under the same GPIO CS. */
	if (set(&h->e[E_CH], TP_CH_SW_RST)) failed = 1;
	start = touch_ticks();
	for (polls = 0; polls < POLL_MAX; polls++) {
		if (rd(SPI + TP_SPI_STATUS, &status)) { failed = 1; break; }
		if (TP_ST_RX_LVL(status) == 0) break;
		if (rd(SPI + TP_SPI_RX_DATA, &data)) { failed = 1; break; }
		if ((touch_ticks() - start) * 1000000ull / f > 1000u) { failed = 1; break; }
	}
	if (polls == POLL_MAX) failed = 1;
	return failed ? -1 : 0;
}

static int spi_identify(void *p, uint8_t id[4])
{
	struct hw *h = p;
	const uint8_t cmd[5] = { 0xfbu, 0x20u, 0, 0, 0 };
	uint8_t reply[5];
	int bad = 0;
	if (set(&h->s[S_SPI_DAT], 0) || set(&h->e[E_CS], 0) || bounded_delay(1u))
		bad = 1;
	if (!bad && burst(h, cmd, 0)) bad = 1;
	if (!bad && burst(h, 0, reply)) bad = 1;
	if (!bad) {
		id[0] = reply[1]; id[1] = reply[2];
		id[2] = reply[3]; id[3] = reply[4];
	}
	if (bounded_delay(TP_FTM5_SPI_DELAY_CS_US)) bad = 1;
	if (set(&h->s[S_SPI_DAT], 1u << TOUCH_PIN_CS_NR)) bad = 1;
	if (set(&h->e[E_CS], 1u)) bad = 1;
	return bad ? -1 : 0;
}

static int engine_restore(void *p)
{
	struct hw *h = p;
	unsigned i;
	uint32_t v;
	int bad = 0;
	/* Attempt all restores even if disabling channels or the FIFO reset
	 * fails.  TX_DATA has no readable snapshot; SW_RST drains it. */
	if (set(&h->e[E_CH], 0)) bad = 1;
	if (set(&h->e[E_PKT], 0)) bad = 1;
	if (set(&h->e[E_CS], 1u)) bad = 1;
	if (set(&h->e[E_CH], TP_CH_SW_RST)) bad = 1;
	if (set(&h->e[E_CH], 0)) bad = 1;
	/* The captured USI_CON had RESET=1.  Reasserting it can clear other
	 * engine registers (host fault model).  Restore it before other engine
	 * words, then verify them all.  ABL writes OPTION and FB_CLK while
	 * USI_CON reset is asserted; any ignored restore must fail readback. */
	if (restore(&h->e[E_USI_CON])) bad = 1;
	for (i = E_COUNT; i > 1; i--) if (restore(&h->e[i - 1])) bad = 1;
	for (i = 0; i < E_COUNT; i++)
		if (rd(h->e[i].pa, &v) || v != h->e[i].old) bad = 1;
	if (engine_quiet()) bad = 1;
	return bad ? -1 : 0;
}

static int mode_restore(void *p)
{
	struct hw *h = p;
	return restore(&h->s[S_MODE]);
}

static int shared_restore(void *p)
{
	struct hw *h = p;
	unsigned i;
	int bad = 0;
	for (i = S_COUNT; i > 0; i--)
		if (restore(&h->s[i - 1])) bad = 1;
	return bad ? -1 : 0;
}

int oriole_touch_id_run(uintptr_t dtb, uint64_t image_base, uint64_t image_size)
{
	struct hw h;
	struct oti_result r;
	struct oti_ops ops;
	int rc;
	h.dtb = dtb;
	h.image_base = image_base;
	h.image_size = image_size;
	/* Build this table on the stack: the freestanding image forbids ABS64
	 * relocations from a static function-pointer initializer. */
	ops.preflight = preflight;
	ops.shared_snapshot = shared_snapshot;
	ops.rail_read = rail_read;
	ops.rail_set = rail_set;
	ops.mode_set = mode_set;
	ops.engine_snapshot = engine_snapshot;
	ops.spi_prepare = spi_prepare;
	ops.spi_identify = spi_identify;
	ops.engine_restore = engine_restore;
	ops.mode_restore = mode_restore;
	ops.shared_restore = shared_restore;
	rc = oti_run(&ops, &h, &r);
	con_hex2("ORIOLE TOUCH ID", "first", r.first_error, "cleanup", r.cleanup_error);
	con_hex2("ORIOLE TOUCH ID", "id0", r.id[0], "id1", r.id[1]);
	con_hex2("ORIOLE TOUCH ID", "attempts", r.attempts,
	         "restored", r.rail25_restored + r.rail26_restored);
	con_str("ORIOLE TOUCH ID", rc ? "FAILED" : "PASS 36 48 AND RESTORED");
	return rc;
}
