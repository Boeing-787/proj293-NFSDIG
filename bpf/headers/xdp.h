#ifndef __XDP_H
#define __XDP_H

//RPC请求头部，36字节加资格验证信息长度
struct rpc_call_head{
    u32 fragment_header;	//是否是最后一片以及此后部分的长度
    u32 xid;				//XID，请求与回复相同
    u32 msg_type;			//请求包固定为0
	u32 rpc_ver;			//RPC版本
	u32 prog;				//RPC程序，100003表示NFS
	u32 prog_ver;			//程序版本，4表示NFS4
	u32 procedure;		//例程号，1表示COMPOUND请求
    u32 cred_flavor;		//资格验证机制
    u32 cred_length;		//资格验证信息长度
	//之后的字段由于验证信息长度不同需要计算偏移
};

//RPC回复头部，28字节
struct rpc_reply_head{
    u32 fragment_header;	//是否是最后一片以及此后部分的长度
    u32 xid;				//XID，请求与回复相同
    u32 msg_type;			//回复包固定为1
    u32 reply_state;		//回复状态，接受为0
    u32 verifier_flavor;	//验证机制，0表示无
    u32 verifier_length;	//验证信息长度
    u32 accept_state;		//接受状态，RPC成功执行为0
};

//nfs回复内容头部
struct nfs_reply_head{
	u32 status;			//此次回复的结果
	u32 tag_len;			//tag长度
	u32 op_num;			//这个包中请求的个数
};

// NFS操作类型枚举
enum nfs_op_type {
    NFS_OP_PUTROOTFH = 1,
    NFS_OP_PUTFH = 2,
    NFS_OP_GETFH = 3,
    NFS_OP_LOOKUP = 4,
    NFS_OP_ACCESS = 5,
    NFS_OP_READLINK = 6,
    NFS_OP_READ = 7,
    NFS_OP_WRITE = 8,
    NFS_OP_CREATE = 9,
    NFS_OP_MKDIR = 10,
    NFS_OP_SYMLINK = 11,
    NFS_OP_MKNOD = 12,
    NFS_OP_REMOVE = 13,
    NFS_OP_RMDIR = 14,
    NFS_OP_RENAME = 15,
    NFS_OP_LINK = 16,
    NFS_OP_READDIR = 17,
    NFS_OP_READDIRPLUS = 18,
    NFS_OP_FSSTAT = 19,
    NFS_OP_FSINFO = 20,
    NFS_OP_PATHCONF = 21,
    NFS_OP_COMMIT = 22,
    NFS_OP_SETATTR = 23,
    NFS_OP_GETATTR = 24,
    NFS_OP_DELEGPURGE = 25,
    NFS_OP_DELEGRETURN = 26,
    NFS_OP_LAYOUTGET = 27,
    NFS_OP_LAYOUTCOMMIT = 28,
    NFS_OP_LAYOUTRETURN = 29,
    NFS_OP_SECINFO = 30,
    NFS_OP_FSID_PRESENT = 31,
    NFS_OP_EXCHANGE_ID = 32,
    NFS_OP_CREATE_SESSION = 33,
    NFS_OP_DESTROY_SESSION = 34,
    NFS_OP_SEQUENCE = 35,
    NFS_OP_GET_LEASE_TIME = 36,
    NFS_OP_RECLAIM_COMPLETE = 37,
    NFS_OP_ILLEGAL = 10044
};

// NFS操作统计信息
struct nfs_op_stats {
    u32 xid;           // 请求ID
    u32 op_type;       // 操作类型
    u32 op_count;      // 操作计数
    u64 timestamp;     // 时间戳
    u32 src_ip;        // 源IP地址
    u32 dst_ip;        // 目标IP地址
    u16 src_port;      // 源端口
    u16 dst_port;      // 目标端口
    u8 protocol;       // 协议类型 (TCP=6, UDP=17)
    u32 status;        // 操作状态
    u64 data_size;     // 数据大小
    char tag[32];      // 操作标签
};

// XDP统计信息
struct xdp_stats {
    u64 total_packets;     // 总包数
    u64 nfs_packets;       // NFS包数
    u64 tcp_packets;       // TCP包数
    u64 udp_packets;       // UDP包数
    u64 total_bytes;       // 总字节数
    u64 nfs_bytes;         // NFS字节数
};

#endif 