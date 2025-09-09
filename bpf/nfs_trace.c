// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2021 Wenbo Zhang
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_endian.h>
#include "nfs_trace.h"
#include "headers/nfsd.h"


// ----------------------------------------------------------------------------//
//                              Global Variables                               //                                     //
char LICENSE[] SEC("license") = "Dual BSD/GPL";
volatile const __u32 filter_pid;
__u64 hit = 0;
__u64 miss = 0;


#define FILE_NAME_LEN 32
#define TASK_COMM_LEN 32
#define MAX_PROCDURE_LEN 32
#define IOCB_DIRECT		(1 << 17) // 内核宏变量
struct trace_event_raw_rpc_task {
    unsigned short common_type;
    unsigned char common_flags;
    unsigned char common_preempt_count;
    int common_pid;

    unsigned int task_id;
    unsigned int client_id;
    const void *action;
    unsigned long runstate;
    int status;
    unsigned short flags;
};
enum op_type {
    //file_operations
    nfs_file_mmap, nfs4_file_open, nfs4_file_flush, nfs_file_release,
    nfs_file_fsync, nfs_lock, nfs_flock, nfs_check_flags, nfs4_setlease,
    nfs4_copy_file_range, nfs4_file_llseek, nfs42_fallocate, nfs42_remap_file_range,
    //dir_inode
    nfs_create, nfs_lookup, nfs_atomic_open, nfs_link, nfs_unlink,
    nfs_symlink, nfs_mkdir, nfs_rmdir, nfs_mknod, nfs_rename, 
    nfs_permission,nfs_getattr, nfs_setattr, nfs4_listxattr,
    //dentry_operations
    nfs4_lookup_revalidate, nfs_weak_revalidate, nfs_dentry_delete, 
    nfs_dentry_iput, nfs_d_automount, nfs_d_release
};




struct func_stats {
    u64 latency;
    u64 timestamp;
	u32 pid;
	enum op_type op;
    char comm[TASK_COMM_LEN];
};

struct rw_event {
    u32 pid;
    u64 lat;
    u64 time_stamp;
    u64 size;
    char comm[TASK_COMM_LEN];
    char file[FILE_NAME_LEN];
};

// struct pgio_event {
//     u32 pid;
//     u64 lat;
//     u64 time_stamp;
//     u64 size;
//     char comm[TASK_COMM_LEN];
//     char file[FILE_NAME_LEN];
// };
struct rpc_key{
    u32 task_id;
    u32 client_id;
};

struct rpc_event {
    u32 tk_owner;// pid
    char proc[TASK_COMM_LEN];
    u64 timestamp;
    u64 wake_lat;
    u64 end_lat;
    u64 end_action;
};

struct error_event {
    u64 time_stamp;
    u32 pid;
    char proc[TASK_COMM_LEN]; //rpc procedure name
    u64 error_status;
};

struct vfs_data {
    u64 time_stamp;
    char file_name[FILE_NAME_LEN];
    bool is_direct; //保留字段
};




struct {
	__uint(type, BPF_MAP_TYPE_QUEUE);
	__type(value, struct rw_event);
	__uint(max_entries, MAX_QUEUE_ENTRIES);
} io_events SEC(".maps");


struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_ENTRIES);
	__type(key, __u64); // pid_tgid
	__type(value, struct vfs_data);
} io_starts SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_QUEUE);
	__type(value, struct error_event);
	__uint(max_entries, MAX_QUEUE_ENTRIES);
} nfs_error_events SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_ENTRIES);
    __type(key, struct rpc_key);
    __type(value, struct rpc_event);
}rpc_start SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_QUEUE);
    __type(value, struct rpc_event);
    __uint(max_entries, MAX_QUEUE_ENTRIES);
}rpc_events  SEC(".maps");

// ----------------------------------------------------------------------------//
//                              Utils Func                                     //
static __always_inline void *
bpf_map_lookup_or_try_init(void *map, const void *key, const void *init)
{
    /* 如果没有找到，尝试创建一个 */
    bpf_map_update_elem(map, key, init, BPF_ANY);
    return bpf_map_lookup_elem(map, key);
}

static __always_inline void handle_generic_error(u64 pid_tgid, int error_code, const char *proc_name) {
    struct error_event e_event = {};
    e_event.pid = (__u32)(pid_tgid >> 32);
    e_event.time_stamp = bpf_ktime_get_ns();
    e_event.error_status = error_code;
    bpf_probe_read_kernel_str(e_event.proc, sizeof(e_event.proc), proc_name);
    bpf_map_push_elem(&nfs_error_events, &e_event, BPF_EXIST); 
}

static __always_inline char * get_file_name(struct file *fp) {
    struct dentry *dentry = BPF_CORE_READ(fp, f_path.dentry);
    if (!dentry) return NULL;
    const __u8 *file_name = BPF_CORE_READ(dentry, d_name.name);
    if (!file_name) return NULL;
    return (char *)file_name;
}

static __always_inline int parse_print_rpc_task_runstate(unsigned long runstate){
    bpf_printk("runstate: ");
    if (runstate & (1UL << 0)) bpf_printk("RUNNING|");
    if (runstate & (1UL << 1)) bpf_printk("QUEUED|");
    if (runstate & (1UL << 2)) bpf_printk("ACTIVE|");
    if (runstate & (1UL << 3)) bpf_printk("NEED_XMIT|");
    if (runstate & (1UL << 4)) bpf_printk("NEED_RECV|");
    if (runstate & (1UL << 5)) bpf_printk("MSG_PIN_WAIT|");
    if (runstate & (1UL << 6)) bpf_printk("SIGNALLED|");
    return 0;
}

static __always_inline int parse_print_rpc_task_flags(unsigned short flags){
    bpf_printk("flags: ");
    if (flags & 0x0001) bpf_printk("ASYNC|");
    if (flags & 0x0002) bpf_printk("SWAPPER|");
    if (flags & 0x0004) bpf_printk("MOVEABLE|");
    if (flags & 0x0010) bpf_printk("NULLCREDS|");
    if (flags & 0x0020) bpf_printk("MAJORSEEN|");
    if (flags & 0x0080) bpf_printk("DYNAMIC|");
    if (flags & 0x0100) bpf_printk("NO_ROUND_ROBIN|");
    if (flags & 0x0200) bpf_printk("SOFT|");
    if (flags & 0x0400) bpf_printk("SOFTCONN|");
    if (flags & 0x0800) bpf_printk("SENT|");
    if (flags & 0x1000) bpf_printk("TIMEOUT|");
    if (flags & 0x2000) bpf_printk("NOCONNECT|");
    if (flags & 0x4000) bpf_printk("NORTO|");
    if (flags & 0x8000) bpf_printk("CRED_NOREF|");
    return 0;
}

// static __always_inline int print_rpc(struct trace_event_raw_rpc_task *ctx){
//     bpf_printk("timestamp: %ld", bpf_ktime_get_ns());
//     u64 pid = bpf_get_current_pid_tgid() >> 32;
//     //打印ctx各个字段：
//     bpf_printk("rpc_task_complete: pid = %d, task_id=%u, client_id=%u, action=%ps, status=%d", 
//         pid, ctx->task_id, ctx->client_id, ctx->action, ctx->status);
    
//     // 打印解析后的flags和runstate
//     //parse_print_rpc_task_flags(ctx->flags);
//     parse_print_rpc_task_runstate(ctx->runstate);
//     return 0;
// }

// ----------------------------------------------------------------------------//
//                              TrackIOPS  & Client Side                       //

//nfs_file_splice_read, nfs_file_splice_write
SEC("kprobe/nfs_file_splice_read")
int trace_entry_nfs_file_splice_read(struct pt_regs *ctx) { 
    __u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = pid_tgid >> 32;
    if (filter_pid && filter_pid != pid) {
        return 0;
    }
    struct file * fp = (struct file *)PT_REGS_PARM1(ctx);
    char * file_name = get_file_name(fp);
    struct vfs_data data = {};
    data.time_stamp = bpf_ktime_get_ns();
    bpf_probe_read_kernel_str(&data.file_name, sizeof(data.file_name), file_name);
    bpf_map_update_elem(&io_starts, &pid_tgid, &data, BPF_ANY);
    return 0;
}

SEC("kretprobe/nfs_file_splice_read")
int trace_exit_nfs_file_splice_read(struct pt_regs *ctx) { 
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    long int ret = PT_REGS_RC(ctx); 

    struct vfs_data * data = bpf_map_lookup_elem(&io_starts, &pid_tgid);
    if (!data) {
        return 0;
    }

    struct rw_event event = {};
    event.pid = pid_tgid >> 32;
    event.time_stamp = bpf_ktime_get_ns();
    event.lat = event.time_stamp - data->time_stamp;
    event.size = ret;
    bpf_get_current_comm(&event.comm, sizeof(event.comm));
    bpf_probe_read_kernel_str(&event.file, sizeof(event.file), data->file_name);
    bpf_map_push_elem(&io_events, &event, BPF_EXIST);
    bpf_map_delete_elem(&io_starts, &pid_tgid);
    return 0;
}



SEC("kprobe/nfs_file_read" ) 
int trace_entry_nfs_file_read(struct pt_regs *ctx) {
    
    __u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = pid_tgid >> 32;


    if (filter_pid && filter_pid != pid) {
        return 0;
    }

    struct kiocb *iocb = (struct kiocb *)PT_REGS_PARM1(ctx);
    struct file *fp = BPF_CORE_READ(iocb, ki_filp);
    char * file_name;
	file_name = get_file_name(fp);

    struct vfs_data data = {};
    data.time_stamp = bpf_ktime_get_ns();
    bpf_probe_read_kernel_str(&data.file_name, sizeof(data.file_name), file_name);
    int flags = 0;
    bpf_core_read(&flags, sizeof(flags), &iocb->ki_flags);

    data.is_direct = (flags & IOCB_DIRECT) != 0;
    bpf_map_update_elem(&io_starts, &pid_tgid, &data, BPF_ANY);
    return 0;
}



SEC("kretprobe/nfs_file_read" ) 
int trace_exit_nfs_file_read(struct pt_regs *ctx) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    long int ret = PT_REGS_RC(ctx); 

    struct vfs_data * data = bpf_map_lookup_elem(&io_starts, &pid_tgid);
    if (!data) {
        return 0;
    }

    struct rw_event event = {};
    event.pid = pid_tgid >> 32;
    event.time_stamp = bpf_ktime_get_ns();
    event.lat = event.time_stamp - data->time_stamp;
    event.size = ret;
    bpf_get_current_comm(&event.comm, sizeof(event.comm));
    bpf_probe_read_kernel_str(&event.file, sizeof(event.file), data->file_name);
    bpf_map_push_elem(&io_events, &event, BPF_EXIST);
    bpf_map_delete_elem(&io_starts, &pid_tgid);
    return 0;
}

SEC("kprobe/iter_file_splice_write")
int trace_entry_iter_file_splice_write(struct pt_regs *ctx) { 
    __u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = pid_tgid >> 32;
    if (filter_pid && filter_pid != pid) {
        return 0;
    }
    struct vfs_data data = {};
    data.time_stamp = bpf_ktime_get_ns();
    bpf_map_update_elem(&io_starts, &pid_tgid, &data, BPF_ANY);
    return 0;

}

SEC("kretprobe/iter_file_splice_write")
int trace_exit_iter_file_splice_write(struct pt_regs *ctx) { 
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    long int ret = PT_REGS_RC(ctx);

    struct vfs_data * data = bpf_map_lookup_elem(&io_starts, &pid_tgid);
    if (!data) {
        //bpf_printk("write failed from io_starts");
        return 0;
    }

    struct rw_event event = {};
    event.pid = pid_tgid >> 32;
    event.time_stamp = bpf_ktime_get_ns();
    event.lat = event.time_stamp - data->time_stamp;
    event.size = ret;
    bpf_get_current_comm(&event.comm, sizeof(event.comm));
    bpf_probe_read_kernel_str(&event.file, sizeof(event.file), data->file_name);
    bpf_map_push_elem(&io_events, &event, BPF_EXIST);
    return 0;

}

SEC("kprobe/nfs_file_write" ) 
int trace_entry_nfs_file_write(struct pt_regs *ctx) { 
    __u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = pid_tgid >> 32;
	//__u32 tid = (__u32)pid_tgid;
    // bpf_printk(" trace entry nfs_file_write with pid %d and timestamp %ld", pid, bpf_ktime_get_ns()); 

    if (filter_pid && filter_pid != pid) {
        return 0;
    }

    struct kiocb *iocb = (struct kiocb *)PT_REGS_PARM1(ctx);
    struct file *fp = BPF_CORE_READ(iocb, ki_filp);
    struct dentry *dentry = BPF_CORE_READ(fp, f_path.dentry);
    const __u8 *file_name;
	file_name = BPF_CORE_READ(dentry, d_name.name);

    struct vfs_data data = {};
    data.time_stamp = bpf_ktime_get_ns();
    bpf_probe_read_kernel_str(&data.file_name, sizeof(data.file_name), file_name);
    bpf_map_update_elem(&io_starts, &pid_tgid, &data, BPF_ANY);
    return 0;
}

SEC("kretprobe/nfs_file_write" ) 
int trace_exit_nfs_file_write(struct pt_regs *ctx) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    long int ret = PT_REGS_RC(ctx); 
    // if (ret < 0) {
    //     // 错误处理
    //     handle_generic_error(pid_tgid, ret, nfs_file_write); 
    //     // bpf_map_delete_elem(&io_starts, &pid_tgid);
    //     return 0;
    // } 
    
    struct vfs_data * data = bpf_map_lookup_elem(&io_starts, &pid_tgid);
    if (!data) {
        //bpf_printk("write failed from io_starts");
        return 0;
    }

    struct rw_event event = {};
    event.pid = pid_tgid >> 32;
    event.time_stamp = bpf_ktime_get_ns();
    event.lat = event.time_stamp - data->time_stamp;
    event.size = ret;
    bpf_get_current_comm(&event.comm, sizeof(event.comm));
    bpf_probe_read_kernel_str(&event.file, sizeof(event.file), data->file_name);
    bpf_map_push_elem(&io_events, &event, BPF_EXIST);
   //bpf_map_delete_elem(&io_starts, &pid_tgid);
    return 0;
}




/*---------------------------------------------rpc task management--------------------------------------------------------*/

SEC("kprobe/rpc_execute")
int rpc_execute(struct pt_regs *ctx){
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    struct rpc_task* task = (struct rpc_task *)PT_REGS_PARM1(ctx);
    struct rpc_message msg = BPF_CORE_READ(task, tk_msg);
    const struct rpc_procinfo * procinfo = BPF_CORE_READ(&msg, rpc_proc);
    // task_id 初始化为0
    //client id
    struct rpc_clnt* clnt = BPF_CORE_READ(task, tk_client);
    u32 client_id = BPF_CORE_READ(clnt, cl_clid);
    // get proc name
    const char *proc_name;
	proc_name = BPF_CORE_READ(procinfo, p_name);

    //bpf_probe_read_kernel_str(
    struct rpc_key key = {
        .task_id = 0,
        .client_id = client_id,
    };

    struct rpc_event event = {
        .tk_owner = BPF_CORE_READ(task, tk_owner),
        .timestamp = bpf_ktime_get_ns(),
        .wake_lat = 0,
        .end_lat = 0
    };
    bpf_probe_read_kernel_str(&event.proc, sizeof(event.proc), proc_name);
    bpf_map_update_elem(&rpc_start, &key, &event, BPF_ANY);
    return 0;
}


SEC("tracepoint/sunrpc/rpc_task_begin")
int rpc_task_begin(struct trace_event_raw_rpc_task *ctx){
    u64 pid = bpf_get_current_pid_tgid() >> 32;
    // bpf_printk("rpc_task_begin: pid = %d, task_id=%u, client_id=%u", 
    //      pid, ctx->task_id, ctx->client_id);
    struct rpc_key key = {
        .task_id = 0,
        .client_id = ctx->client_id,
    };
    struct rpc_event *event = bpf_map_lookup_elem(&rpc_start, &key);
    if(event){
        //bpf_printk("rpc_task_begin:task_id=%u, client_id=%u",  ctx->task_id, ctx->client_id);
        bpf_map_delete_elem(&rpc_start, &key);
        key.task_id = ctx->task_id;
        event->timestamp = bpf_ktime_get_ns();
        bpf_map_update_elem(&rpc_start, &key, event, BPF_ANY);

        if(ctx->status != 0) {
            handle_generic_error(pid, ctx->status, event->proc);
            //bpf_printk("rpc_task_begin error: pid = %d, task_id=%u, client_id=%u, action=%ps, status=%d", 
            //    pid, ctx->task_id, ctx->client_id, ctx->action, ctx->status);
            return 0;
        }
    }

    //trackiops
    void *val = bpf_map_lookup_elem(&link_begin, &pid);
    if(val){
        u64 task_id = ctx->task_id;
        u64 start_time = *((u64 *)val);
        struct rpc_task_info info = {
            .timestamp = start_time,
            .pid = pid
        };
        bpf_map_lookup_or_try_init(&waiting_rpc, &task_id, &info);      
    }
    return 0;
}



SEC("tracepoint/sunrpc/rpc_task_wakeup")
int rpc_task_wakeup(struct trace_event_raw_rpc_task *ctx){
    
    struct rpc_key key = {
        .task_id = ctx->task_id,
        .client_id = ctx->client_id,
    };

    struct rpc_event *event = bpf_map_lookup_elem(&rpc_start, &key);
    if(event){
        //bpf_printk("rpc_task_wakeup:  task_id=%u, client_id=%u, action=%ps, status=%d", 
        //ctx->task_id, ctx->client_id, ctx->action, ctx->status);
        u64 begin_stamp = event->timestamp;
        event->wake_lat = bpf_ktime_get_ns() - begin_stamp;
        bpf_map_update_elem(&rpc_start, &key, event, BPF_ANY);

        if(ctx->status != 0) {
            u64 pid = bpf_get_current_pid_tgid() >> 32;
            handle_generic_error(pid, ctx->status, event->proc);
            return 0;
        }
    }

    //打印ctx各个字段：
    // bpf_printk("rpc_task_wakeup: pid = %d, task_id=%u, client_id=%u, action=%ps, status=%d", 
    //     pid, ctx->task_id, ctx->client_id, ctx->action, ctx->status);
    
    // 打印解析后的flags和runstate
    //parse_print_rpc_task_flags(ctx->flags);
    //parse_print_rpc_task_runstate(ctx->runstate);
    return 0;
}

SEC("tracepoint/sunrpc/rpc_task_call_done")
int rpc_task_call_done(struct trace_event_raw_rpc_task *ctx){

    struct rpc_key key = {
        .task_id = ctx->task_id,
        .client_id = ctx->client_id,
    };

    struct rpc_event *event = bpf_map_lookup_elem(&rpc_start, &key);
    if(event){
        bpf_printk("rpc_task_call_done:  task_id=%u, client_id=%u, action=%ps, status=%d", 
             ctx->task_id, ctx->client_id, ctx->action, ctx->status);
        event->end_action = (unsigned long)ctx->action;
        long  err = bpf_map_push_elem(&rpc_events, event, BPF_EXIST);
        //bpf_map_delete_elem(&rpc_start, &key);
        if(ctx->status != 0) {

            u64 pid = bpf_get_current_pid_tgid() >> 32;
            handle_generic_error(pid, ctx->status, event->proc);
            return 0;
        }
    }
    //打印ctx各个字段：
    // bpf_printk("rpc_task_call_done: pid = %d, task_id=%u, client_id=%u, action=%ps, status=%d", 
    //     pid, ctx->task_id, ctx->client_id, ctx->action, ctx->status);
    
    // 打印解析后的flags和runstate
    //parse_print_rpc_task_flags(ctx->flags);
    //parse_print_rpc_task_runstate(ctx->runstate);
    return 0;
}

SEC("tracepoint/sunrpc/rpc_task_end")
int rpc_task_end(struct trace_event_raw_rpc_task *ctx){
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    struct rpc_key key = {
        .task_id = ctx->task_id,
        .client_id = ctx->client_id,
    };
    struct rpc_event *event = bpf_map_lookup_elem(&rpc_start, &key);
    if(event){
        bpf_printk("rpc_task_end: task_id=%u, client_id=%u, action=%ps, status=%d", 
            ctx->task_id, ctx->client_id, ctx->action, ctx->status);
        u64 begin_stamp = event->timestamp;
        event->timestamp = bpf_ktime_get_ns();
        event->end_lat = event->timestamp - begin_stamp;
        bpf_map_update_elem(&rpc_start, &key, event, BPF_ANY);

        if(ctx->status != 0) {
            handle_generic_error(pid, ctx->status, event->proc);
            //bpf_printk("rpc_task_begin error: pid = %d, task_id=%u, client_id=%u, action=%ps, status=%d", 
            //    pid, ctx->task_id, ctx->client_id, ctx->action, ctx->status);
            return 0;
        }
    }
    //打印ctx各个字段：
    // bpf_printk("rpc_task_end: pid = %d, task_id=%u, client_id=%u, action=%ps, status=%d", 
    //     pid, ctx->task_id, ctx->client_id, ctx->action, ctx->status);
    
    // 打印解析后的flags和runstate
    //parse_print_rpc_task_flags(ctx->flags);
    //parse_print_rpc_task_runstate(ctx->runstate);


    // trackiops
    u64 task_id = ctx->task_id;
    void *val = bpf_map_lookup_elem(&waiting_rpc, &task_id);
    if(val){
        struct rpc_task_info info = *((struct rpc_task_info *)val);
        bpf_map_lookup_or_try_init(&link_end, &info.pid, &info.timestamp);
        //bpf_map_delete_elem(&waiting_rpc, &task_id);
      
    }
    return 0;
}

// ----------------------------------------------------------------------------//
//                              TrackIOPS  & Server Side                       //

struct svc_data{
    char proc[TASK_COMM_LEN];
    u64 time_stamp;
    u32 xid;
};

SEC("kprobe/nfsd_dispatch")
int nfsd_dispatch(struct pt_regs *ctx){ 
    struct svc_rqst * rqst = (struct svc_rqst *)PT_REGS_PARM1(ctx);
    const struct svc_procedure * proc = BPF_CORE_READ(rqst, rq_procinfo);
    u64 process_func = (u64)BPF_CORE_READ(proc, pc_func);

    const char *proc_name;
	proc_name = BPF_CORE_READ(proc, pc_name);

    struct svc_data data = {};
    data.xid = BPF_CORE_READ(rqst, rq_xid);
    bpf_printk("nfsd_dispatch: xid: %u, proc_name: %s, process_func: %llx", proc_name, process_func);
    return 0;
}

SEC("kprobe/svc_recv")
int svc_recv(struct pt_regs *ctx){ 
    struct svc_rqst * rqst = (struct svc_rqst *)PT_REGS_PARM1(ctx);
    const struct svc_procedure * proc = BPF_CORE_READ(rqst, rq_procinfo);
    u64 process_func = (u64)BPF_CORE_READ(proc, pc_func);

    const char *proc_name;
	proc_name = BPF_CORE_READ(proc, pc_name);

    struct auth_domain * rq_client = BPF_CORE_READ(rqst, rq_client);
    char * name = BPF_CORE_READ(rq_client, name);

    bpf_printk("svc_recv: peer name: %s, proc name: %s, timestamp: %lu", name, proc_name, bpf_ktime_get_ns());
    struct svc_data data = {};
    return 0;
}

SEC("tracepoint/sunrpc/svc_send")
int svc_send(void *ctx){ 
    struct svc_send_format{
        u16 common_type;
        u8 common_flags;
        u8 common_preempt_count;
        int common_pid;
        u8 * server;
        u8 * client;
        u32 netns_ino;
        u32 xid;
        int status;
        u64 flags;
    };
    struct svc_send_format * format = (struct svc_send_format *)ctx;
    //xprt = rqstp->rq_xprt;
    u32 xid = format->xid;
    bpf_printk("svc_send: %lu, xid: %u, status: %d", bpf_ktime_get_ns(), xid, format->status);
    //status = xprt->xpt_ops->xpo_sendto(rqstp);
    return 0;
}

// svc_xdr_recvfrom
// svc_xdr_sendto
SEC("tracepoint/sunrpc/svc_xdr_recvfrom")
int svc_xdr_recvfrom(void *ctx){ 
    struct svc_xdr_recvfrom_format{
        u16 common_type;
        u8 common_flags;
        u8 common_preempt_count;
        int common_pid;

        u32 xid;
        const void * head_base;
        size_t head_len;
        const void * tail_base;
        size_t tail_len;
        u32 page_len;
        u32 msg_len;
    };
    struct svc_xdr_recvfrom_format * format = (struct svc_xdr_recvfrom_format *)ctx;
    u32 xid = format->xid;
    bpf_printk("svc_xdr_recvfrom: %lu, xid: %u", bpf_ktime_get_ns(), xid);
    return 0;
}

SEC("tracepoint/sunrpc/svc_xdr_sendto")
int svc_xdr_sendto(void *ctx){ 
    struct svc_xdr_recvfrom_format{
        u16 common_type;
        u8 common_flags;
        u8 common_preempt_count;
        int common_pid;

        u32 xid;
        const void * head_base;
        size_t head_len;
        const void * tail_base;
        size_t tail_len;
        u32 page_len;
        u32 msg_len;
    };
    struct svc_xdr_recvfrom_format * format = (struct svc_xdr_recvfrom_format *)ctx;
    u32 xid = format->xid;
    bpf_printk("svc_xdr_sendto: %lu, xid: %u", bpf_ktime_get_ns(), xid);
    return 0;
}


// ------------------------------------------------------------------------------------ //
//                                    NFSD Operations ---------------------------------- //

// 宏定义：统一的NFS操作函数生成器
// 只需要一个枚举类型参数，自动提取xid并调用统一的处理函数
#define DEFINE_NFSD_OP(op_enum) \
    SEC("kprobe/nfsd4_" #op_enum) \
    int trace_entry_nfsd4_##op_enum(struct pt_regs *ctx) { \
        struct svc_rqst *rqst = (struct svc_rqst *)PT_REGS_PARM1(ctx); \
        __u32 xid = rqst ? BPF_CORE_READ(rqst, rq_xid) : 0; \
        return trace_nfsd_op_entry(ctx, (u32)nfsd4_##op_enum, xid); \
    } \
    SEC("kretprobe/nfsd4_" #op_enum) \
    int trace_exit_nfsd4_##op_enum(struct pt_regs *ctx) { \
        return trace_nfsd_op_exit(ctx, (u32)nfsd4_##op_enum); \
    }

// 统一的NFS操作入口处理函数
static __always_inline int trace_nfsd_op_entry(struct pt_regs *ctx, u32 op_type, __u32 xid) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    u64 ts = bpf_ktime_get_ns();
    
    struct nfsd_op_stats stats = {};
    stats.timestamp = ts;
    stats.pid = pid;
    stats.op = op_type;
    stats.xid = xid;
    bpf_get_current_comm(&stats.comm, sizeof(stats.comm));
    bpf_printk("nfsd_op_entry: op: %d, pid: %u, timestamp: %lu", op_type, pid, ts);

    // 使用联合键 (op_type, pid) 确保每个进程的每个操作类型都有唯一键值
    struct nfsd_op_key key = {.op_type = op_type, .pid = pid};
    bpf_map_update_elem(&nfsd_op_starts, &key, &stats, BPF_ANY);
    return 0;
}

// 统一的NFS操作退出处理函数
static __always_inline int trace_nfsd_op_exit(struct pt_regs *ctx, u32 op_type) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    
    // 使用联合键 (op_type, pid) 查找开始统计信息
    struct nfsd_op_key key = {.op_type = op_type, .pid = pid};
    struct nfsd_op_stats *start_stats = bpf_map_lookup_elem(&nfsd_op_starts, &key);
    if (!start_stats) {
        bpf_printk("nfsd_op_exit: start_stats not found for op_type: %d, pid: %u", op_type, pid);
        return 0;
    }

    // 从start_stats中获取xid
    __u32 xid = start_stats->xid;
    
    u64 delta = bpf_ktime_get_ns() - start_stats->timestamp;
    delta = delta / 1000;  // 转换为微秒
    //bpf_map_delete_elem(&nfsd_op_starts, &key);  // 使用联合键删除
    if (delta <= 0) return 0;

    struct nfsd_op_stats stats = {};
    stats.timestamp = bpf_ktime_get_ns();
    stats.latency = delta;
    stats.pid = pid;
    stats.op = op_type;
    stats.xid = xid;
    bpf_get_current_comm(&stats.comm, sizeof(stats.comm));

    bpf_printk("nfsd_op_exit: op: %d, pid: %u, latency: %lu", op_type, pid, delta);
    
    int err = bpf_map_push_elem(&nfsd_op_events, &stats, 0);
    if (err) {
        bpf_printk("nfsd_op_events map_push failed: %d", err);
    }

    return 0;
}




// 使用宏定义统一生成所有NFS操作函数
// 只需要一个枚举类型参数，自动生成入口和退出函数
DEFINE_NFSD_OP(sequence)
DEFINE_NFSD_OP(open)
DEFINE_NFSD_OP(close)
DEFINE_NFSD_OP(read)
DEFINE_NFSD_OP(write)
DEFINE_NFSD_OP(lookup)
DEFINE_NFSD_OP(create)
DEFINE_NFSD_OP(remove)
DEFINE_NFSD_OP(create_session)
DEFINE_NFSD_OP(destroy_session)
DEFINE_NFSD_OP(getattr)
DEFINE_NFSD_OP(setattr)
DEFINE_NFSD_OP(getxattr)
DEFINE_NFSD_OP(setxattr)
DEFINE_NFSD_OP(allocate)
DEFINE_NFSD_OP(layoutget)
DEFINE_NFSD_OP(access)
DEFINE_NFSD_OP(commit)
DEFINE_NFSD_OP(delegreturn)
DEFINE_NFSD_OP(getfh)
DEFINE_NFSD_OP(link)
DEFINE_NFSD_OP(lock)
DEFINE_NFSD_OP(lockt)
DEFINE_NFSD_OP(locku)
DEFINE_NFSD_OP(lookupp)
DEFINE_NFSD_OP(nverify)
DEFINE_NFSD_OP(open_confirm)
DEFINE_NFSD_OP(open_downgrade)
DEFINE_NFSD_OP(putfh)
DEFINE_NFSD_OP(putrootfh)
DEFINE_NFSD_OP(readdir)
DEFINE_NFSD_OP(readlink)
DEFINE_NFSD_OP(rename)
DEFINE_NFSD_OP(renew)
DEFINE_NFSD_OP(restorefh)
DEFINE_NFSD_OP(savefh)
DEFINE_NFSD_OP(secinfo)
DEFINE_NFSD_OP(setclientid)
DEFINE_NFSD_OP(setclientid_confirm)
DEFINE_NFSD_OP(verify)
DEFINE_NFSD_OP(release_lockowner)
DEFINE_NFSD_OP(exchange_id)
DEFINE_NFSD_OP(backchannel_ctl)
DEFINE_NFSD_OP(bind_conn_to_session)
DEFINE_NFSD_OP(destroy_clientid)
DEFINE_NFSD_OP(reclaim_complete)
DEFINE_NFSD_OP(secinfo_no_name)
DEFINE_NFSD_OP(test_stateid)
DEFINE_NFSD_OP(free_stateid)
DEFINE_NFSD_OP(getdeviceinfo)
DEFINE_NFSD_OP(layoutcommit)
DEFINE_NFSD_OP(layoutreturn)
DEFINE_NFSD_OP(deallocate)
DEFINE_NFSD_OP(clone)
DEFINE_NFSD_OP(copy)
DEFINE_NFSD_OP(seek)
DEFINE_NFSD_OP(offload_status)
DEFINE_NFSD_OP(offload_cancel)
DEFINE_NFSD_OP(copy_notify)
DEFINE_NFSD_OP(listxattrs)
DEFINE_NFSD_OP(removexattr)





// ------------------------------------------------------------------------------------ //
//                                    NFS Operations ---------------------------------- //

struct { 
    __uint(type, BPF_MAP_TYPE_HASH); 
    __uint(max_entries, 10240); 
    __type(key, __u32); 
    __type(value, __u64); 
} starts SEC(".maps"); 

struct {
	__uint(type, BPF_MAP_TYPE_QUEUE);
	__type(value, struct func_stats);
	__uint(max_entries, MAX_QUEUE_ENTRIES);
} op_events SEC(".maps");


static __always_inline int trace_func_entry(struct pt_regs *ctx) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = pid_tgid >> 32;
	__u32 tid = (__u32)pid_tgid;
    u64 ts = bpf_ktime_get_ns();
    bpf_map_update_elem(&starts, &tid, &ts, BPF_ANY);
    return 0;
}

static __always_inline int trace_func_exit(struct pt_regs *ctx, enum op_type op) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = pid_tgid >> 32;
	__u32 tid = (__u32)pid_tgid;
    u64 *start = bpf_map_lookup_elem(&starts, &tid);
    if (!start) return 0;

    u64 delta = bpf_ktime_get_ns() - *start;
    delta = delta / 1000;// convert to us
    bpf_map_delete_elem(&starts, &tid);
    if(delta <= 0) return 0;

    struct func_stats stats = {};
    stats.timestamp = bpf_ktime_get_ns();
    stats.latency = delta;
    stats.pid = pid;
    stats.op = op;
    bpf_get_current_comm(&stats.comm, sizeof(stats.comm));

    // bpf_perf_event_output(ctx, &info, BPF_F_CURRENT_CPU, &stats, sizeof(stats));
    int err = bpf_map_push_elem(&op_events, &stats, BPF_EXIST); // 注意第三个参数调整
    if (err) {
        bpf_printk("map_push failed: %d", err);
    }

    return 0;
}


#define DEFINE_FUNC_TRACE(func) \
    SEC("kprobe/nfs_" #func) \
    int trace_entry_##func(struct pt_regs *ctx) { \
        return trace_func_entry(ctx); \
    } \
    SEC("kretprobe/" #func) \
    int trace_exit_##func(struct pt_regs *ctx) { \
        return trace_func_exit(ctx, func); \
    }

// 文件操作

DEFINE_FUNC_TRACE(nfs_file_mmap)
DEFINE_FUNC_TRACE(nfs4_file_open)
DEFINE_FUNC_TRACE(nfs4_file_flush)
DEFINE_FUNC_TRACE(nfs_file_release)
DEFINE_FUNC_TRACE(nfs_file_fsync)
DEFINE_FUNC_TRACE(nfs_lock)
DEFINE_FUNC_TRACE(nfs_flock)
DEFINE_FUNC_TRACE(nfs_check_flags)
DEFINE_FUNC_TRACE(nfs4_setlease)
DEFINE_FUNC_TRACE(nfs4_copy_file_range)
DEFINE_FUNC_TRACE(nfs4_file_llseek)
DEFINE_FUNC_TRACE(nfs42_fallocate)
DEFINE_FUNC_TRACE(nfs42_remap_file_range)

// file文件操作
DEFINE_FUNC_TRACE(nfs_create)
DEFINE_FUNC_TRACE(nfs_lookup)
DEFINE_FUNC_TRACE(nfs_atomic_open)
DEFINE_FUNC_TRACE(nfs_link)
DEFINE_FUNC_TRACE(nfs_unlink)
DEFINE_FUNC_TRACE(nfs_symlink)
DEFINE_FUNC_TRACE(nfs_mkdir)
DEFINE_FUNC_TRACE(nfs_rmdir)
DEFINE_FUNC_TRACE(nfs_mknod)
DEFINE_FUNC_TRACE(nfs_rename)
//DEFINE_FUNC_TRACE(nfs_permission)
DEFINE_FUNC_TRACE(nfs_getattr)
DEFINE_FUNC_TRACE(nfs_setattr)
DEFINE_FUNC_TRACE(nfs4_listxattr)

// dir目录操作
DEFINE_FUNC_TRACE(nfs4_lookup_revalidate)
DEFINE_FUNC_TRACE(nfs_weak_revalidate)
DEFINE_FUNC_TRACE(nfs_dentry_delete)
DEFINE_FUNC_TRACE(nfs_dentry_iput)
DEFINE_FUNC_TRACE(nfs_d_automount)
DEFINE_FUNC_TRACE(nfs_d_release)

// 添加随机延迟相关的全局变量
volatile const __u64 delay_probability = 1;  // 延迟概率 (0-100)
volatile const __u32 all_delay_us = 20;      // 延迟 (微秒)
// BPF兼容的延迟实现
static __always_inline void bpf_delay(u32 delay_us) {
    u64 delay_ns = (u64)delay_us * 1000;  // 转换为纳秒
    u64 start_time = bpf_ktime_get_ns();
    u64 target_time = start_time + delay_ns;
    
    // 使用有限循环次数来避免验证器错误
    #pragma unroll
    for (int i = 0; i < 1000; i++) {
        u64 current_time = bpf_ktime_get_ns();
        if (current_time >= target_time) {
            break;
        }
        // 添加一些计算来消耗时间
        u64 dummy = current_time * 2 + 1;
        dummy = dummy * 3 + 2;
        dummy = dummy * 5 + 3;
        (void)dummy; // 避免编译器优化
    }
    //bpf_printk("nfs_permission: injected delay of %u ns", bpf_ktime_get_ns() - start_time);
}

SEC("kprobe/nfs_permission") 
int trace_entry_nfs_permission(struct pt_regs *ctx) { 
    return trace_func_entry(ctx); 
} 

SEC("kretprobe/nfs_permission") 
int trace_exit_nfs_permission(struct pt_regs *ctx) { 
    //生成随机延迟
    u64 random = bpf_ktime_get_ns();
    if ((random % 100) < delay_probability) {
        u32 delay_us = all_delay_us;
        bpf_delay(delay_us);
    }
    
    return trace_func_exit(ctx, nfs_permission); 
}