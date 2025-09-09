#ifndef __NFSD_H
#define __NFSD_H



#define MAX_ENTRIES 1024
#define MAX_QUEUE_ENTRIES 65536
#define FILE_NAME_LEN 32
#define TASK_COMM_LEN 32
#define MAX_PROCDURE_LEN 32

// NFS操作类型枚举
enum nfsd_op_type {
    // 基础NFSv4操作
    nfsd4_access,
    nfsd4_close,
    nfsd4_commit,
    nfsd4_create,
    nfsd4_delegreturn,
    nfsd4_getattr,
    nfsd4_getfh,
    nfsd4_link,
    nfsd4_lock,
    nfsd4_lockt,
    nfsd4_locku,
    nfsd4_lookup,
    nfsd4_lookupp,
    nfsd4_nverify,
    nfsd4_open,
    nfsd4_open_confirm,
    nfsd4_open_downgrade,
    nfsd4_putfh,
    nfsd4_putrootfh,
    nfsd4_read,
    nfsd4_readdir,
    nfsd4_readlink,
    nfsd4_remove,
    nfsd4_rename,
    nfsd4_renew,
    nfsd4_restorefh,
    nfsd4_savefh,
    nfsd4_secinfo,
    nfsd4_setattr,
    nfsd4_setclientid,
    nfsd4_setclientid_confirm,
    nfsd4_verify,
    nfsd4_write,
    nfsd4_release_lockowner,
    
    // NFSv4.1操作
    nfsd4_exchange_id,
    nfsd4_backchannel_ctl,
    nfsd4_bind_conn_to_session,
    nfsd4_create_session,
    nfsd4_destroy_session,
    nfsd4_sequence,
    nfsd4_destroy_clientid,
    nfsd4_reclaim_complete,
    nfsd4_secinfo_no_name,
    nfsd4_test_stateid,
    nfsd4_free_stateid,
    
    // pNFS操作 (可选)
    nfsd4_getdeviceinfo,
    nfsd4_layoutget,
    nfsd4_layoutcommit,
    nfsd4_layoutreturn,
    
    // NFSv4.2操作
    nfsd4_allocate,
    nfsd4_deallocate,
    nfsd4_clone,
    nfsd4_copy,
    nfsd4_seek,
    nfsd4_offload_status,
    nfsd4_offload_cancel,
    nfsd4_copy_notify,
    nfsd4_getxattr,
    nfsd4_setxattr,
    nfsd4_listxattrs,
    nfsd4_removexattr,
    

};

// NFS操作统计信息结构
struct nfsd_op_stats {
    u64 latency;        // 8字节，偏移0
    u64 timestamp;      // 8字节，偏移8
    u32 pid;           // 4字节，偏移16
    u32 xid;           // 4字节，偏移20
    u32 op;            // 4字节，偏移24 - 使用u32而不是enum确保大小一致
    char comm[TASK_COMM_LEN];  // 32字节，偏移28
    char tag[MAX_PROCDURE_LEN]; // 32字节，偏移60
} __attribute__((packed));  // 禁用填充，确保紧凑布局

// NFS复合操作信息
struct nfsd_compound_info {
    u32 xid;
    u32 opcnt;
    char tag[MAX_PROCDURE_LEN];
    u64 timestamp;
    u32 pid;
};



struct {
    __uint(type, BPF_MAP_TYPE_QUEUE);
    __type(value, struct nfsd_op_stats);
    __uint(max_entries, MAX_QUEUE_ENTRIES);
} nfsd_op_events SEC(".maps");

// 联合键结构，用于nfsd_op_starts映射
struct nfsd_op_key {
    u32 op_type;  // 使用u32而不是enum确保大小一致
    u32 pid;      // 4字节
} __attribute__((packed));  // 禁用填充，确保紧凑布局

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_ENTRIES);
    __type(key, struct nfsd_op_key);  // 使用联合键 (op_type, pid)
    __type(value, struct nfsd_op_stats);
} nfsd_op_starts SEC(".maps");



#endif /* __NFSD_H */
