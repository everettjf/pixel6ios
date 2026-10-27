#include "orioletouchid_flow.h"

/* These are the only two S2MPG10 registers accepted by the existing Oriole
 * ACPM client.  Off and on values were measured on this Pixel 6; the hardware
 * backend must still enforce the live FDT/voltage-code gates. */
#define OTI_LDO25M 0x5cu
#define OTI_LDO26M 0x5du
#define OTI_OFF25  0x2cu
#define OTI_OFF26  0x3cu
#define OTI_ON25   0xacu
#define OTI_ON26   0xbcu

static void error_once(struct oti_result *r, enum oti_stage stage)
{
	if (r->first_error == OTI_OK)
		r->first_error = stage;
}

static void cleanup_once(struct oti_result *r, enum oti_stage stage)
{
	if (r->cleanup_error == OTI_OK)
		r->cleanup_error = stage;
}

static int read_equals(const struct oti_ops *o, void *ctx, uint32_t reg, uint32_t want)
{
	uint32_t got = 0;
	return o->rail_read(ctx, reg, &got) == 0 && got == want;
}

int oti_run(const struct oti_ops *o, void *ctx, struct oti_result *r)
{
	int shared = 0, mode = 0, engine = 0, rail25 = 0, rail26 = 0;
	int published = 0, rc;
	unsigned i;

	if (!r)
		return -1;
	r->first_error = r->cleanup_error = OTI_OK;
	r->attempts = r->rail25_restored = r->rail26_restored = 0;
	for (i = 0; i < 4; i++)
		r->id[i] = 0;
	if (!o || !o->preflight || !o->shared_snapshot || !o->rail_read || !o->rail_set ||
	    !o->mode_set || !o->engine_snapshot || !o->spi_prepare || !o->spi_identify ||
	    !o->engine_restore || !o->mode_restore || !o->shared_restore) {
		error_once(r, OTI_BAD_OPS);
		return -1;
	}
	if (o->preflight(ctx)) {
		error_once(r, OTI_PREFLIGHT);
		return -1;
	}
	if (o->shared_snapshot(ctx)) {
		error_once(r, OTI_SHARED_SNAPSHOT);
		return -1;
	}
	shared = 1;
	if (!read_equals(o, ctx, OTI_LDO25M, OTI_OFF25) ||
	    !read_equals(o, ctx, OTI_LDO26M, OTI_OFF26)) {
		error_once(r, OTI_RAIL_READ);
		goto cleanup;
	}
	published = 0;
	rc = o->rail_set(ctx, OTI_LDO25M, 1, &published);
	rail25 = !!published || rc == 0;
	if (rc || !published) {
		error_once(r, OTI_RAIL_ENABLE_25);
		goto cleanup;
	}
	if (!read_equals(o, ctx, OTI_LDO25M, OTI_ON25)) {
		error_once(r, OTI_RAIL_VERIFY);
		goto cleanup;
	}
	published = 0;
	rc = o->rail_set(ctx, OTI_LDO26M, 1, &published);
	rail26 = !!published || rc == 0;
	if (rc || !published) {
		error_once(r, OTI_RAIL_ENABLE_26);
		goto cleanup;
	}
	if (!read_equals(o, ctx, OTI_LDO26M, OTI_ON26)) {
		error_once(r, OTI_RAIL_VERIFY);
		goto cleanup;
	}
	/* Set the cleanup flag BEFORE the call: a partial mode write may succeed. */
	mode = 1;
	if (o->mode_set(ctx)) {
		error_once(r, OTI_MODE_SET);
		goto cleanup;
	}
	/* No SPI register read occurs before mode_set reports readback success. */
	if (o->engine_snapshot(ctx)) {
		error_once(r, OTI_ENGINE_SNAPSHOT);
		goto cleanup;
	}
	engine = 1;
	if (o->spi_prepare(ctx)) {
		error_once(r, OTI_SPI_PREPARE);
		goto cleanup;
	}
	r->attempts = 1;
	if (o->spi_identify(ctx, r->id)) {
		error_once(r, OTI_SPI_IDENTIFY);
		goto cleanup;
	}
	if (!((r->id[0] == 0x36u && r->id[1] == 0x48u) ||
	      (r->id[0] == 0x48u && r->id[1] == 0x36u)))
		error_once(r, OTI_ID_MISMATCH);

cleanup:
	/* Every restore is independent.  A sticky read/write fault must never
	 * suppress a later attempt, especially the second PMIC rail. */
	if (engine && o->engine_restore(ctx))
		cleanup_once(r, OTI_ENGINE_RESTORE);
	if (mode && o->mode_restore(ctx))
		cleanup_once(r, OTI_MODE_RESTORE);
	if (shared && o->shared_restore(ctx))
		cleanup_once(r, OTI_SHARED_RESTORE);
	if (rail26) {
		int off;
		published = 0;
		rc = o->rail_set(ctx, OTI_LDO26M, 0, &published);
		off = read_equals(o, ctx, OTI_LDO26M, OTI_OFF26);
		if (rc || !off)
			cleanup_once(r, OTI_RAIL_RESTORE_26);
		else
			r->rail26_restored = 1;
	}
	if (rail25) {
		int off;
		published = 0;
		rc = o->rail_set(ctx, OTI_LDO25M, 0, &published);
		off = read_equals(o, ctx, OTI_LDO25M, OTI_OFF25);
		if (rc || !off)
			cleanup_once(r, OTI_RAIL_RESTORE_25);
		else
			r->rail25_restored = 1;
	}
	return r->first_error == OTI_OK && r->cleanup_error == OTI_OK &&
	       r->attempts == 1 && r->rail25_restored && r->rail26_restored ? 0 : -1;
}
