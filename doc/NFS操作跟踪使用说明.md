# NFS操作跟踪功能使用说明

## 概述

本功能基于eBPF技术，通过kprobe和kretprobe来跟踪NFS服务器端的各种操作，包括基础NFSv4操作、NFSv4.1会话管理操作、NFSv4.2新特性操作等。

## 功能特性

### 1. 支持的操作类型

#### 基础NFSv4操作
- **文件操作**: ACCESS, CLOSE, COMMIT, CREATE, GETATTR, READ, WRITE, OPEN
- **目录操作**: LOOKUP, READDIR, MKDIR, RMDIR
- **文件句柄操作**: GETFH, PUTFH, PUTROOTFH
- **锁定操作**: LOCK, LOCKT, LOCKU
- **其他操作**: LINK, REMOVE, RENAME, SETATTR, VERIFY等

#### NFSv4.1操作
- **会话管理**: CREATE_SESSION, DESTROY_SESSION, SEQUENCE
- **客户端管理**: EXCHANGE_ID, SETCLIENTID, DESTROY_CLIENTID
- **状态管理**: TEST_STATEID, FREE_STATEID
- **pNFS支持**: LAYOUTGET, LAYOUTCOMMIT, LAYOUTRETURN

#### NFSv4.2操作
- **存储管理**: ALLOCATE, DEALLOCATE, CLONE, COPY
- **扩展属性**: GETXATTR, SETXATTR, LISTXATTRS, REMOVEXATTR
- **高级功能**: SEEK, OFFLOAD_STATUS, OFFLOAD_CANCEL

### 2. 数据结构

#### nfsd_op_stats
```c
struct nfsd_op_stats {
    u64 latency;           // 操作延迟（纳秒）
    u64 timestamp;         // 时间戳
    u32 pid;              // 进程ID
    u32 xid;              // 事务ID
    enum nfsd_op_type op; // 操作类型
    char comm[TASK_COMM_LEN]; // 进程名
    char tag[MAX_PROCDURE_LEN]; // 操作标签
};
```

#### nfsd_compound_info
```c
struct nfsd_compound_info {
    u32 xid;              // 复合操作的事务ID
    u32 opcnt;            // 操作数量
    char tag[MAX_PROCDURE_LEN]; // 操作标签
    u64 timestamp;        // 时间戳
    u32 pid;              // 进程ID
};
```

## 使用方法

### 1. 编译BPF程序

```bash
# 编译BPF程序
make -C bpf/

# 或者使用clang直接编译
clang -O2 -target bpf -c nfs_trace.c -o nfs_trace.o
```

### 2. 加载和运行

```bash
# 加载BPF程序
sudo bpftool prog load nfs_trace.o /sys/fs/bpf/nfs_trace

# 附加kprobe
sudo bpftool kprobe add nfsd4_access entry /sys/fs/bpf/nfs_trace trace_entry_nfsd4_access
sudo bpftool kprobe add nfsd4_access exit /sys/fs/bpf/nfs_trace trace_exit_nfsd4_access

# 查看已附加的kprobe
sudo bpftool kprobe list
```

### 3. 监控数据

```bash
# 查看NFS操作事件
sudo bpftool map dump name nfsd_op_events

# 查看复合操作信息
sudo bpftool map dump name nfsd_compound_starts
```

## 配置选项

### 1. 过滤进程
可以通过设置`filter_pid`来只跟踪特定进程的NFS操作：

```c
volatile const __u32 filter_pid = 12345; // 只跟踪PID为12345的进程
```

### 2. 选择操作类型
可以通过修改`TrackNfsdProgs`数组来选择要跟踪的操作类型：

```go
var TrackNfsdProgs = []TraceProg{
    // 只跟踪基础操作
    {
        Type:    "kprobe",
        Details: KprobeProg{Symbol: "nfsd4_read"},
    },
    {
        Type:    "kretprobe",
        Details: KprobeProg{Symbol: "nfsd4_read"},
    },
    // ... 其他操作
}
```

## 性能考虑

### 1. 内存使用
- `nfsd_op_starts`: 哈希表，存储操作开始信息
- `nfsd_op_events`: 队列，存储操作完成事件
- `nfsd_compound_starts`: 哈希表，存储复合操作信息

### 2. 性能影响
- 每个NFS操作都会触发两次eBPF程序执行（入口和退出）
- 建议在生产环境中谨慎使用，避免影响NFS性能
- 可以通过采样率控制来减少性能影响

## 故障排除

### 1. 常见问题

#### kprobe附加失败
```bash
# 检查内核符号是否存在
sudo cat /proc/kallsyms | grep nfsd4_access

# 检查内核版本兼容性
uname -r
```

#### 数据不完整
- 检查BPF maps是否正确创建
- 验证kprobe是否正确附加
- 检查内核日志中的错误信息

### 2. 调试技巧

```bash
# 启用BPF调试信息
echo 1 > /sys/kernel/debug/bpf/verifier_log_level

# 查看BPF程序加载状态
sudo bpftool prog list

# 查看BPF maps状态
sudo bpftool map list
```

## 扩展开发

### 1. 添加新的操作类型
1. 在`nfsd_op_type`枚举中添加新类型
2. 在`get_nfsd_op_type`函数中添加名称匹配
3. 创建对应的kprobe函数
4. 在`TrackNfsdProgs`中添加配置

### 2. 自定义数据处理
可以修改`trace_nfsd_op_entry`和`trace_nfsd_op_exit`函数来添加自定义的数据处理逻辑。

## 注意事项

1. **内核版本要求**: 需要支持eBPF的Linux内核（4.4+）
2. **权限要求**: 需要root权限来加载和运行BPF程序
3. **稳定性**: 在生产环境中使用前请充分测试
4. **兼容性**: 不同内核版本的NFS实现可能有差异

## 相关文档

- [eBPF官方文档](https://ebpf.io/)
- [Linux内核NFS文档](https://www.kernel.org/doc/html/latest/filesystems/nfs/)
- [BPF工具使用指南](https://github.com/libbpf/libbpf)
