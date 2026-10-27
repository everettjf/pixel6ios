#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "orioletouchid_flow.h"

enum { PRE, SNAP, READ25, READ26, ON25, VERIFY25, ON26, VERIFY26,
       MODE, ENGINE, PREPARE, IDENTIFY, ERESTORE, MRESTORE, SRESTORE,
       OFF26, OFF25, CHECKOFF26, CHECKOFF25, FIFO };

struct fake {
	int fail, reads25, reads26, on25, on26, mode_ok, engine_seen;
	int erestore, mrestore, srestore, off26, off25, identify_calls, fifo_calls;
	int order[40], n;
};

static int hit(struct fake *f, int stage)
{
	assert(f->n < 40);
	f->order[f->n++] = stage;
	return f->fail == stage;
}

static int pre(void *p) { return hit(p, PRE); }
static int snap(void *p) { return hit(p, SNAP); }
static int read_rail(void *p, uint32_t reg, uint32_t *v)
{
	struct fake *f = p;
	int stage;
	assert(reg == 0x5c || reg == 0x5d);
	if (reg == 0x5c) {
		stage = f->off25 ? CHECKOFF25 : f->reads25++ ? VERIFY25 : READ25;
		*v = f->on25 ? 0xac : 0x2c;
	} else {
		stage = f->off26 ? CHECKOFF26 : f->reads26++ ? VERIFY26 : READ26;
		*v = f->on26 ? 0xbc : 0x3c;
	}
	return hit(f, stage);
}
static int set_rail(void *p, uint32_t reg, int on, int *published)
{
	struct fake *f = p;
	int stage = reg == 0x5c ? (on ? ON25 : OFF25) : (on ? ON26 : OFF26);
	assert(reg == 0x5c || reg == 0x5d);
	*published = 1;
	if (on) {
		if (reg == 0x5c) f->on25 = 1;
		else f->on26 = 1;
	} else {
		if (reg == 0x5c) { f->on25 = 0; f->off25++; }
		else { f->on26 = 0; f->off26++; }
	}
	return hit(f, stage);
}
static int mode_set(void *p)
{
	struct fake *f = p;
	f->mode_ok = 1;
	return hit(f, MODE);
}
static int engine_snapshot(void *p)
{
	struct fake *f = p;
	assert(f->mode_ok);
	f->engine_seen = 1;
	return hit(f, ENGINE);
}
static int prepare(void *p)
{
	struct fake *f = p;
	assert(f->engine_seen);
	return hit(f, PREPARE);
}
static int identify(void *p, uint8_t id[4])
{
	struct fake *f = p;
	f->identify_calls++;
	id[0] = f->fail == IDENTIFY + 100 ? 0 : 0x36;
	id[1] = 0x48;
	id[2] = id[3] = 0;
	return hit(f, IDENTIFY);
}
static int fifo_read(void *p, uint8_t event[8])
{
	struct fake *f = p;
	f->fifo_calls++;
	event[0] = 0x03;
	return hit(f, FIFO);
}
static int erestore(void *p)
{
	struct fake *f = p;
	f->erestore++;
	return hit(f, ERESTORE);
}
static int mrestore(void *p)
{
	struct fake *f = p;
	f->mrestore++;
	return hit(f, MRESTORE);
}
static int srestore(void *p)
{
	struct fake *f = p;
	f->srestore++;
	return hit(f, SRESTORE);
}
static const struct oti_ops ops = {
	.preflight = pre, .shared_snapshot = snap, .rail_read = read_rail,
	.rail_set = set_rail, .mode_set = mode_set, .engine_snapshot = engine_snapshot,
	.spi_prepare = prepare, .spi_identify = identify,
	.engine_restore = erestore, .mode_restore = mrestore,
	.shared_restore = srestore
};

static int position(struct fake *f, int stage)
{
	int i;
	for (i = 0; i < f->n; i++)
		if (f->order[i] == stage) return i;
	return -1;
}

int main(void)
{
	struct fake f;
	struct oti_result r;
	int fail, rc;
	for (fail = PRE; fail <= CHECKOFF25; fail++) {
		f = (struct fake){0};
		f.fail = fail;
		rc = oti_run(&ops, &f, &r);
		assert(rc != 0);
		assert(f.identify_calls <= 1 && r.attempts <= 1);
		assert(position(&f, ENGINE) < 0 || position(&f, MODE) >= 0);
		if (f.off25) assert(position(&f, OFF26) < position(&f, OFF25) || !f.off26);
		if (fail >= ON25 && fail <= CHECKOFF25)
			assert(f.off25 == 1);
		if (fail >= ON26 && fail <= CHECKOFF25)
			assert(f.off26 == 1);
		if (fail >= MODE && fail <= CHECKOFF25)
			assert(f.mrestore == 1);
		if (fail >= PREPARE && fail <= CHECKOFF25)
			assert(f.erestore == 1);
	}
	f = (struct fake){0};
	f.fail = -1;
	rc = oti_run(&ops, &f, &r);
	assert(rc == 0 && r.first_error == OTI_OK && r.cleanup_error == OTI_OK);
	assert(r.attempts == 1 && f.identify_calls == 1);
	assert(r.rail25_restored && r.rail26_restored);
	assert(f.off25 == 1 && f.off26 == 1 && f.erestore == 1 && f.mrestore == 1 && f.srestore == 1);
	f = (struct fake){0};
	f.fail = IDENTIFY + 100; /* a complete transfer with the wrong ID */
	assert(oti_run(&ops, &f, &r) != 0 && r.first_error == OTI_ID_MISMATCH);
	assert(f.off25 == 1 && f.off26 == 1 && r.cleanup_error == OTI_OK);
	/* The opt-in FIFO read is permitted only after a verified chip ID;
	 * its failure still runs every independent cleanup attempt. */
	{
		struct oti_ops fifo_ops = ops;
		fifo_ops.fifo_read = fifo_read;
		f = (struct fake){0}; f.fail = -1;
		assert(oti_run(&fifo_ops, &f, &r) == 0);
		assert(f.fifo_calls == 1 && r.fifo_attempts == 1 && r.event[0] == 0x03);
		assert(position(&f, IDENTIFY) < position(&f, FIFO));
		assert(position(&f, FIFO) < position(&f, ERESTORE));
		f = (struct fake){0}; f.fail = FIFO;
		assert(oti_run(&fifo_ops, &f, &r) != 0 && r.first_error == OTI_FIFO_READ);
		assert(f.fifo_calls == 1 && f.off25 == 1 && f.off26 == 1);
		assert(f.erestore == 1 && f.mrestore == 1 && f.srestore == 1);
		f = (struct fake){0}; f.fail = IDENTIFY + 100;
		assert(oti_run(&fifo_ops, &f, &r) != 0 && r.first_error == OTI_ID_MISMATCH);
		assert(f.fifo_calls == 0 && r.fifo_attempts == 0);
	}
	/* A malformed ops table must not call any hardware callback. */
	f = (struct fake){0};
	assert(oti_run(0, &f, &r) != 0 && r.first_error == OTI_BAD_OPS && f.n == 0);
	puts("oriole touch ID flow: failure injection passed");
	return 0;
}
