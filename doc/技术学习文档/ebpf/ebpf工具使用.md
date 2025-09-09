# CPU 
## 指标
USE指标：使用率，饱和度， 错误数
对应——CPU使用率， CPU队列等待时间或队列长度， 和CPU错误数

## 工具
+ 与使用率相关传统工具有：top, uptime, mpstat，
+ 相关ebpf工具有：cpudist
+ 跟踪 CPU 饱和度（运行队列长度） : runqlen, runqlat
+ llcstat利用PMC事件来按进程输出最后一级缓存的命中率

需要注意的是，在一个繁忙的系统中使用kprobes会带来不可忽视的性能损耗
一个比较重要的工具是offcputime, 它通过跟踪上下文切换事件来记录一个线程脱离CPU的时间和返回CPU的时间，它开销比较大，而且输出比较多，最好和profile一起作为一个单独的工具使用

## 内存分析
思路：
1. 检查系统中是否有OOM Killer杀掉进程的信息
2. 检查换页空间的大小和对应IO操作的活跃度
3. 检查系统中空闲内存用量（swap, free, iostat, vmstat, swapon）
4. 检查进程内存用量(ps aux，关注VSZ,RSS,%MEM)
4. 检查系统中缺页错误的发生概率，并且检查缺页错误发生时的调用栈信息，（这可以解释RSS增长的原因）与哪些文件有关

相关ebpf工具：
1. oomkill: 展示OOM Killer事件的详细信息
2. memleak：展示可能发生内存泄漏的代码路径
3. mmapsnoop：跟踪mmap调用
4. brkstack： 跟踪brk()调用
5. shmsnoop： 
6. faults
7. ffaults
8. vmscan
9. drsnoop
10. swapin
12. hfaults

## 文件系统分析
思路：
1. 识别文件系统挂载 ：df 或 mount
2. 检查文件系统的容量
3. 确定负载（fio）
4. 使用opensnoop观测哪些文件被打开
5. 使用filelife检查是否存在短期文件问题
6. 查找慢速文件系统操作
7. 检查文件系统延时分布
8. 检查页缓存命中率
9. 使用vfsstat比较逻辑IO与物理IO的区别

传统工具：
+ df
+ iostat

ebpf工具
文件操作跟踪
opensnoop

功能：跟踪全系统范围的文件打开操作（open()/openat() 系统调用）
使用场景：排查文件找不到错误、分析配置文件加载路径、检测异常文件访问
典型输出：时间戳、进程名、PID、文件路径、返回码
statsnoop

功能：捕获 stat() 系列系统调用（stat/lstat/newfstatat）
使用场景：分析配置文件检查、日志轮转检测、文件元数据访问模式
典型输出：目标文件名、UID、调用进程信息
syncsnoop

功能：跟踪 sync/fsync/fdatasync 等同步操作
使用场景：定位高延迟的持久化操作、分析数据库事务提交开销
输出字段：进程名、目标文件描述符、同步耗时
内存映射分析
mmapfiles

功能：统计通过 mmap() 映射到内存的文件
使用场景：分析共享库加载、大文件内存映射行为
数据维度：映射次数、文件路径、映射大小
fmapfault

功能：跟踪文件映射内存区域的缺页错误（minor/major fault）
使用场景：分析内存映射文件的实时加载行为
关键指标：缺页类型、触发进程、关联文件名
文件读写分析
scread

功能：捕获 read() 系统调用的文件访问细节
扩展能力：可过滤特定文件扩展名（如 .conf）
输出示例：读取偏移量、字节数、目标文件路径
fsrwstat

功能：统计文件系统读写操作的吞吐量和 I/O 大小分布
分析维度：按挂载点或文件系统类型聚合
典型用途：识别存储性能瓶颈
高级缓存分析
cachestat

功能：实时显示页缓存命中率（LRU 算法相关指标）
关键指标：hit%（缓存命中率）、dirty（脏页数量）、writeback（回写中页数）
扩展用途：结合 vfsstat 区分逻辑 I/O 与物理 I/O
dcstat & dcsnoop

dcstat：统计目录项缓存（dentry cache）的命中率
dcsnoop：跟踪失败的目录项缓存查找操作
典型场景：优化频繁访问的目录结构
性能问题定位
fileslower

功能：捕获超过指定阈值的慢速文件操作（read/write/open）
调优建议：通常设置 10ms 作为基线阈值
输出包含：操作类型、耗时、关联文件名
filetop

功能：类似 top 的实时文件读写排行榜
排序依据：按读写吞吐量或操作次数排序
数据源：动态跟踪 read/write 系统调用
特殊场景工具
filelife

功能：跟踪短生命周期文件（创建后快速删除）
典型场景：排查临时文件泄漏、分析构建工具产生的中间文件
输出字段：文件存在时长、创建进程信息
readahead

功能：分析文件预读机制的效率
关键指标：预读命中率、无效预读量
优化参考：调整 vm.vfs_cache_pressure 等内核参数
补充工具
vfsstat：按秒粒度统计 VFS 调用次数（open/read/write 等）
writeback：跟踪脏页回写磁盘的过程，显示回写延迟分布
mountsnoop：监控文件系统挂载/卸载事件

# 磁盘
思路：
1.  对于性能问题，先检查文件系统
2. 检查基本磁盘性能指标：IOPS, 使用率，延迟
3. 跟踪延迟分布
4. 单独跟踪具体的块，找寻行为模式

传统工具：
+ iostat

ebpf工具
+ I/O 延迟分析
    1. biolatency	统计块设备 I/O 延迟分布直方图，可识别存储响应时间异常
    2. biosnoop	实时跟踪每个块 I/O 操作的详细信息（进程、LBA、字节数、延迟）
    3. nvmelatency	专用于 NVMe 设备的 I/O 延迟分布分析
    4. scsilatency	测量 SCSI 命令的协议层延迟（从提交到完成）
+ I/O 操作跟踪
    1. biotop	类似 top 的实时块 I/O 进程排行榜（按吞吐量/IOPS 排序）
    2. bitesize	统计 I/O 请求大小的分布情况（识别大块/碎片化写入）
    3. seeksize	跟踪 I/O 操作的寻址距离（检测随机/顺序访问模式）
    4. biopattern	检测存储访问模式（顺序/随机），优化预读策略
+ 高级调试
    1. biostacks	显示触发块 I/O 操作的内核调用栈（定位高延迟源头）
    2. scsiresult	捕获 SCSI 命令的返回状态码（排查设备级错误）
    3. bioerr	跟踪块层错误事件（如 EIO 错误），记录错误上下文
+ 存储子系统分析
    1. mdflush	监控 MDRAID 阵列的缓存刷新操作（分析 RAID 性能瓶颈）
    2. iosched	跟踪 I/O 调度器队列行为（如 CFQ/Deadline 调度策略效果）

## 网络
思路：
1. 理解基本网络统计信息：速率和吞吐量，TCP连接率和重传率
2. 跟踪新TCP链接的建立和时长来定性分析负载，并且寻找低效之处
3. 检查是否到达网络接口吞吐量的上限
4. 跟踪TCP重传和其它不常见TCP事件
5. 测量DNS延迟
6. 从各个角度拆解网络延迟：连接延迟，首字节延迟，各网络协议栈延迟等。应在有负载网络和空闲网络中分别测量这些延迟
7. 使用负载生成工具探索吞吐量上限，检查在已知负载情况下发生的网络事件

传统工具：
——展示内核各种统计信息
1. ss： 套接字统计: ss -tiepm
2. ip： ip统计
3. nstat： 网络栈统计
4. netstat：网络栈统计和状态
5. sar： 网络和其他统计信息
6. nicstat：接口统计
7. ethtool: 接口驱动程序统计
8. tcpdump: 

ebpf工具：
1. gethostlatency：跟踪DNS解析延迟
2. tcplife：跟踪TCP连接的建立和关闭
3. nettxlat: 展示发送延迟
4. skbdrop: 跟踪不常见的skb丢弃事件


## 常见问题
### 开销
决定一个跟踪程序的CPU开销主要有三个因素：
1. 被跟踪事件的触发频率
2. 跟踪时执行的操作
3. 系统中CPU的个数
额外开销 = 频率 * 执行的操作数 / CPU个数

