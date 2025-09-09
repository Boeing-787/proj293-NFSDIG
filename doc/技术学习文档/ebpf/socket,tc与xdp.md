## Socket Filter vs TC vs XDP 插桩点对比

### 1. **Socket Filter 插桩点** 

#### 优势：
- **应用层可见性**：能够看到经过 socket 层的所有数据包，包括本地生成和接收的数据包
- **完整的协议栈信息**：可以访问到完整的网络协议栈上下文，包括 socket 状态、用户空间信息等
- **用户空间集成**：直接与用户空间应用程序集成，便于数据传递和处理
- **细粒度控制**：可以基于具体的 socket 连接进行过滤和处理
- **低开销**：相比 XDP 和 TC，在 socket 层的开销相对较小

#### 特点：
- 插桩点在 socket 层，数据包已经经过完整的网络协议栈处理
- 可以访问 `skb->pkt_type`、`skb->ifindex` 等 socket 相关信息
- 适合应用层网络监控和调试

#### 实例：
```
SEC("socket")
int socket_handler(struct __sk_buff *skb)
{
	struct so_event *e;
	__u8 verlen;
	__u16 proto;
	__u32 nhoff = ETH_HLEN;

	bpf_skb_load_bytes(skb, 12, &proto, 2);
	proto = __bpf_ntohs(proto);
	if (proto != ETH_P_IP)
		return 0;

	if (ip_is_fragment(skb, nhoff))
		return 0;

	/* reserve sample from BPF ringbuf */
	e = bpf_ringbuf_reserve(&rb, sizeof(*e), 0);
	if (!e)
		return 0;

	bpf_skb_load_bytes(skb, nhoff + offsetof(struct iphdr, protocol), &e->ip_proto, 1);

	if (e->ip_proto != IPPROTO_GRE) {
		bpf_skb_load_bytes(skb, nhoff + offsetof(struct iphdr, saddr), &(e->src_addr), 4);
		bpf_skb_load_bytes(skb, nhoff + offsetof(struct iphdr, daddr), &(e->dst_addr), 4);
	}

	bpf_skb_load_bytes(skb, nhoff + 0, &verlen, 1);
	bpf_skb_load_bytes(skb, nhoff + ((verlen & 0xF) << 2), &(e->ports), 4);
	e->pkt_type = skb->pkt_type;
	e->ifindex = skb->ifindex;
	bpf_ringbuf_submit(e, 0);

	return skb->len;
}

```

### 2. **TC (Traffic Control) 插桩点**
The TC subsystem is intended to regulate how network traffic is scheduled.
For example, you might want to limit the bandwidth available to each
application so that they all get a fair chance. But when you’re looking at
scheduling individual packets, bandwidth isn’t a terribly meaningful term, as
it’s used for the average amount of data being sent or received. A given
application might be very bursty, or another application might be very
sensitive to network latency, so TC gives much finer control over the way
packets are handled and prioritized

#### 优势：
- **网络层处理**：在网络协议栈的中间层进行拦截，可以修改数据包
- **灵活的位置**：可以在 ingress（入站）和 egress（出站）两个方向进行拦截
- **QoS 控制**：天然支持流量控制和 QoS 功能
- **数据包修改**：可以修改数据包内容、重定向、丢弃等,直接操作内核数据结构sk_buff

#### 特点：
- 插桩点在网络层，数据包已经经过 MAC 层处理但还未到达 socket 层
- 可以访问网络层头部信息，但无法直接访问 socket 层信息
- 适合网络流量控制、负载均衡、防火墙等功能


#### 示例：
```
SEC("tc")
int tc_ingress(struct __sk_buff *ctx)
{
	void *data_end = (void *)(__u64)ctx->data_end;
	void *data = (void *)(__u64)ctx->data;
	struct ethhdr *l2;
	struct iphdr *l3;

	if (ctx->protocol != bpf_htons(ETH_P_IP))
		return TC_ACT_OK;

	l2 = data;
	if ((void *)(l2 + 1) > data_end)
		return TC_ACT_OK;

	l3 = (struct iphdr *)(l2 + 1);
	if ((void *)(l3 + 1) > data_end)
		return TC_ACT_OK;

	bpf_printk("Got IP packet: tot_len: %d, ttl: %d", bpf_ntohs(l3->tot_len), l3->ttl);
	return TC_ACT_OK;
}
```

### 3. **XDP (eXpress Data Path) 插桩点**

#### 优势：
- **最高性能**：在网络驱动层直接处理，性能最优
- **早期拦截**：在网络协议栈的最早期进行拦截，可以避免不必要的处理开销
- **硬件卸载**：支持网卡硬件卸载，进一步提升性能
- **DDoS 防护**：能够快速丢弃恶意数据包，有效防护 DDoS 攻击

#### 特点：
- 插桩点在网络驱动层，数据包刚到达网卡就开始处理
- 只能访问数据包原始内容，无法访问网络协议栈的上下文信息
- 适合高性能网络处理、DDoS 防护、负载均衡等场景

#### 示例：
```
unsigned char lookup_protocol(struct xdp_md *ctx)
{
    unsigned char protocol = 0;
    void *data = (void *)(long)ctx->data;                             
    void *data_end = (void *)(long)ctx->data_end;
    struct ethhdr *eth = data;                                        
    if (data + sizeof(struct ethhdr) > data_end)                      
        return 0;
    // Check that it's an IP packet
    if (bpf_ntohs(eth->h_proto) == ETH_P_IP)                          
    {
        // Return the protocol of this packet
        // 1 = ICMP
        // 6 = TCP
        // 17 = UDP       
        struct iphdr *iph = data + sizeof(struct ethhdr);             

        if (data + sizeof(struct ethhdr) + sizeof(struct 
    iphdr) <= data_end) 
            protocol = iph->protocol;                                 
    }
    return protocol;
}
```

## 具体对比分析

### 性能对比：
```
XDP > TC > Socket Filter
```

### 功能丰富度：
```
Socket Filter > TC > XDP
```

### 使用场景：

| 插桩点 | 适用场景 | 不适用场景 |
|--------|----------|------------|
| **Socket Filter** | 应用层监控、调试、协议分析 | 高性能网络处理、DDoS防护 |
| **TC** | 流量控制、负载均衡、网络策略 | 应用层调试、socket状态分析 |
| **XDP** | 高性能处理、DDoS防护、负载均衡 | 应用层监控、复杂协议分析 |

### 当前 Socket Filter 代码的优势：

1. **完整的网络信息**：可以获取到 `pkt_type`、`ifindex` 等 socket 层特有的信息
2. **应用层集成**：通过 Ring Buffer 直接与用户空间应用通信
3. **协议栈完整性**：数据包已经经过完整的协议栈处理，信息更丰富
4. **调试友好**：适合网络应用的调试和监控

总的来说，Socket Filter 插桩点在**应用层网络监控和调试**方面具有独特优势，而 XDP 和 TC 更适合**网络层面的高性能处理**。选择哪种插桩点主要取决于具体的应用场景和性能需求。