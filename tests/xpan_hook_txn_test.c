#include "../firmware/xpan_hook_txn.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

struct mock {
    unsigned int words[2], writes, publishes, enters, leaves;
    unsigned int fail_write, fail_publish, fail_restore, fail_enter, fail_read;
};

static int enter(void *p) {
    struct mock *m=p;
    ++m->enters;
    return !m->fail_enter;
}
static void leave(void *p) { ++((struct mock *)p)->leaves; }
static void other_leave(void *p) { leave(p); }
static int read_word(void *p, unsigned int address, unsigned int *out) {
    struct mock *m=p;
    if (m->fail_read || (address != 0x1000 && address != 0x1004)) return 0;
    *out=m->words[(address-0x1000)/4];
    return 1;
}
static int write_word(void *p, unsigned int address, unsigned int value) {
    struct mock *m=p;
    unsigned int index=(address-0x1000)/4;
    if (index >= 2 || (address != 0x1000 && address != 0x1004)) return 0;
    ++m->writes;
    if (m->fail_restore && m->writes == m->fail_restore) return 0;
    m->words[index]=value;
    return m->writes != m->fail_write;
}
static int publish(void *p) {
    struct mock *m=p;
    ++m->publishes;
    return m->publishes != m->fail_publish;
}

int main(void) {
    const struct gr4_xpan_hook_site sites[2]={{0x1000,11,21},{0x1004,12,22}};
    const struct gr4_xpan_hook_site duplicate[2]={{0x1000,11,21},{0x1000,12,22}};
    const struct gr4_xpan_hook_io io={enter,leave,read_word,write_word,publish};
    struct gr4_xpan_hook_txn txn;
    struct mock m, wrong_context;
    struct gr4_xpan_hook_io wrong_io=io;
    unsigned int writes, enters, leaves;

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12;
    assert(!gr4_xpan_hook_install(&txn,duplicate,2,&io,&m));
    assert(!m.enters && !m.writes);
    puts("duplicate-sites-rejected");
    assert(gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(txn.state==1 && m.words[0]==21 && m.words[1]==22);
    assert(m.enters==1 && m.leaves==1 && m.publishes==1);
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(gr4_xpan_hook_remove(&txn,&io,&m));
    assert(txn.state==0 && m.words[0]==11 && m.words[1]==12);
    assert(!txn.guard_held && !txn.guard_context && !txn.guard_io.leave);
    puts("install-remove-publishes-and-releases");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=99;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(txn.state==0 && !m.writes && m.leaves==1);
    puts("install-preflight-mismatch-no-writes");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12; m.fail_write=2;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(txn.state==0 && m.words[0]==11 && m.words[1]==12);
    assert(m.publishes==1 && m.leaves==1);
    puts("committed-write-error-rolls-back");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12; m.fail_publish=1;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(txn.state==0 && m.words[0]==11 && m.words[1]==12);
    assert(m.publishes==2 && m.leaves==1);
    puts("publication-error-rolls-back");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12; m.fail_write=2; m.fail_restore=3;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(txn.state==2 && m.words[1]==22 && m.leaves==0);
    assert(!gr4_xpan_hook_remove(&txn,&io,&m));
    assert(txn.guard_held && txn.guard_context==&m);
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    puts("failed-rollback-retains-guard");

    memset(&wrong_context,0,sizeof wrong_context);
    writes=m.writes; enters=m.enters; leaves=m.leaves;
    wrong_io.leave=other_leave;
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&wrong_context));
    assert(!gr4_xpan_hook_recover_original(&txn,&wrong_io,&m));
    assert(m.writes==writes && m.enters==enters && m.leaves==leaves);
    assert(!wrong_context.enters && !wrong_context.writes && !wrong_context.leaves);
    puts("wrong-recovery-owner-rejected");

    /* An equivalent callback copy is accepted; recovery never enters twice. */
    wrong_io=io;
    assert(gr4_xpan_hook_recover_original(&txn,&wrong_io,&m));
    assert(txn.state==0 && !txn.guard_held && m.words[0]==11 && m.words[1]==12);
    assert(m.enters==enters && m.leaves==leaves+1);
    writes=m.writes; leaves=m.leaves;
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(m.writes==writes && m.leaves==leaves);
    puts("recovery-restores-without-reenter-or-double-release");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12; m.fail_enter=1;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    assert(txn.state==0 && !txn.guard_held && !m.writes && !m.leaves);
    puts("enter-failure-does-not-own-guard");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12;
    assert(gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    m.words[1]=99; writes=m.writes;
    assert(!gr4_xpan_hook_remove(&txn,&io,&m));
    assert(txn.state==2 && txn.guard_held && m.writes==writes && m.leaves==1);
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(m.words[0]==11 && m.words[1]==99 && m.leaves==1);
    /* Simulate independent conflict resolution; never overwrite 99 ourselves. */
    m.words[1]=22;
    assert(gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(m.words[1]==12 && m.enters==2 && m.leaves==2 && txn.state==0);
    puts("remove-conflict-keeps-callers-stopped-until-resolved");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12;
    assert(gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    m.fail_read=1; writes=m.writes;
    assert(!gr4_xpan_hook_remove(&txn,&io,&m));
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(txn.state==2 && m.writes==writes && m.leaves==1);
    m.fail_read=0;
    assert(gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(m.enters==2 && m.leaves==2);
    puts("read-failure-retains-guard-for-retry");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12; m.fail_write=2; m.fail_restore=3;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    m.fail_restore=m.writes+1;
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(txn.state==2 && m.leaves==0);
    m.fail_restore=0;
    m.fail_publish=m.publishes+1;
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(m.words[0]==11 && m.words[1]==12 && txn.state==2 && m.leaves==0);
    assert(gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(txn.state==0 && m.enters==1 && m.leaves==1);
    puts("recovery-write-and-publication-failures-retry");

    memset(&txn,0,sizeof txn); memset(&m,0,sizeof m);
    m.words[0]=11; m.words[1]=12; m.fail_write=2; m.fail_restore=3;
    assert(!gr4_xpan_hook_install(&txn,sites,2,&io,&m));
    writes=m.writes;
    txn.count=GR4_XPAN_MAX_HOOKS+1;
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    txn.count=2; txn.sites[1].address=txn.sites[0].address;
    assert(!gr4_xpan_hook_recover_original(&txn,&io,&m));
    assert(m.writes==writes && m.leaves==0 && txn.state==2);
    txn.sites[1]=sites[1];
    assert(gr4_xpan_hook_recover_original(&txn,&io,&m));
    puts("invalid-journal-rejected-before-recovery-writes");
    return 0;
}
