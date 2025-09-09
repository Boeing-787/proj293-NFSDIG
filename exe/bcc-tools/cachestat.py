#!/usr/bin/env python3
#
# cachestat     Count cache kernel function calls.
#               For Linux, uses BCC, eBPF. See .c file.
#
# USAGE: cachestat
# Taken from funccount by Brendan Gregg
# This is a rewrite of cachestat from perf to bcc
# https://github.com/brendangregg/perf-tools/blob/master/fs/cachestat
#
# Copyright (c) 2016 Allan McAleavy.
# Copyright (c) 2015 Brendan Gregg.
# Licensed under the Apache License, Version 2.0 (the "License")
#
# 09-Sep-2015   Brendan Gregg   Created this.
# 06-Nov-2015   Allan McAleavy
# 13-Jan-2016   Allan McAleavy  run pep8 against program
# 02-Feb-2019   Brendan Gregg   Column shuffle, bring back %ratio
# 15-Feb-2023   Rong Tao        Add writeback_dirty_{folio,page} tracepoints
# 17-Nov-2024   Rocky Xing      Added filemap_add_folio/folio_mark_accessed kprobes

from __future__ import print_function
from bcc import BPF
from time import sleep, strftime
import argparse
import signal
import re
from sys import argv
import os
import sys

# signal handler
def signal_ignore(signal, frame):
    print()

# Function to gather data from /proc/meminfo
# return dictionary for quicker lookup of both values
def get_meminfo():
    result = dict()

    for line in open('/proc/meminfo'):
        k = line.split(':', 3)
        v = k[1].split()
        result[k[0]] = int(v[0])
    return result

# set global variables
mpa = 0
mbd = 0
apcl = 0
apd = 0
total = 0
misses = 0
hits = 0
debug = 0

# arguments
parser = argparse.ArgumentParser(
    description="Count cache kernel function calls",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-T", "--timestamp", action="store_true",
    help="include timestamp on output")
parser.add_argument("interval", nargs="?", default=1,
    help="output interval, in seconds")
parser.add_argument("count", nargs="?", default=-1,
    help="number of outputs")
parser.add_argument("--ebpf", action="store_true",
    help=argparse.SUPPRESS)
parser.add_argument("--pid", type=int, default=0,
    help="filter by pid")
parser.add_argument("--output", type=str, default="../traceOutput/cachestat.csv",
    help="output file")
args = parser.parse_args()
count = int(args.count)
tstamp = args.timestamp
interval = int(args.interval)
filter_pid = args.pid
output_file = args.output
# define BPF program
bpf_text = """
#include <uapi/linux/ptrace.h>
// 定义默认值（可选）
#ifndef FILTER_PID
#define FILTER_PID 0
#endif
struct key_t {
    // NF_{APCL,MPA,MBD,APD}
    u32 nf;
};



enum {
    NF_APCL,
    NF_MPA,
    NF_MBD,
    NF_APD,
};

BPF_HASH(counts, struct key_t);

static int __do_count(void *ctx, u32 nf) {
    struct key_t key = {};
    u64 ip;

    key.nf = nf;
    counts.atomic_increment(key); // update counter
    return 0;
}

static int filter(u32 pid) {
    if (FILTER_PID && pid != FILTER_PID) {
        return 1;
    }
    return 0;
}

int do_count_apcl(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (filter(pid)) {
        return 0;
    }
    return __do_count(ctx, NF_APCL);
}

int do_count_mpa(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (filter(pid)) {
        return 0;
    }
    return __do_count(ctx, NF_MPA);
}
int do_count_mbd(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (filter(pid)) {
        return 0;
    }
    return __do_count(ctx, NF_MBD);
}
int do_count_apd(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (filter(pid)) {
        return 0;
    }
    return __do_count(ctx, NF_APD);
}
int do_count_apd_tp(void *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (filter(pid)) {
        return 0;
    }
    return __do_count(ctx, NF_APD);
}
"""

if debug or args.ebpf:
    print(bpf_text)
    if args.ebpf:
        exit()

# 在加载BPF程序时，可以通过BPF的C预处理器宏定义功能，动态传递filter_pid的值。

b = BPF(text=bpf_text, cflags=["-Dfilter_pid=%d" % filter_pid])
if BPF.get_kprobe_functions(b'filemap_add_folio'):
    b.attach_kprobe(event="filemap_add_folio", fn_name="do_count_apcl")
else:
    b.attach_kprobe(event="add_to_page_cache_lru", fn_name="do_count_apcl")
if BPF.get_kprobe_functions(b'folio_mark_accessed'):
    b.attach_kprobe(event="folio_mark_accessed", fn_name="do_count_mpa")
else:
    b.attach_kprobe(event="mark_page_accessed", fn_name="do_count_mpa")

# Function account_page_dirtied() is changed to folio_account_dirtied() in 5.15.
# Both folio_account_dirtied() and account_page_dirtied() are
# static functions and they may be gone during compilation and this may
# introduce some inaccuracy, use tracepoint writeback_dirty_{page,folio},
# instead when attaching kprobe fails, and report the running
# error in time.
if BPF.get_kprobe_functions(b'folio_account_dirtied'):
    b.attach_kprobe(event="folio_account_dirtied", fn_name="do_count_apd")
elif BPF.get_kprobe_functions(b'account_page_dirtied'):
    b.attach_kprobe(event="account_page_dirtied", fn_name="do_count_apd")
elif BPF.tracepoint_exists("writeback", "writeback_dirty_folio"):
    b.attach_tracepoint(tp="writeback:writeback_dirty_folio", fn_name="do_count_apd_tp")
elif BPF.tracepoint_exists("writeback", "writeback_dirty_page"):
    b.attach_tracepoint(tp="writeback:writeback_dirty_page", fn_name="do_count_apd_tp")
else:
    raise Exception("Failed to attach kprobe %s or %s or any tracepoint" %
                    ("folio_account_dirtied", "account_page_dirtied"))
b.attach_kprobe(event="mark_buffer_dirty", fn_name="do_count_mbd")

# check whether hash table batch ops is supported
htab_batch_ops = True if BPF.kernel_struct_has_field(b'bpf_map_ops',
        b'map_lookup_and_delete_batch') == 1 else False

f = sys.stdout
if output_file:
    # 检查 output_file 是否存在，如果不存在则创建

    if not os.path.exists(output_file):
        # 如果父目录不存在，也一并创建
        parent_dir = os.path.dirname(output_file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir)
        open(output_file, "a").close()
    f = open(output_file, "w")
# header
if tstamp:
    f.write("%-8s " % "TIME,")
f.write("%8s %8s %8s %8s %12s %10s" %
    ("HITS,", "MISSES,", "DIRTIES,", "HITRATIO,", "BUFFERS_MB,", "CACHED_MB"))
f.write("\n")

loop = 0
exiting = 0
while 1:
    if count > 0:
        loop += 1
        if loop > count:
            exit()

    try:
        sleep(interval)
    except KeyboardInterrupt:
        exiting = 1
        # as cleanup can take many seconds, trap Ctrl-C:
        signal.signal(signal.SIGINT, signal_ignore)

    counts = b["counts"]
    for k, v in sorted(counts.items_lookup_and_delete_batch()
                                if htab_batch_ops else counts.items(),
                                key=lambda counts: counts[1].value):
        # partial string matches in case of .isra (necessary?)
        if k.nf == 0: # NF_APCL
            apcl = max(0, v.value)
        if k.nf == 1: # NF_MPA
            mpa = max(0, v.value)
        if k.nf == 2: # NF_MBD
            mbd = max(0, v.value)
        if k.nf == 3: # NF_APD
            apd = max(0, v.value)

    # total = total cache accesses without counting dirties
    # misses = total of add to lru because of read misses
    total = mpa - mbd
    misses = apcl - apd
    if misses < 0:
        misses = 0
    if total < 0:
        total = 0
    hits = total - misses

    # If hits are < 0, then its possible misses are overestimated
    # due to possibly page cache read ahead adding more pages than
    # needed. In this case just assume misses as total and reset hits.
    if hits < 0:
        misses = total
        hits = 0
    ratio = 0
    if total > 0:
        ratio = float(hits) / total

    if debug:
        f.write("%d %d %d %d %d %d %d\n" %
        (mpa, mbd, apcl, apd, total, misses, hits))

    if not htab_batch_ops:
        counts.clear()

    # Get memory info
    mem = get_meminfo()
    cached = int(mem["Cached"]) / 1024
    buff = int(mem["Buffers"]) / 1024

    if tstamp:
        f.write("%-8s, " % strftime("%H:%M:%S"))
    f.write("%8d,%8d,%8d,%7.2f%%,%12.0f,%10.0f\n" %
        (hits, misses, mbd, 100 * ratio, buff, cached))

    mpa = mbd = apcl = apd = total = misses = hits = cached = buff = 0

    if exiting:
        if output_file and f != sys.stdout:
            f.close()
        print("Detaching...")
        exit()
