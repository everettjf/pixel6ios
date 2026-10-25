#include "resetcheck.h"
#include "console.h"

/* No kernel entry or controller handoff: the caller always resets. Keeping
 * USB active here makes the EL3 return/readback evidence observable. */
void oriole_resetcheck(uint64_t deadline)
{
    con_str("ORIOLE_RESETCHECK", "waiting boundedly for USB configured+DTR");
    while ((int64_t)(deadline-resetcheck_ticks())>0 && !resetcheck_ready())
        resetcheck_wait_ms(1);
    if (!resetcheck_ready()) {
        con_str("RESETCHECK", "no host; no PMU writes");
        return;
    }
    uint32_t before=0, after=0;
    if (!resetcheck_read(RC_SYSIP,&before)) {
        con_str("RESETCHECK", "SYSIP read fault; no PMU writes");
        return;
    }
    con_hex("RESETCHECK SYSIP before",before);
    uint64_t ret=resetcheck_write(RC_SYSIP,0xfc);
    int read_ok=resetcheck_read(RC_SYSIP,&after);
    con_hex("RESETCHECK mode SMC ret",ret);
    con_hex("RESETCHECK readback valid",read_ok);
    con_hex("RESETCHECK SYSIP after",after);
    int accepted=ret==0 && read_ok && after==0xfc;
    con_str("RESETCHECK",accepted ? "mode accepted; drain before SWRESET" :
                                   "mode refused; no SWRESET");
    /* Existing eight-second final-log drain, serviced by the console hook.
     * Any USB fault/disconnect during it also closes the SWRESET gate. */
    resetcheck_wait_ms(8000);
    if (!accepted || !resetcheck_ready()) return;
    ret=resetcheck_write(RC_SWRESET,2);
    con_hex("RESETCHECK SWRESET returned",ret);
    resetcheck_wait_ms(8000);
}
