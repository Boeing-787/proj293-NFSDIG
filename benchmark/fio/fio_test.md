# FIO 性能测试工具完整指南

这是一个基于 FIO 的存储性能测试工具，提供了多种预设的测试场景，用于评估 NFS 或其他存储系统的性能。

## 安装依赖

### 系统要求
- Ubuntu 18.04+ / CentOS 7+ / RHEL 7+
- Python 3.6+
- 至少 2GB 可用内存
- 至少 10GB 可用磁盘空间

### 安装 FIO

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install fio

# CentOS/RHEL
sudo yum install fio

# 或者从源码编译（推荐最新版本）
git clone https://github.com/axboe/fio.git
cd fio
./configure
make && sudo make install
```

### 验证安装

```bash
# 检查fio版本
fio --version

# 检查可用引擎
fio --enghelp
```

## 关键参数详解

### 基础参数
- **--name**: 测试任务名称，用于标识不同的测试
- **--directory**: 测试目录路径（需提前创建）
- **--size**: 每个线程生成的文件大小
  - 常用值：1M, 10M, 100M, 1G, 10G
  - 特殊值：0（表示使用整个设备）
- **--rw**: I/O 模式
  - `read`: 顺序读
  - `write`: 顺序写
  - `randread`: 随机读
  - `randwrite`: 随机写
  - `rw`: 顺序读写混合
  - `randrw`: 随机读写混合
  - `trim`: 擦除操作
- **--bs**: 块大小
  - 小文件：512B, 1k, 4k, 8k
  - 大文件：16k, 32k, 64k, 128k, 256k, 512k, 1M, 2M, 4M
- **--direct**: 是否绕过缓存
  - `0`: 使用系统缓存
  - `1`: 直接I/O，绕过缓存
- **--numjobs**: 并发线程数
  - 常用值：1, 2, 4, 8, 16, 32, 64
- **--runtime**: 测试运行时间（秒）
  - 常用值：30, 60, 300, 600, 1800
- **--ioengine**: I/O 引擎
  - `libaio`: Linux异步I/O引擎（推荐）
  - `sync`: 同步I/O引擎
  - `psync`: 预读同步I/O
  - `vsync`: 向量同步I/O
  - `posixaio`: POSIX异步I/O

### 高级参数
- **--iodepth**: I/O队列深度（异步引擎）
  - 常用值：1, 4, 8, 16, 32, 64, 128
- **--time_based**: 基于时间运行而非基于大小
- **--group_reporting**: 合并报告所有线程的结果
- **--output**: 输出结果到文件
- **--output-format**: 输出格式（normal, json, json+）
- **--random_distribution**: 随机分布类型
  - `random`: 均匀分布
  - `zipf`: 齐普夫分布
  - `pareto`: 帕累托分布
- **--percentage_random**: 随机I/O的百分比（混合模式）

## 使用方法

### 基本用法

```bash
# 使用默认参数运行简单测试
python3 fio.py

# 指定测试场景和挂载目录
python3 fio.py --scene fileserver --mnt /mnt/nfs_test

# 查看帮助信息
python3 fio.py --help
```

### 测试场景说明

| 场景 | 描述 | 适用场景 |
|------|------|----------|
| `simple_test` | 基础性能测试 | 快速验证存储性能 |
| `tiny_file` | 小文件测试 | 文件系统小文件性能 |
| `libaio` | 异步I/O测试 | 高性能异步I/O场景 |
| `sync` | 同步I/O测试 | 同步I/O性能对比 |
| `fileserver` | 文件服务器场景 | 文件服务器工作负载 |
| `webserver` | Web服务器场景 | Web应用存储性能 |
| `mailserver` | 邮件服务器场景 | 邮件系统存储性能 |

### 挂载目录选项

- `/mnt/nfs_test`: 标准NFS测试目录
- `~/nfs`: 用户目录下的NFS测试目录

## 使用方式

### 1. 命令行方式

#### 基础顺序读测试
```bash
fio --name=seq_read --directory=/path/to/test --size=1G --rw=read --bs=4k --direct=1 --numjobs=4 --runtime=60
```

#### 随机读写混合测试
```bash
fio --name=rand_rw --directory=/path/to/test --size=1G --rw=randrw --bs=4k --direct=1 --numjobs=8 --iodepth=16 --runtime=300 --percentage_random=70
```

#### 大块顺序写测试
```bash
fio --name=seq_write --directory=/path/to/test --size=10G --rw=write --bs=1M --direct=1 --numjobs=4 --runtime=180
```

### 2. 配置文件方式

#### 创建配置文件 test.fio
```ini
[global]
directory=/path/to/test
direct=1
group_reporting=1
time_based=1
runtime=60

[seq_read]
name=sequential_read
rw=read
bs=4k
size=1G
numjobs=4

[rand_write]
name=random_write
rw=randwrite
bs=4k
size=1G
numjobs=8
iodepth=16
```

#### 运行配置文件
```bash
fio test.fio
```

## 配置文件说明

每个测试场景都有对应的 `.fio` 配置文件：

- `simple_test.fio`: 基础读写测试
- `tiny_file.fio`: 小文件性能测试
- `libaio.fio`: 异步I/O性能测试
- `sync.fio`: 同步I/O性能测试
- `fileserver.fio`: 文件服务器工作负载
- `webserver.fio`: Web服务器工作负载
- `mailserver.fio`: 邮件服务器工作负载

### 直接使用配置文件

```bash
# 直接运行特定配置文件
fio simple_test.fio

# 指定输出文件
fio simple_test.fio --output=results.txt

# JSON格式输出
fio simple_test.fio --output-format=json --output=results.json
```

## 性能指标详解

### 关键指标
- **IOPS**: 每秒I/O操作数
- **Bandwidth**: 带宽（MB/s）
- **Latency**: 延迟（us/ms）
  - min: 最小延迟
  - max: 最大延迟
  - mean: 平均延迟
  - stddev: 标准差

### 性能评估
- **高IOPS**: 适合随机小文件操作
- **高带宽**: 适合大文件顺序操作
- **低延迟**: 适合实时应用
- **一致性**: 标准差越小越好

## 典型性能参考

### 理论性能区间

| 存储类型 | 随机读IOPS | 顺序读带宽 | 随机写IOPS | 顺序写带宽 |
|----------|------------|------------|------------|------------|
| SATA SSD | 50K-100K | 500-550 MB/s | 30K-80K | 400-500 MB/s |
| NVMe SSD | 500K-1M | 2-7 GB/s | 300K-800K | 1.5-6 GB/s |
| HDD | 100-200 | 150-200 MB/s | 100-200 | 100-150 MB/s |

### 本机典型结果

系统信息：
> Linux shasha-ThinkCentre-M720t-D418 6.8.0-41-generic #41-Ubuntu SMP PREEMPT_DYNAMIC Fri Aug  2 20:41:06 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux
> Intel(R) Core(TM) i7-8700 CPU @ 3.20GHz，39 bits physical, 48 bits virtual，Little Endian, 6核12线程
> Mem:15G, Swap:4G 
> nfs导出目录对应的磁盘：Disk model: SAMSUNG MZVLB256HBHQ-000L7；Units: sectors of 1 * 512 = 512 bytes；Sector size (logical/physical): 512 bytes / 512 bytes；I/O size (minimum/optimal): 512 bytes / 512 bytesDisklabel type: gpt；Disk identifier: E68868F8-478A-4401-895F-879CAD53AED8
> 对应文件系统：ext4

**典型性能（simple_test环回测试**
```
mpstat:
%usr   %nice    %sys %iowait    %irq   %soft  %steal  %guest  %gnice   %idle
0.17    0.00    4.49   13.81    0.00    2.63    0.00    0.00    0.00   78.90

r/s     rkB/s   rrqm/s  %rrqm r_await rareq-sz     w/s     wkB/s   wrqm/s  %wrqm w_await wareq-sz     d/s     dkB/s   drqm/s  %drqm d_await dareq-sz     f/s f_await  aqu-sz  %util
536.00   6016.00     0.00   0.00    0.37    11.22 1916.00  20312.00  3162.00  62.27    0.61    10.60    0.00      0.00     0.00   0.00    0.00     0.00  328.00    0.91    1.66  68.20

nfsiostat:
read:              ops/s            kB/s           kB/op         retrans    avg RTT (ms)    avg exe (ms)  avg queue (ms)          errors
                2690.000       11579.609           4.305        0 (0.0%)           2.858           2.914           0.034        0 (0.0%)
write:             ops/s            kB/s           kB/op         retrans    avg RTT (ms)    avg exe (ms)  avg queue (ms)          errors
                1328.000        5737.375           4.320        0 (0.0%)           5.880           5.950           0.039        0 (0.0%)
```

simple_test分析：
CPU瓶颈分析：
  1. 用户空间CPU: 0.17% - 极低
  2. 系统空间CPU: 4.49% - 较低
  3. I/O等待时间: 13.81% - 中等偏高
  4. 空闲时间: 78.90% - 充足
  5. 软中断: 2.63% - 正常
本地磁盘瓶颈分析：
  1. 设备利用率: 68.20% - 接近饱和
  2. 读操作: 536 ops/s, 6MB/s - 较低
  3. 写操作: 1916 ops/s, 20MB/s - 较高
  4. 响应时间: 读0.37ms, 写0.61ms - 良好
  5. 队列长度: 1.66 - 正常`
NFS网络瓶颈分析：
  1. 读操作: 2690 ops/s, 11.6MB/s
  2. 写操作: 1328 ops/s, 5.7MB/s
  3. 网络延迟: 读2.86ms, 写5.88ms - 较高
  4. 重传率: 0% - 网络稳定
  5. 错误率: 0% - 无网络错误

## 故障排除

### 常见问题

1. **权限错误**: 确保测试目录有读写权限
2. **空间不足**: 检查测试目录的可用空间
3. **fio未安装**: 安装fio工具
4. **目录不存在**: 工具会自动创建测试目录

### 调试模式

```bash
# 查看详细输出
fio --debug=all simple_test.fio

# 只运行部分测试
fio --section=sequential_read simple_test.fio
```

## 扩展自定义

### 添加新场景

1. 创建新的 `.fio` 配置文件
2. 在 `fio.py` 的 `choices` 中添加新场景名
3. 更新文档说明

### 修改测试参数

直接编辑对应的 `.fio` 配置文件，调整参数值以满足特定需求。

## 注意事项

1. 测试前确保存储系统稳定
2. 避免在生产环境直接运行
3. 测试时间较长，请耐心等待
4. 结果可能因硬件配置而异
5. 建议在系统空闲时进行测试以获得准确结果
6. 多次测试取平均值以获得更可靠的结果 