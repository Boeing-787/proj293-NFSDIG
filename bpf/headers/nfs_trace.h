#ifndef __NFS_H
#define __NFS_H

#include "vmlinux.h"

#define MAX_ENTRIES	1024
#define IPV6_LEN	16
#define MAX_SLOTS	27
#define AF_INET6 10
#define AF_INET 2

/// @sample {"interval": 1000, "type" : "log2_hist"}
//                              TRACKIOPS                                //
// --------------------------------------------------------------------  //



struct raw_metrics {
    u64 count;  
    u64 size;   
    u64 lat;    
};



struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_ENTRIES);
	__type(key, u64);
	__type(value, u64);
}link_begin SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_ENTRIES);
	__type(key, u64);
	__type(value, struct rpc_task_info);
}waiting_rpc SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_ENTRIES);
	__type(key, u64);
	__type(value, u64);
}link_end SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_ENTRIES);
    __type(key, struct io_metrics_key);
    __type(value, struct raw_metrics);
} io_metrics_read SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_ENTRIES);
    __type(key, struct io_metrics_key);
    __type(value, struct raw_metrics);
} io_metrics_write SEC(".maps");

struct rpc_task_info {
    u64 timestamp;
    u64 pid;
};
struct io_metrics_key {
    u64 fileid;      // 文件 inode 号
    dev_t dev;       // 设备号
};





//                                 OP_metrics                              //
// ----------------------------------------------------------------------  //   










#endif