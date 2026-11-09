#!/usr/bin/env python3
"""Fault-check the two actual detour words with compiled transaction code.

Guard/cache callbacks are host models; never writes a camera or firmware file.
"""
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def check(out,patch):
    words=patch['hook_words']
    if len(words)!=2 or [int(w['address'],16) for w in words]!=[0x536438A0,0x536438A4]:
        raise ValueError('unexpected fixed detour sites')
    sites=',\n'.join('{%su,%su,%su}'%(w['address'],w['original'],w['replacement']) for w in words)
    originals=','.join(w['original']+'u' for w in words)
    replacements=','.join(w['replacement']+'u' for w in words)
    source=r'''
#include "xpan_hook_txn.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const struct gr4_xpan_hook_site sites[2]={SITES};
static const unsigned int original[2]={ORIGINAL};
static const unsigned int patched[2]={PATCHED};
struct model { unsigned int words[2],writes,publishes,enters,leaves,held;
               unsigned int fail_write,fail_restore,fail_publish; };
static int enter(void *p) { struct model *m=p;assert(!m->held);m->held=1;++m->enters;return 1; }
static void leave(void *p) { struct model *m=p;
    assert(m->held && ((!memcmp(m->words,original,sizeof original)) ||
                       (!memcmp(m->words,patched,sizeof patched))));
    m->held=0;++m->leaves;
}
static int read_word(void *p,unsigned int a,unsigned int *v) {
    struct model *m=p;assert(m->held);
    if(a!=sites[0].address && a!=sites[1].address)return 0;
    *v=m->words[(a-sites[0].address)/4];return 1;
}
static int write_word(void *p,unsigned int a,unsigned int v) {
    struct model *m=p;unsigned int index=(a-sites[0].address)/4;assert(m->held && index<2);
    assert(v==original[index] || v==patched[index]);++m->writes;
    if(m->writes==m->fail_restore)return 0;
    m->words[index]=v;return m->writes!=m->fail_write;
}
static int publish(void *p) { struct model *m=p;assert(m->held);++m->publishes;return m->publishes!=m->fail_publish; }
static void seed(struct model *m,struct gr4_xpan_hook_txn *t) {
    memset(m,0,sizeof *m);memset(t,0,sizeof *t);memcpy(m->words,original,sizeof original);
}
int main(void) {
    const struct gr4_xpan_hook_io io={enter,leave,read_word,write_word,publish};
    struct model m;struct gr4_xpan_hook_txn t;unsigned int writes;
    seed(&m,&t);assert(gr4_xpan_hook_install(&t,sites,2,&io,&m));
    assert(!memcmp(m.words,patched,sizeof patched) && !m.held);
    assert(gr4_xpan_hook_remove(&t,&io,&m));assert(!memcmp(m.words,original,sizeof original));
    puts("exact-detour-pair-install-remove");
    seed(&m,&t);m.fail_write=2;assert(!gr4_xpan_hook_install(&t,sites,2,&io,&m));
    assert(!memcmp(m.words,original,sizeof original) && !m.held && t.state==0);
    puts("literal-word-committed-error-restores-pair");
    seed(&m,&t);m.fail_publish=1;assert(!gr4_xpan_hook_install(&t,sites,2,&io,&m));
    assert(!memcmp(m.words,original,sizeof original) && !m.held && m.publishes==2);
    puts("publication-error-restores-pair-before-release");
    seed(&m,&t);m.fail_write=2;m.fail_restore=3;
    assert(!gr4_xpan_hook_install(&t,sites,2,&io,&m));assert(m.held && t.state==2 && !m.leaves);
    assert(gr4_xpan_hook_recover_original(&t,&io,&m));
    assert(!memcmp(m.words,original,sizeof original) && !m.held && m.enters==1 && m.leaves==1);
    puts("mixed-instruction-literal-holds-guard-until-recovery");
    seed(&m,&t);assert(gr4_xpan_hook_install(&t,sites,2,&io,&m));
    m.words[1]=0xDEADBEEFu;writes=m.writes;
    assert(!gr4_xpan_hook_remove(&t,&io,&m));assert(m.held && m.writes==writes);
    assert(!gr4_xpan_hook_recover_original(&t,&io,&m));assert(m.words[1]==0xDEADBEEFu && m.held);
    /* Model an external owner resolving its word; recovery does not write it. */
    m.words[1]=patched[1];assert(gr4_xpan_hook_recover_original(&t,&io,&m));
    assert(!memcmp(m.words,original,sizeof original) && !m.held);
    puts("unknown-literal-never-overwritten-callers-stay-stopped");
    return 0;
}
'''.replace('SITES',sites).replace('ORIGINAL',originals).replace('PATCHED',replacements)
    src=out/'detour-transaction-model.c';binary=out/'detour-transaction-model'
    src.write_text(source)
    command=[shutil.which('clang'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-I',str(ROOT/'firmware'),str(src),str(ROOT/'firmware/xpan_hook_txn.c'),'-o',str(binary)]
    subprocess.run(command,check=True)
    run=subprocess.run([str(binary)],capture_output=True,text=True,check=True)
    cases=run.stdout.splitlines()
    if len(cases)!=5 or len(set(cases))!=5:raise ValueError('incomplete detour pair recovery checks')
    result={'schema':'gr4-detour-transaction-host-v1','passed':True,'cases':cases,
            'site_words':words,'camera_access':False,'pause_and_cache_are_host_models':True}
    (out/'transaction-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
