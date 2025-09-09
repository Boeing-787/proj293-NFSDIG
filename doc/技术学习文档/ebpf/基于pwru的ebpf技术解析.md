# 基于pwru的ebpf技术解析
由于我们都是ebpf技术小白，参考前人优秀的实现能够最大程度地提高我们的编程水平。与bcc和libbpf中的ebpf小工具相比，pwru是一个更加集成和复杂的ebpf工具，也是一个功能强大的ebpf框架。它提供了一个统一的接口来处理各种类型的ebpf程序，并且支持多种过滤条件，并且适用于容器场景。在nfs文件系统的应用场景中，很大一部分场景发生在容器中，随着云原生技术的应用渐渐深入和应用广泛，我们认为一个容器友好的ebpf工具是非常有必要的。因此，我们选择了pwru作为我们学习和开发自己的ebpf工具的基础。通过充分地利用pwru的功能，我们可以更好地理解和应用ebpf技术，开发出更加强大和灵活的工具。

## 统一函数进行条件过滤
`handle_everything` 函数是 `kprobe_pwru.c` 文件中的一个核心逻辑函数，其主要作用是对 `sk_buff`（即网络数据包）进行一系列的跟踪、过滤和输出处理，以决定是否需要记录该数据包的信息，并更新相关的 BPF 映射。
###  **函数签名与参数说明**

```c
static __noinline bool handle_everything(struct sk_buff *skb, void *ctx, struct event_t *event, u64 *_stackid, const bool is_kprobe)
```

| 参数名         | 类型             | 说明 |
|----------------|------------------|------|
| skb         | `struct sk_buff *` | 网络数据包结构体指针 |
| ctx        | `void *`         | eBPF 上下文（如寄存器信息等） |
| event       | `struct event_t *` | 输出事件结构体，用于存储 skb 的相关信息 |
| `_stackid`     | `u64 *`          | 可选栈 ID 指针，用于基于栈的追踪 |
| `is_kprobe`    | `const bool`     | 是否来自 kprobe 的调用 |


###  **函数功能解析**

####  **1. 初始化变量**
- 获取当前 [skb] 地址：`u64 skb_addr = (u64) skb;`
- 获取 `skb->head` 地址：`u64 skb_head = (u64) BPF_CORE_READ(skb, head);`
- 如果启用了基于栈 ID 的追踪，则获取或计算栈 ID：  
  ```c
  if (cfg->track_skb_by_stackid)
      stackid = _stackid ? *_stackid : get_stackid(ctx, is_kprobe);
  ```

####  **2. 根据配置判断是否追踪当前 skb**

##### a. **检查是否由 XDP 跟踪**
```c
if (cfg->track_xdp && cfg->track_skb) {
    if (bpf_map_lookup_elem(&xdp_dhs_skb_heads, &skb_head)) {
        tracked_by = TRACKED_BY_XDP;
        bpf_map_delete_elem(&xdp_dhs_skb_heads, &skb_head);
        goto cont;
    }
}
```
- 如果启用了 `track_xdp` 和 `track_skb`，并且 `skb_head` 存在于 `xdp_dhs_skb_heads` 中：
  - 认为该 skb 来自 XDP。
  - 设置 `tracked_by = TRACKED_BY_XDP`。
  - 删除该键值对并跳转到 [cont] 标签处执行后续操作。

##### b. **检查是否已被跟踪（通过 skb 地址）**
```c
if (cfg->track_skb && bpf_map_lookup_elem(&skb_addresses, &skb_addr)) {
    tracked_by = _stackid ? TRACKED_BY_STACKID : TRACKED_BY_SKB;
    goto cont;
}
```
- 如果启用了 `track_skb` 且 `skb_addresses` 中已存在该地址：
  - 若有 `_stackid`，则标记为 `TRACKED_BY_STACKID`。
  - 否则标记为 `TRACKED_BY_SKB`。
  - 跳转至 `cont` 执行后续操作。

##### c. **检查是否通过栈 ID 被跟踪**
```c
if (cfg->track_skb_by_stackid && bpf_map_lookup_elem(&stackid_skb, &stackid)) {
    tracked_by = TRACKED_BY_STACKID;
    goto cont;
}
```
- 如果启用了 `track_skb_by_stackid` 并且 `stackid_skb` 中存在该栈 ID：
  - 标记为 `TRACKED_BY_STACKID`。
  - 跳转至 `cont`。

##### d. **通过 filter 判断是否匹配规则**
```c
if (filter(skb)) {
    tracked_by = TRACKED_BY_FILTER;
    goto cont;
}
```
- 如果 `filter(skb)` 返回 true，表示该 skb 符合用户配置的过滤条件。
- 设置 `tracked_by = TRACKED_BY_FILTER`。
- 跳转至 `cont`。

##### e. **未命中任何追踪条件**
```c
return false;
```
- 如果上述所有条件都不满足，则返回 [false]，不继续处理。

---

####  **3. 执行 set_output 填充 event 数据**
```c
cont:
set_output(ctx, skb, event);
```
- 调用 `set_output()` 将 [skb] 的各种元数据填充进 [event]结构中，包括：
  - `meta`: 网络命名空间、接口索引、MTU、协议等。
  - `tuple`: IP 地址、端口、协议等。
  - `tunnel_tuple`: 隧道相关元组。
  - `print_skb_id` / `print_shinfo_id`: BTF 编码后的 skb/shinfo 内容。
  - `print_stack_id`: 当前调用栈 ID。
  - `cb`: 控制块信息。
  - `skb_metadata`: skb 元数据数组。

---

####  **4. 更新跟踪状态（可选）**

##### a. **添加 skb 到跟踪列表**
```c
if (cfg->track_skb && tracked_by == TRACKED_BY_FILTER) {
    bpf_map_update_elem(&skb_addresses, &skb_addr, &TRUE, BPF_ANY);
    if (cfg->track_xdp)
        bpf_map_update_elem(&xdp_dhs_skb_heads, &skb_head, &skb_addr, BPF_ANY);
}
```
- 如果是通过 [filter] 匹配的 skb，并且启用了 `track_skb`，则将其地址加入 `skb_addresses`。
- 如果启用 `track_xdp`，也将其头地址加入 `xdp_dhs_skb_heads`。

##### b. **维护基于栈 ID 的跟踪关系**
```c
if (cfg->track_skb_by_stackid && tracked_by != TRACKED_BY_STACKID) {
    u64 *old_stackid = bpf_map_lookup_elem(&skb_stackid, &skb);
    if (old_stackid && *old_stackid != stackid) {
        bpf_map_delete_elem(&stackid_skb, old_stackid);
    }
    bpf_map_update_elem(&stackid_skb, &stackid, &skb, BPF_ANY);
    bpf_map_update_elem(&skb_stackid, &skb, &stackid, BPF_ANY);
}
```
- 如果启用了 `track_skb_by_stackid`，并且不是通过栈 ID 匹配的：
  - 查看旧的栈 ID，如果存在且不同，则删除旧映射。
  - 添加新的栈 ID → skb 映射。
  - 同时更新 skb → 栈 ID 映射。

---

####  **5. 填充 event 的通用字段**
```c
event->pid = bpf_get_current_pid_tgid() >> 32;
event->ts = bpf_ktime_get_ns();
event->cpu_id = bpf_get_smp_processor_id();
```
- [pid]: 当前进程 PID。
- [ts]: 当前时间戳（纳秒）。
- [cpu_id]: 当前 CPU ID。

---

###  **返回值说明**
- 成功匹配并处理后返回 [true]。
- 否则返回 [false]，表示无需进一步处理。

####  主要功能点：

| 功能 | 描述 |
|------|------|
| 追踪机制 | 支持地址、栈 ID、XDP 头部、过滤器等多种追踪方式 |
| 过滤机制 | 使用 [filter(skb)] 对 skb 进行高级筛选 |
| 元数据收集 | 收集 skb 的 netns、协议、IP/端口、栈 ID 等信息 |
| 状态维护 | 更新 BPF map（如 `skb_addresses`, `stackid_skb` 等）以支持多次追踪 |
| 时间戳记录 | 记录事件发生的时间和 CPU 信息 |


## 获取ebpf跟踪程序地址进行符号解析
`get_addr` 函数的作用是**获取当前 eBPF 程序执行的指令地址（Instruction Pointer, IP）**，用于标识触发该事件的内核函数或调用位置。


###  **函数逻辑详解**

```c
static __always_inline u64 get_addr(void *ctx, const bool is_kprobe, const bool has_get_func_ip)
```

| 参数名             | 类型             | 说明 |
|--------------------|------------------|------|
| `ctx`            | `void *`         | eBPF 上下文指针（通常是 `struct pt_regs *`） |
| `is_kprobe`        | `const bool`     | 是否由 kprobe 触发 |
| `has_get_func_ip`  | `const bool`     | 是否支持使用 `bpf_get_func_ip()` 获取地址 |

####  情况一：支持 `bpf_get_func_ip()`
```c
if (has_get_func_ip) {
    ip = bpf_get_func_ip(ctx); /* endbr 已被 helper 处理 */
}
```
- 使用 BPF 辅助函数 `bpf_get_func_ip(ctx)` 直接获取调用地址。
- 这种方式适用于 fentry/fexit 等现代 BPF 程序类型，它能自动处理如 `endbr` 指令等对地址的影响。

####  情况二：不支持 `bpf_get_func_ip()`
```c
else 
    ip = is_kprobe ? PT_REGS_IP((struct pt_regs *) ctx) : get_func_ip();
```
- 如果是 kprobe：
  ```c
  ip = PT_REGS_IP((struct pt_regs *) ctx);
  ```
  - 从寄存器中直接读取程序计数器（IP）值。
- 否则（如 trampoline 或 fentry 等）调用 `get_func_ip()` 手动解析 IP 地址。

#####  架构相关修正（x86）
```c
#ifdef bpf_target_x86
	ip -= ENDBR_INSN_SIZE;	// 减去 endbr 指令长度
	ip -= is_kprobe;		// 如果是 kprobe，再减 1
#endif
```
- `ENDBR_INSN_SIZE`: x86 中的 `endbr64` 是一个 4 字节的指令，用于间接跳转的目标对齐。
- `is_kprobe`: 在 x86 上，kprobe 的回调地址会指向目标地址+1，因此需要减 1 来还原原始地址。

### 与libbpf-bootstrap的方法进行比较
| 方法         | 优点                                                                 | 缺点                                                                                 | 适用场景                |
|--------------|---------------------------------------------------------------------|--------------------------------------------------------------------------------------|-------------------------|
| **blazesym** | 1. 支持多种符号源（ELF、DWARF、内核、进程等）<br>2. 解析能力强大，支持C++/Rust等复杂符号<br>3. 代码现代、易扩展<br>4. 跨平台性好 | 1. 依赖Rust生态，需安装Rust工具链<br>2. 体积较大，部署复杂<br>3. 运行时依赖多，静态链接难度高 | 需要高级符号解析、跨平台、支持多语言符号的eBPF工具 |
| **kallsyms/libbpf** | 1. 只依赖C库，部署简单<br>2. 体积小，启动快<br>3. 直接读取内核符号，效率高<br>4. 适合嵌入式/生产环境 | 1. 仅支持内核符号，用户态符号支持有限<br>2. 复杂符号（如C++/Rust）支持较差<br>3. 解析能力有限 | 只需内核符号、追踪内核路径、对部署要求高的场景 |

#### 1. blazesym（Rust库）

**优点：**
- 功能强大，支持解析ELF、DWARF、内核、进程等多种符号源。
- 支持复杂语言（如C++、Rust）的符号解析，能还原出更详细的函数名、变量名等。
- 代码现代，易于维护和扩展，适合新项目和需要多语言支持的场景。

**缺点：**
- 依赖Rust工具链，部署环境需有Rust（cargo），对部分生产环境不友好。
- 体积较大，静态链接和跨平台部署难度较高。
- 运行时依赖多，可能引入额外的安全和维护成本。

#### 2. kallsyms/libbpf（C库）

**优点：**
- 只依赖C语言库（libbpf、libelf等），部署极其简单，适合生产环境和嵌入式设备。
- 体积小，启动快，资源消耗低。
- 直接读取内核符号表，效率高，适合内核追踪和调试。

**缺点：**
- 只能解析内核符号，对用户态程序、复杂语言（C++/Rust）支持有限。
- 解析能力有限，无法还原复杂的符号信息。
- 某些情况下（如内核开启了符号隐藏），解析能力会进一步受限。

#### 总结建议

- **如果你只做内核追踪、对部署和性能要求高，优先用kallsyms/libbpf。**
- **如果你需要支持多语言、用户态符号、复杂符号解析，且不介意Rust依赖，可以用blazesym。**

