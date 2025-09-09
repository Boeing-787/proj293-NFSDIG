# nfs与rpc状态转换详解

## 文件名获取
1. 获取 `struct file` 指针，从而获取dentry指针，在d_name字段中获取文件名

   ```c
   struct file *fp = BPF_CORE_READ(kiocb, ki_filp);
   fp = datap->fp;
   dentry = BPF_CORE_READ(fp, f_path.dentry);
   file_name = BPF_CORE_READ(dentry, d_name.name);
   bpf_probe_read_kernel_str(&event.file, sizeof(event.file), file_name);
   ```

## nfs读路径解析：
1. nfs_file_read处理一般读写流量
2. 当SYNC标记位未使用时，nfs_file_read调用：
   generic_file_read_iter()
   → filemap_read()
      → filemap_get_pages()
         → page_cache_sync_readahead() // 触发预读
         → __page_cache_alloc()        // 分配新页
         → mapping->a_ops->readpage()  // 调用文件系统特定方法
3.  RPC 调用与服务端交互
   nfs_initiate_pgio()
   → nfs_initiate_read()          // 初始化 RPC 请求
      → rpc_run_task()             // 异步提交到 RPC 队列
         → rpc_execute()             // 由rpc调度执行
            → xprt_transmit()          // 通过传输层发送（TCP/UDP）

   + RPC 层实现超时重传（xprt->ops->timer）
   + 可恢复错误（如网络闪断）自动重试最多 NFS_MAX_RPC_TIMEOUT 次
4. 总调用链：(直接IO)
   nfs_file_read()
   → nfs_file_direct_read()
      → nfs_direct_read_schedule_iovec()
         → nfs_pageio_complete()
            → nfs_pageio_doio()
               → nfs_initiate_pgio() // 往下就是rpc层，参考第4点

5. 总调用链：(非直接IO)
![alt text](buf_read_image.png)


## nfs写路径解析 nfs_file_write和nfs_writepages的区别：
+ nfs_file_write
直接响应用户空间 write() 系统调用，将数据写入页缓存（Page Cache），属于同步写入路径。

+ nfs_writepages
由内核的 pdflush 或 writeback 线程触发，异步将累积的脏页批量写入 NFS 服务端，属于后台回写路径。
nfs_writepages涉及到的主要函数包括：
![alt text](nfs_writepages.png)


## nfs错误捕捉机制：
NFS 内核错误捕捉机制通过 分层处理（RPC → NFS协议 → VFS）将底层网络或协议错误转换为应用层可理解的 POSIX 错误码，同时结合重试策略和日志系统，确保文件系统操作的鲁棒性和可调试性。理解这一机制对诊断网络文件系统问题（如超时、权限错误）至关重要。

   App->>VFS: read()
   VFS->>NFS: nfs_file_read()
   NFS->>RPC: 发送 RPC 请求
   RPC->>Server: NFS_READ
   Server-->>RPC: 返回错误码 NFS3ERR_STALE
   RPC->>NFS: 转换错误码 -ESTALE
   NFS->>VFS: 返回 -ESTALE
   VFS->>App: 返回 -ESTALE


## RPC task结构分析

[rpc调用过程分析](https://cloud.tencent.com/developer/article/2372669)
### tk_status字段的取值：
在 NFS/RPC 的上下文中，`task->tk_status` 是一个表示 RPC 任务执行状态的整型字段。它通常用于记录当前 RPC 任务的执行结果或错误码。

| 值 | 含义 | 说明 |
|----|------|------|
| `0` | 成功 | 操作正常完成 |
| `-EACCES` | 权限不足 | 拒绝访问目标资源 |
| `-ENOENT` | 文件不存在 | 请求的目标文件/目录不存在 |
| `-ENOMEM` | 内存不足 | 分配内存失败 |
| `-ENETUNREACH` | 网络不可达 | 无法连接到服务端 |
| `-ECONNREFUSED` | 连接被拒绝 | 服务端未响应或端口未开放 |
| `-ETIMEDOUT` | 超时 | RPC 请求超时（可能重试） |
| `-ESTALE` | 句柄过期 | NFS 文件句柄失效，需要重新挂载或 revalidate |
| `-ERESTARTSYS` | 系统调用被中断 | 任务被信号中断（如 Ctrl+C） |
| `-EIO` | I/O 错误 | 通用 I/O 故障（如网络断开、磁盘故障等） |
| `-EFAULT` | 地址错误 | 内核访问非法地址 |
| `-EINVAL` | 参数无效 | 传递了不合法参数 |
| `-EAGAIN` | 资源暂时不可用 | 表示可以稍后重试 |

> `tk_status` 与 Linux 内核中的标准错误码一致，定义在 `<linux/errno.h>` 或对应架构头文件中。

---

### `struct rpc_task` 结构体字段详解

以下是 `rpc_task` 结构体各字段的作用和含义：

#### 🔹 引用计数 & 状态
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `tk_count` | `atomic_t` | 引用计数器，用于管理该任务的生命周期（原子操作） |
| `tk_status` | `int` | 当前任务的状态（成功、错误码等） |
| `tk_rpc_status` | `int` | 上一次 RPC 操作的结果（独立于 `tk_status`） |

#### 🔹 任务调度相关
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `tk_task` | `struct list_head` | 全局任务链表节点，用于链接所有 RPC 任务 |
| `tk_callback` | `void (*)(struct rpc_task *)` | 回调函数，在任务唤醒后执行 |
| `tk_action` | `void (*)(struct rpc_task *)` | 下一步要执行的操作函数（异步任务） |
| `tk_timeout` | `unsigned long` | 超时时间（单位：jiffies），用于 `rpc_sleep()` |
| `tk_runstate`| `unsigned long` | 任务运行状态标志位（如是否正在运行、等待等） |

#### 🔹 等待队列 & 工作队列
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `tk_waitqueue` | `struct rpc_wait_queue *` | 任务所在的等待队列 |
| `u.tk_work` | `struct work_struct` | 异步任务的工作结构体（用于工作队列） |
| `u.tk_wait` | `struct rpc_wait` | 同步等待结构体 |

#### 🔹 RPC 请求信息
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `tk_msg` | `struct rpc_message` | RPC 请求的消息结构（包含请求体、应答体等） |
| `tk_calldata`| `void *` | 用户自定义数据（由调用者传入） |
| `tk_ops` | `const struct rpc_call_ops *` | 调用者的回调函数集合（如 `rpc_call_done`, `rpc_release`） |
| `tk_client` | `struct rpc_clnt *` | 指向当前 RPC 客户端 |
| `tk_xprt` | `struct rpc_xprt *` | 指向传输层实例（TCP/UDP） |
| `tk_op_cred` | `struct rpc_cred *` | 当前操作使用的凭证 |
| `tk_rqstp`| `struct rpc_rqst *` | 当前请求对应的 `rpc_rqst` 结构（含 XID 等信息） |

#### 🔹 执行环境 & 调度
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `tk_workqueue` | `struct workqueue_struct *` | 任务所属的工作队列（通常是 `rpciod`） |
| `tk_start`| `ktime_t` | 任务开始时间戳 |
| `tk_owner` | `pid_t` | 任务所属进程 PID |
| `tk_flags` | `unsigned short` | 任务标志位（如 `RPC_TASK_ASYNC`, `RPC_TASK_SOFT` 等） |
| `tk_timeouts` | `unsigned short` | 超时次数统计 |
| `tk_pid` | `unsigned short` | 调试用途的 PID 标识 |
| `tk_priority` | `unsigned char:2` | 任务优先级（低、中、高） |
| `tk_garb_retry` | `unsigned char:2` | 渣回收重试次数 |
| `tk_cred_retry` | `unsigned char:2` | 凭证获取重试次数 |

---
#### 在 eBPF 中的应用：
- 跟踪 `tk_status` 可以分析 NFS 请求的成功率、错误类型。
- 配合 `tk_start` 和当前时间戳可计算 RPC 延迟。

## rpc 调用过程分析
根据提供的链接文章《[RPC 调用过程分析](https://cloud.tencent.com/developer/article/2372669)》，结合 Linux 内核中 RPC 子系统的实现，本文将结构化阐述 **RPC 状态管理机制**，并基于 eBPF 技术提出观测与跟踪建议。

---

##  一、RPC 状态管理机制详解

### 1. **RPC 任务状态流转**

`struct rpc_task` 是内核中用于描述一次 RPC 请求的核心结构体。它通过 `tk_status` 和 `tk_runstate` 字段来维护任务的状态信息。

####  主要状态字段：

| 字段名 | 类型 | 含义 |
|--------|------|------|
| `tk_status` | int | 当前任务的执行结果或错误码（如 `0`, `-ETIMEDOUT`, `-ESTALE`） |
| `tk_runstate` | unsigned long | 表示任务运行状态标志位（如 `RPC_TASK_RUNNING`, `RPC_TASK_QUEUED`） |

####  状态流转流程：
```
INITIAL → ALLOCATED → BOUND → ENCODED → SENT → RECEIVED → DECODED → FINISHED
```

- **INITIAL**：任务初始化阶段；
- **ALLOCATED**：分配了请求结构 (`rpc_rqst`)；
- **BOUND**：绑定到传输层（TCP/UDP）；
- **ENCODED**：请求数据已编码为 XDR 格式；
- **SENT**：请求已发送；
- **RECEIVED**：接收到响应；
- **DECODED**：响应数据已解码；
- **FINISHED**：任务结束，调用 `tk_callback` 回馈用户。

---

### 2. **RPC 超时与重试机制**

RPC 使用 `tk_timeout` 控制每个步骤的最大等待时间，并通过 `tk_timeouts` 记录超时次数。

####  超时处理逻辑：
- 每次超时后，`tk_timeouts++`；
- 若未超过最大限制（如 NFSv4 的 `NFS_MAX_RPC_TIMEOUT`），则重试；
- 若达到上限，则设置 `tk_status = -ETIMEDOUT` 并终止任务。

####  常见可恢复错误：
| 错误码 | 含义 | 是否可重试 |
|--------|------|------------|
| `-EIO` | 一般 I/O 错误 | ✅ |
| `-ETIMEDOUT` | 超时 | ✅ |
| `-ECONNREFUSED` | 连接被拒绝 | ✅ |
| `-ESTALE` | 文件句柄过期 | ❌ |
| `-ENOENT` | 文件不存在 | ❌ |
| `-EACCES` | 权限不足 | ❌ |

---

### 3. **异步 vs 同步任务**

| 类型 | 特点 | 示例 |
|------|------|------|
| 同步任务 | 阻塞当前线程直到完成 | `nfs_getattr()` 获取文件属性 |
| 异步任务 | 由 `workqueue` 异步执行 | `nfs_readpage()` 异步读取页缓存 |

异步任务使用 `tk_action` 函数指针定义下一步操作，例如：
- `rpc_call_start`
- `rpc_call_encode`
- `rpc_call_decode`
- `nfs4_run_state_manager`

---

### 4. **RPC 任务调度模型**

RPC 任务由 `rpciod` 工作队列统一调度执行：

```
User App -> VFS -> NFS -> RPC -> Schedule Task (on rpciod)
                             ↓
                     Run tk_action()
                             ↓
                     Execute RPC Request
                             ↓
                     Handle Response / Error
```

---

## 二、eBPF 观测与跟踪建议

### 1. **核心可观测指标**
以下为建议在 eBPF 中追踪的关键指标：

| 指标 | 说明 |
|------|------|
| RPC 请求延迟 | [start_time](file:///home/lll/bpfnfs/bpf/utils.h#L72-L72) 到 [end_time](file:///home/lll/bpfnfs/bpf/utils.h#L73-L73) 的差值 |
| 成功/失败率 | 统计 `tk_status == 0` 的比例 |
| 超时次数 | 统计 `tk_status == -ETIMEDOUT` 的频率 |
| 重试次数 | `tk_timeouts` 字段统计 |
| 协议错误分布 | 如 `-ESTALE`, `-EACCESS`, `-ENOENT` 等错误分类统计 |

---


---

### 3. **观测维度设计**

####  1. **按进程观测**
- 跟踪每个进程发起的 RPC 请求数量、平均延迟、错误率等。
- 使用 `pid` 作为 key 存入 map。

####  2. **按操作类型观测**
- 区分 `READ`, `WRITE`, `LOOKUP`, `GETATTR` 等操作；
- 可以使用 `op_type` 枚举区分不同 NFS 操作；
- 支持聚合统计（如总请求数、平均延迟、错误数）。

####  3. **延迟直方图**
- 使用 `bpf_perf_event_output()` 或自定义环形缓冲区记录每次 RPC 的耗时；
- 在用户空间绘制延迟分布图。

####  4. **错误码分布**
- 将 `tk_status` 值映射为字符串名称（如 `-ETIMEDOUT`, `-ESTALE`）；
- 统计各类错误的发生频次。

---

### 4. **推荐 eBPF Map 设计**

| Map 名称 | 类型 | Key | Value | 用途 |
|----------|------|-----|-------|------|
| `rpc_start_times` | HASH | `u32 pid` | `ktime_t` | 记录每个进程的 RPC 开始时间 |
| `rpc_latency_hist` | ARRAY | `u32 slot` | `u64 count` | 延迟直方图 |
| `error_count_map` | HASH | `int error_code` | `u64 count` | 错误码统计 |
| `nfs_op_latencies` | PERCPU_HASH | `enum op_type` | `struct lat_stat`（min/max/avg/count） | 按 NFS 操作类型统计延迟 |

---

### 5. **用户态工具建议**

####  用户态采集器可以使用如下方式：
- **libbpf + CO-RE** 实现零侵入式监控；
- **perf buffer / ring buffer** 上报事件；
- **Prometheus + Grafana** 展示实时监控面板；
- **ebpf_exporter** 对接 Prometheus；
- **CLI 工具**（如 `bpftrace`, `bpftool`）进行快速调试。

---

##  三、典型观测场景示例

### 场景 1：查看某进程的 RPC 延迟分布
```bash
PID: 1234
Total RPCs: 1000
Average Latency: 2.5ms
P99 Latency: 15ms
Error Rate: 0.2%
```

### 场景 2：统计 ESTALE 错误发生情况
```bash
Error Code: -ESTALE
Count: 23
Last Seen: 12s ago
```

### 场景 3：按操作类型统计平均延迟
| Op Type | Count | Avg Latency (us) | P99 Latency (us) |
|---------|-------|------------------|-------------------|
| READ    | 1500  | 800              | 3000              |
| WRITE   | 800   | 1200             | 4500              |
| LOOKUP  | 500   | 200              | 1000              |
| GETATTR | 700   | 150              | 800               |

---

##  四、总结

###  RPC 状态管理机制核心要点
- 使用 `tk_status` 跟踪执行结果；
- 通过 `tk_runstate` 管理任务生命周期；
- 支持同步与异步两种模式；
- 具备自动重试机制（如网络闪断）；
- 失败任务返回 POSIX 错误码供上层识别。

###  eBPF 监控建议
- 使用 `tracepoint/sunrpc/rpc_task_begin` 和 `rpc_task_end` 跟踪任务生命周期；
- 结合 [kprobe](file:///home/lll/go/pkg/mod/github.com/cilium/ebpf@v0.18.0/link/kprobe.go#L146-L203) 捕获关键函数入口；
- 通过 [map](file:///home/lll/anaconda3/include/fmt/ranges.h#L519-L519) 统计错误码、延迟、请求类型；
- 用户态使用 `libbpf` + `CO-RE` 快速构建观测系统；
- 可视化展示：延迟直方图、错误热力图、按 PID 分布等。

