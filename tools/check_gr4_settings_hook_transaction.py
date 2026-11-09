#!/usr/bin/env python3
"""Fault-check all ten menu detour words with the compiled recovery transaction.

Host memory/guard/cache models only. No USB or firmware writes.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from build_gr4_settings_hooks import SITES,ROOT


def check(out,patch):
    words=patch['hook_words'];addresses=[int(w['address'],16) for w in words]
    expected=[address+offset for name,address,original in SITES for offset in (0,4)]
    if addresses!=expected:raise ValueError('unexpected menu detour words')
    for index,(name,address,original) in enumerate(SITES):
        if patch['sites'][index]['original_hex']!=original:raise ValueError('original changed')
    sites=',\n'.join('{%su,%su,%su}'%(w['address'],w['original'],w['replacement']) for w in words)
    originals=','.join(w['original']+'u' for w in words)
    replacements=','.join(w['replacement']+'u' for w in words)
    source=r'''
#include "xpan_hook_txn.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define N 10u
static const struct gr4_xpan_hook_site sites[N]={SITES};
static const unsigned int original[N]={ORIGINAL};
static const unsigned int patched[N]={PATCHED};
struct model { unsigned int words[N],writes,publishes,enters,leaves,held;
               unsigned int fail_write,fail_restore,fail_publish; };
static int indexof(unsigned int a) {
    for(unsigned int i=0;i<N;++i)if(a==sites[i].address)return (int)i;
    return -1;
}
static int enter(void *p) { struct model *m=p;assert(!m->held);m->held=1;++m->enters;return 1; }
static void leave(void *p) { struct model *m=p;
    assert(m->held && ((!memcmp(m->words,original,sizeof original)) ||
                       (!memcmp(m->words,patched,sizeof patched))));
    m->held=0;++m->leaves;
}
static int read_word(void *p,unsigned int a,unsigned int *v) {
    struct model *m=p;int i=indexof(a);assert(m->held);
    if(i<0)return 0;*v=m->words[i];return 1;
}
static int write_word(void *p,unsigned int a,unsigned int v) {
    struct model *m=p;int i=indexof(a);assert(m->held && i>=0);
    assert(v==original[i] || v==patched[i]);++m->writes;
    if(m->writes==m->fail_restore)return 0;
    m->words[i]=v;return m->writes!=m->fail_write;
}
static int publish(void *p) { struct model *m=p;assert(m->held);++m->publishes;return m->publishes!=m->fail_publish; }
static void seed(struct model *m,struct gr4_xpan_hook_txn *t) {
    memset(m,0,sizeof *m);memset(t,0,sizeof *t);memcpy(m->words,original,sizeof original);
}
int main(void) {
    const struct gr4_xpan_hook_io io={enter,leave,read_word,write_word,publish};
    struct model m;struct gr4_xpan_hook_txn t;unsigned int writes;
    seed(&m,&t);assert(gr4_xpan_hook_install(&t,sites,N,&io,&m));
    assert(!memcmp(m.words,patched,sizeof patched) && !m.held);
    assert(gr4_xpan_hook_remove(&t,&io,&m));assert(!memcmp(m.words,original,sizeof original));
    puts("ten-menu-words-install-remove");
    for(unsigned int i=1;i<=N;++i) {
        seed(&m,&t);m.fail_write=i;assert(!gr4_xpan_hook_install(&t,sites,N,&io,&m));
        assert(!memcmp(m.words,original,sizeof original) && !m.held && t.state==0);
        printf("committed-write-error-restores-all-words-%u\n",i);
    }
    seed(&m,&t);m.fail_publish=1;assert(!gr4_xpan_hook_install(&t,sites,N,&io,&m));
    assert(!memcmp(m.words,original,sizeof original) && !m.held && m.publishes==2);
    puts("publication-error-restores-all-before-release");
    for(unsigned int i=1;i<=N;++i) {
        seed(&m,&t);m.fail_write=i;m.fail_restore=i+1;
        assert(!gr4_xpan_hook_install(&t,sites,N,&io,&m));assert(m.held && t.state==2 && !m.leaves);
        assert(gr4_xpan_hook_recover_original(&t,&io,&m));
        assert(!memcmp(m.words,original,sizeof original) && !m.held && m.enters==1 && m.leaves==1);
        printf("partial-patch-holds-guard-until-recovery-%u\n",i);
    }
    for(unsigned int i=0;i<N;++i) {
        seed(&m,&t);assert(gr4_xpan_hook_install(&t,sites,N,&io,&m));
        m.words[i]=0xDEADBEEFu;writes=m.writes;
        assert(!gr4_xpan_hook_remove(&t,&io,&m));assert(m.held && m.writes==writes);
        assert(!gr4_xpan_hook_recover_original(&t,&io,&m));assert(m.words[i]==0xDEADBEEFu && m.held);
        m.words[i]=patched[i];assert(gr4_xpan_hook_recover_original(&t,&io,&m));
        assert(!memcmp(m.words,original,sizeof original) && !m.held);
        printf("unknown-word-preserved-and-callers-stopped-%u\n",i);
    }
    return 0;
}
'''.replace('SITES',sites).replace('ORIGINAL',originals).replace('PATCHED',replacements)
    src=out/'menu-transaction-model.c';binary=out/'menu-transaction-model'
    src.write_text(source)
    subprocess.run([shutil.which('clang'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
        '-I',str(ROOT/'firmware'),str(src),str(ROOT/'firmware/xpan_hook_txn.c'),'-o',str(binary)],check=True)
    result=subprocess.run([str(binary)],capture_output=True,text=True,check=True)
    cases=result.stdout.splitlines()
    assert len(cases)==32 and len(set(cases))==32
    report=dict(schema='gr4-menu-transaction-host-v1',cases_passed=len(cases),cases=cases,
        site_words=words,camera_accessed=False,pause_and_cache_are_host_models=True)
    (out/'transaction-checks.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);a=p.parse_args()
    if (a.package/'transaction-checks.json').exists():raise ValueError('immutable result exists')
    result=check(a.package,json.loads((a.package/'patch.json').read_text()))
    print('Ten-word menu recovery checks passed:',result['cases_passed'])
