#include <vmlinux.h>
#include <bpf/bpf_endian.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include "xdp.h"

// NFS相关常量
#define RPC_MSG_CALL 0
#define RPC_MSG_REPLY 1
#define RPC_PROG_NFS 100003
#define RPC_VER_NFS 4
#define ETH_P_IP 0x0800
#define IPPROTO_TCP 6
#define IPPROTO_UDP 17

// 头部长度常量
#define ETH_HLEN 14
#define IP_HLEN 20
#define TCP_HLEN 20
#define UDP_HLEN 8
#define ALL_HEAD_LEN (ETH_HLEN + IP_HLEN + TCP_HLEN)
#define UDP_HEAD_LEN (ETH_HLEN + IP_HLEN + UDP_HLEN)

// 统计相关常量
#define RX_KEY 0
#define TX_KEY 1

// 配置变量
volatile const u32 filter_src_ip = 0;      // 源IP过滤，0表示不过滤
volatile const u32 filter_dst_ip = 0;      // 目标IP过滤，0表示不过滤
volatile const u16 filter_src_port = 2049;  // 源端口过滤，NFS端口
volatile const u16 filter_dst_port = 2049; // 目标端口过滤，NFS端口
volatile const u8 filter_protocol = 0;     // 协议过滤，0表示不过滤

// 统计映射
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 2);
    __type(key, int);
    __type(value, u64);
} size_map SEC(".maps");

// NFS包统计映射
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, int);
    __type(value, u64);
} nfs_packet_count SEC(".maps");

// XDP统计映射
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, int);
    __type(value, struct xdp_stats);
} xdp_stats_map SEC(".maps");

// NFS操作统计映射（按XID索引）
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 10000);
    __type(key, u32);
    __type(value, struct nfs_op_stats);
} nfs_op_stats_map SEC(".maps");

// 全局计数器映射
struct counter_val {
    u32 counter;
    struct bpf_spin_lock lock;
};

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, int);
    __type(value, struct counter_val);
} packet_counter SEC(".maps");

// 辅助函数：检查IP地址是否匹配过滤条件
static inline bool check_ip_filter(u32 ip) {
    if (filter_src_ip == 0 && filter_dst_ip == 0) {
        return 1; // 不过滤
    }
    return (ip == filter_src_ip || ip == filter_dst_ip);
}

// 辅助函数：检查端口是否匹配过滤条件
static inline bool check_port_filter(u16 src_port, u16 dst_port) {
    // 如果两个过滤端口都为0，表示不过滤
    if (filter_src_port == 0 && filter_dst_port == 0) {
        return 1; // 不过滤
    }
    
    // 如果设置了源端口过滤，检查源端口
    if (filter_src_port != 0 && src_port == filter_src_port) {
        return 1;
    }
    
    // 如果设置了目标端口过滤，检查目标端口
    if (filter_dst_port != 0 && dst_port == filter_dst_port) {
        return 1;
    }
    
    // 对于NFS，通常只要有一个端口匹配2049就应该通过
    if ((filter_src_port == 2049 || filter_dst_port == 2049) &&
        (src_port == 2049 || dst_port == 2049)) {
        return 1;
    }
    
    return 0; // 不匹配过滤条件
}

// 辅助函数：检查协议是否匹配过滤条件
static inline bool check_protocol_filter(u8 protocol) {
    if (filter_protocol == 0) {
        return 1; // 不过滤
    }
    return (protocol == filter_protocol);
}

// 辅助函数：更新XDP统计信息
static inline void update_xdp_stats(u64 packet_size, u8 is_nfs, u8 protocol) {
    int key = 0;
    struct xdp_stats *stats = bpf_map_lookup_elem(&xdp_stats_map, &key);
    
    if (stats == NULL) {
        struct xdp_stats new_stats = {0};
        new_stats.total_packets = 1;
        new_stats.total_bytes = packet_size;
        if (is_nfs) {
            new_stats.nfs_packets = 1;
            new_stats.nfs_bytes = packet_size;
        }
        if (protocol == IPPROTO_TCP) {
            new_stats.tcp_packets = 1;
        } else if (protocol == IPPROTO_UDP) {
            new_stats.udp_packets = 1;
        }
        bpf_map_update_elem(&xdp_stats_map, &key, &new_stats, BPF_ANY);
    } else {
        stats->total_packets++;
        stats->total_bytes += packet_size;
        if (is_nfs) {
            stats->nfs_packets++;
            stats->nfs_bytes += packet_size;
        }
        if (protocol == IPPROTO_TCP) {
            stats->tcp_packets++;
        } else if (protocol == IPPROTO_UDP) {
            stats->udp_packets++;
        }
        bpf_map_update_elem(&xdp_stats_map, &key, stats, BPF_ANY);
    }
}

// 辅助函数：解析必要字段并更新统计（简易版）
static __always_inline void parse_nfs_operations(void *data, void *data_end, u32 data_len, u32 xid, __u8 has_record_marker,
                                       u32 src_ip, u32 dst_ip, u16 src_port, u16 dst_port, u8 protocol) {
    const __u8 *end = (const __u8 *)data_end;
    __u8 *base = (__u8 *)data;

    // 计算固定头大小：到 procedure 字段为止（不包含 cred_flavor/cred_length）
    // TCP: RM(4) + XID(4) + msg_type(4) + rpc_ver(4) + prog(4) + prog_ver(4) + procedure(4) = 28
    // UDP:       XID(4) + msg_type(4) + rpc_ver(4) + prog(4) + prog_ver(4) + procedure(4) = 24
    __u32 header_fixed = (has_record_marker ? 28 : 24);
    if ((void *)base + header_fixed > (void *)end) {
        return;
    }

    // 读取基础字段（msg_type, prog, procedure）
    // 偏移相对于 base：
    // has_rm? 8:4 -> msg_type
    // has_rm? 16:12 -> prog
    // has_rm? 24:20 -> procedure
    __u32 off_msg_type = has_record_marker ? 8 : 4;
    __u32 off_prog = has_record_marker ? 16 : 12;
    __u32 off_proc = has_record_marker ? 24 : 20;
    if ((void *)base + off_proc + 4 > (void *)end) {
        return;
    }
    __u32 msg_type = bpf_ntohl(*((__u32 *)(base + off_msg_type)));
    if (msg_type != RPC_MSG_CALL) {
        bpf_printk("XDP RPC: not CALL msg=%u", msg_type);
        return;
    }
    __u32 prog = bpf_ntohl(*((__u32 *)(base + off_prog)));
    if (prog != RPC_PROG_NFS) {
        // 不是 NFS 程序，直接返回，避免刷屏
        return;
    }
    __u32 procedure = bpf_ntohl(*((__u32 *)(base + off_proc)));
    // 读取程序版本
    __u32 off_prog_ver = has_record_marker ? 20 : 16;
    __u32 prog_ver = bpf_ntohl(*((__u32 *)(base + off_prog_ver)));
    // 仅在 NFSv4 且 COMPOUND 时解析
    if (prog_ver != 4 || procedure != 1) {
        bpf_printk("XDP NFS hdr: ver=%u proc=%u (skip non-v4 COMPOUND)", prog_ver, procedure);
        return;
    }
    bpf_printk("XDP NFSv4 COMPOUND: ver=%u proc=%u rm=%u", prog_ver, procedure, has_record_marker);

    // 进入认证字段位置（紧接在 procedure 之后）
    __u8 *cursor = base + header_fixed;

    // 简化：不解析 cred/verf/tag，直接略过到此并输出基础信息

    // 更新统计（仅填充所需字段）。请求方向无状态码，置 0；Tag 留空
    struct nfs_op_stats *op_stats = bpf_map_lookup_elem(&nfs_op_stats_map, &xid);
    if (op_stats == NULL) {
        struct nfs_op_stats new_stats = (struct nfs_op_stats){};
        new_stats.xid = xid;
        new_stats.timestamp = bpf_ktime_get_ns();
        new_stats.data_size = data_len;
        new_stats.src_ip = src_ip;
        new_stats.dst_ip = dst_ip;
        new_stats.src_port = src_port;
        new_stats.dst_port = dst_port;
        new_stats.protocol = protocol;
        new_stats.status = 0;
        // tag 置空
        bpf_map_update_elem(&nfs_op_stats_map, &xid, &new_stats, BPF_ANY);
    } else {
        op_stats->data_size += data_len;
        op_stats->src_ip = src_ip;
        op_stats->dst_ip = dst_ip;
        op_stats->src_port = src_port;
        op_stats->dst_port = dst_port;
        op_stats->protocol = protocol;
        op_stats->status = 0;
        // tag 置空
        bpf_map_update_elem(&nfs_op_stats_map, &xid, op_stats, BPF_ANY);
    }
}

// 修改函数以使用唯一键记录每个包
static __always_inline void parse_all_operations(void *data, void *data_end, u32 data_len, u32 xid, __u8 has_record_marker,
                                       u32 src_ip, u32 dst_ip, u16 src_port, u16 dst_port, u8 protocol) {
    // 获取唯一键
    int counter_key = 0;
    u32 *counter = bpf_map_lookup_elem(&packet_counter, &counter_key);
    u32 unique_key;
    if (counter == NULL) {
        unique_key = 0;
        bpf_map_update_elem(&packet_counter, &counter_key, &unique_key, BPF_ANY);
    } else {
        unique_key = __sync_fetch_and_add(counter, 1);
    }

    struct nfs_op_stats new_stats = (struct nfs_op_stats){};
    new_stats.xid = xid;
    new_stats.timestamp = bpf_ktime_get_ns();
    new_stats.data_size = data_len;
    new_stats.src_ip = src_ip;
    new_stats.dst_ip = dst_ip;
    new_stats.src_port = src_port;
    new_stats.dst_port = dst_port;
    new_stats.protocol = protocol;
    new_stats.status = 0;
    // tag 置空
    bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
}

SEC("xdp")
int xdp_ingress(struct xdp_md *ctx) {
    // 获取数据包边界
    void *data_end = (void *)(__u64)ctx->data_end;
    void *data = (void *)(__u64)ctx->data;
    
    bpf_printk("XDP: New packet received, size=%d bytes", data_end - data);
    
    // 生成唯一键
    int counter_key = 0;
    struct counter_val *val = bpf_map_lookup_elem(&packet_counter, &counter_key);
    u32 unique_key = 0;
    if (val) {
        bpf_spin_lock(&val->lock);
        unique_key = val->counter;
        val->counter++;
        bpf_spin_unlock(&val->lock);
    } else {
        // 初始化
        struct counter_val init_val = { .counter = 1, .lock = {0} };
        bpf_map_update_elem(&packet_counter, &counter_key, &init_val, BPF_ANY);
        unique_key = 0;
    }
    
    bpf_printk("XDP: Assigned unique_key=%u", unique_key);
    
    // 初始化统计结构
    struct nfs_op_stats new_stats = (struct nfs_op_stats){};
    new_stats.xid = 0; // 默认XID
    new_stats.timestamp = bpf_ktime_get_ns();
    new_stats.data_size = data_end - data;
    new_stats.protocol = 0; // 默认协议
    // IP和端口稍后设置

    // 统计接收的数据包大小
    int sz_key = RX_KEY;
    u64 skb_size = data_end - data;
    
    u64 *size_rx = bpf_map_lookup_elem(&size_map, &sz_key);
    if (size_rx == NULL) {
        u64 size_init = skb_size;
        bpf_map_update_elem(&size_map, &sz_key, &size_init, BPF_ANY);
    } else {
        *size_rx = *size_rx + skb_size;
    }

    // 检查数据包长度是否足够包含以太网和IP头部
    if (data + ETH_HLEN + IP_HLEN > data_end) {
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
        return XDP_PASS;
    }

    // 解析以太网头部
    struct ethhdr *eth = data;
    if (eth->h_proto != bpf_htons(ETH_P_IP)) {
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
        return XDP_PASS;
    }

    // 解析IP头部
    struct iphdr *iph = (struct iphdr *)(data + ETH_HLEN);
    if ((void *)(iph + 1) > data_end) {
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
        return XDP_PASS;
    }

    // 设置IP和协议
    new_stats.src_ip = bpf_ntohl(iph->saddr);
    new_stats.dst_ip = bpf_ntohl(iph->daddr);
    new_stats.protocol = iph->protocol;

    // 检查IP地址过滤
    u32 src_ip = new_stats.src_ip;
    u32 dst_ip = new_stats.dst_ip;
    if (!check_ip_filter(src_ip) && !check_ip_filter(dst_ip)) {
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
        return XDP_PASS;
    }

    // 检查协议类型
    u8 protocol = iph->protocol;
    if (!check_protocol_filter(protocol)) {
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
        return XDP_PASS;
    }

    // 计算IP头部实际长度（考虑IP选项）
    __u32 ip_hdr_len = iph->ihl * 4;
    if (ip_hdr_len < IP_HLEN) {
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
        return XDP_PASS;
    }

    // 处理TCP协议
    if (protocol == IPPROTO_TCP) {
        bpf_printk("Processing TCP packet: src=%u.%u.%u.%u dst=%u.%u.%u.%u", 
                   (src_ip>>24)&0xFF, (src_ip>>16)&0xFF, (src_ip>>8)&0xFF, src_ip&0xFF,
                   (dst_ip>>24)&0xFF, (dst_ip>>16)&0xFF, (dst_ip>>8)&0xFF, dst_ip&0xFF);
        
        if (data + ETH_HLEN + ip_hdr_len + TCP_HLEN > data_end) {
            bpf_printk("TCP packet too short for TCP header");
            // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }
        
        struct tcphdr *tcph = (struct tcphdr *)((void *)iph + ip_hdr_len);
        if ((void *)(tcph + 1) > data_end) {
            bpf_printk("TCP header extends beyond packet boundary");
            // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }

        u16 src_port = bpf_ntohs(tcph->source);
        u16 dst_port = bpf_ntohs(tcph->dest);
        new_stats.src_port = src_port;
        new_stats.dst_port = dst_port;
        
        bpf_printk("TCP packet: src_port=%d dst_port=%d", src_port, dst_port);
        
        // 检查端口过滤
        if (!check_port_filter(src_port, dst_port)) {
            bpf_printk("TCP packet filtered out by port filter: src=%d dst=%d", src_port, dst_port);
            // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }

        // 计算TCP头部长度
        __u32 tcp_hdr_len = tcph->doff * 4;
        if (tcp_hdr_len < TCP_HLEN) {
            // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }

        // 检查数据包总长度
        __u32 total_len = bpf_ntohs(iph->tot_len);
        __u32 data_len = total_len - ip_hdr_len - tcp_hdr_len;
        new_stats.data_size = data_len;
        
        bpf_printk("TCP data analysis: total_len=%d ip_hdr=%d tcp_hdr=%d data_len=%d", 
                   total_len, ip_hdr_len, tcp_hdr_len, data_len);
        
        if (data_len >= sizeof(struct rpc_call_head)) {
            bpf_printk("TCP packet has potential RPC data, checking...");
            // 计算RPC头部位置
            struct rpc_call_head *rpc_head = (struct rpc_call_head *)((void *)tcph + tcp_hdr_len);
            if ((void *)(rpc_head + 1) <= data_end) {
                u32 xid_raw = rpc_head->xid;
                u32 xid = bpf_ntohl(xid_raw);
                new_stats.xid = xid;
                bpf_printk("TCP RPC found: XID_raw=0x%x XID=%u, ports=%d->%d", 
                          xid_raw, xid, src_port, dst_port);
            } else {
                bpf_printk("TCP RPC header extends beyond packet boundary");
            }
        } else {
            bpf_printk("TCP packet too small for RPC: data_len=%d, need=%lu", 
                      data_len, sizeof(struct rpc_call_head));
        }
        
        // 更新映射
        bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
    }
    // 处理UDP协议
    else if (protocol == IPPROTO_UDP) {
        if (data + ETH_HLEN + ip_hdr_len + UDP_HLEN > data_end) {
            bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }
        
        struct udphdr *udph = (struct udphdr *)((void *)iph + ip_hdr_len);
        if ((void *)(udph + 1) > data_end) {
            bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }

        u16 src_port = bpf_ntohs(udph->source);
        u16 dst_port = bpf_ntohs(udph->dest);
        new_stats.src_port = src_port;
        new_stats.dst_port = dst_port;
        
        // 检查端口过滤
        if (!check_port_filter(src_port, dst_port)) {
            bpf_printk("UDP packet filtered out by port filter: src=%d dst=%d", src_port, dst_port);
            // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
            return XDP_PASS;
        }

        // 获取UDP数据长度
        __u32 data_len = bpf_ntohs(udph->len) - UDP_HLEN;
        new_stats.data_size = data_len;
        
        if (data_len >= sizeof(struct rpc_call_head)) {
            // 计算RPC头部位置
            struct rpc_call_head *rpc_head = (struct rpc_call_head *)((void *)udph + UDP_HLEN);
            if ((void *)(rpc_head + 1) <= data_end) {
                new_stats.xid = bpf_ntohl(rpc_head->xid);
            }
        }
        
        // 更新映射
        bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
    } else {
        // 对于其他协议，也记录
        new_stats.src_port = 0;
        new_stats.dst_port = 0;
        new_stats.xid = 0;
        // bpf_map_update_elem(&nfs_op_stats_map, &unique_key, &new_stats, BPF_ANY);
    }

    return XDP_PASS;
}

char __license[] SEC("license") = "GPL";