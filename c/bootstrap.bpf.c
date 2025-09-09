// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
/* Copyright (c) 2020 Facebook */
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "bootstrap.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, 8192);
	__type(key, pid_t);
	__type(value, u64);
} exec_start SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 256 * 1024);
} rb SEC(".maps");

/* 可修改的变量，放在 .bss 段中 */
int my_pid = 0;
unsigned long long dev = 0;
unsigned long long ino = 0;
const volatile unsigned long long min_duration_ns = 0;


/* 检查当前进程是否应该被跟踪，并返回进程 PID */
static inline pid_t should_trace_process(void)
{
	struct bpf_pidns_info ns;
	pid_t pid;
	
	/* 如果 dev 和 ino 为 0，表示不进行命名空间过滤 */
	if (dev == 0 && ino == 0) {
		/* 获取当前进程的 PID */
		pid = bpf_get_current_pid_tgid() >> 32;
	} else {
		/* 获取当前进程在指定命名空间中的信息 */
		if (bpf_get_ns_current_pid_tgid(dev, ino, &ns, sizeof(ns)) != 0)
			return 0; /* 命名空间检查失败，返回 0 */
		pid = ns.pid;
	}
	
	/* 如果 my_pid 为 0，表示跟踪所有进程 */
	if (my_pid == 0)
		return pid;
	
	/* 检查是否匹配指定的 PID */
	if (pid == my_pid)
		return pid;
	
	/* 不匹配指定的 PID，返回 0 */
	return 0;
}

SEC("tp/sched/sched_process_exec")
int handle_exec(struct trace_event_raw_sched_process_exec *ctx)
{
	struct task_struct *task;
	unsigned fname_off;
	struct event *e;
	pid_t pid;
	u64 ts;

	/* remember time exec() was executed for this PID */
	//pid = bpf_get_current_pid_tgid() >> 32;
	/* 检查进程过滤（包含命名空间过滤），并获取 PID */
	pid = should_trace_process();
	if (my_pid && pid != my_pid)
		return 0;
	ts = bpf_ktime_get_ns();
	bpf_map_update_elem(&exec_start, &pid, &ts, BPF_ANY);

	// /* don't emit exec events when minimum duration is specified */
	// if (min_duration_ns)
	// 	return 0;

	// /* reserve sample from BPF ringbuf */
	// e = bpf_ringbuf_reserve(&rb, sizeof(*e), 0);
	// if (!e)
	// 	return 0;

	// /* fill out the sample with data */
	// task = (struct task_struct *)bpf_get_current_task();

	// e->exit_event = false;
	// e->pid = pid;
	// e->ppid = BPF_CORE_READ(task, real_parent, tgid);
	// bpf_get_current_comm(&e->comm, sizeof(e->comm));

	// fname_off = ctx->__data_loc_filename & 0xFFFF;
	// bpf_probe_read_str(&e->filename, sizeof(e->filename), (void *)ctx + fname_off);

	// /* successfully submit it to user-space for post-processing */
	// bpf_ringbuf_submit(e, 0);
	return 0;
}

SEC("tp/sched/sched_process_exit")
int handle_exit(struct trace_event_raw_sched_process_template *ctx)
{
	struct task_struct *task;
	struct event *e;
	pid_t pid, tid;
	u64 id, ts, *start_ts, duration_ns = 0;

	/* get PID and TID of exiting thread/process */
	// id = should_trace_process();
	id = bpf_get_current_pid_tgid();
	pid = id >> 32;
	tid = (u32)id;

	/* ignore thread exits */
	if (pid != tid)
		return 0;

	/* if we recorded start of the process, calculate lifetime duration */
	start_ts = bpf_map_lookup_elem(&exec_start, &pid);
	if (start_ts)
		duration_ns = bpf_ktime_get_ns() - *start_ts;
	else 
		return 0;
	bpf_map_delete_elem(&exec_start, &pid);

	/* if process didn't live long enough, return early */
	if (min_duration_ns && duration_ns < min_duration_ns)
		return 0;

	/* reserve sample from BPF ringbuf */
	e = bpf_ringbuf_reserve(&rb, sizeof(*e), 0);
	if (!e)
		return 0;

	/* fill out the sample with data */
	task = (struct task_struct *)bpf_get_current_task();

	// e->exit_event = true;
	e->duration_ns = duration_ns;
	e->pid = pid;
	e->ppid = BPF_CORE_READ(task, real_parent, tgid);
	e->exit_code = (BPF_CORE_READ(task, exit_code) >> 8) & 0xff;
	bpf_get_current_comm(&e->comm, sizeof(e->comm));

	/* send data to user-space for post-processing */
	bpf_ringbuf_submit(e, 0);
	return 0;
}
