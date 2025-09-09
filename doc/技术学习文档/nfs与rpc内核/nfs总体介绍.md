### 优点
1. 简单，容易上手
2. 部署简单，维护简单
3. 数据可靠，耐用
### 缺点：
1. 单点故障，如果nfs server宕机，所有客户端无法连接
2. 高并发场合，NFS效率低（2千万的PV/日网站不是瓶颈，除非网站架构性能太差）
3. 客户端认证时候基于ip和主机名，权限是根绝ID识别，安全性一般，（放置于内网比较好）
4. NFS数据传输是明文，对数据完整性不做完整
5. 多台机器挂载NFS时候，连接管理麻烦，尤其服务器端出问题，所有NFS 客户端都是挂掉状态

### NFS的主要用途
1. 资源共享：
	+ 文件共享：NFS允许多台计算机共享文件和目录，方便用户在不同机器之间访问相同的文件。
	+ 集中管理：通过NFS，可以将常用的数据和应用程序集中存储在一台服务器上，便于管理和备份。
2. 分布式计算：

	+ 集群计算：在高性能计算和集群环境中，NFS可以用于共享配置文件、日志文件和中间结果，提高计算效率。
	+ 开发和测试：开发团队可以使用NFS共享代码库和测试数据，简化协作和同步工作。
3. 备份和恢复：

	+ 集中备份：NFS可以用于集中备份多台计算机的数据，简化备份和恢复流程。
	+ 灾难恢复：通过NFS，可以快速恢复受损系统的数据。
4. 自动化部署：
	+ 配置管理：在自动化部署和配置管理工具中，NFS可以用于共享配置文件和脚本。
	+ 持续集成：在持续集成和持续交付（CI/CD）管道中，NFS可以用于共享构建输出和测试结果。

### 现有工具
#### 客户端检测NFS挂载
1. nfsstat：静态统计数据，操作次数
2. nfsiostat：（可参考）每个挂载点的详细信息， 读写，目录操作，cache属性
3. nfsdist：跟踪各个文件系统操作的延时
4. nfsslower：可以过滤某一个延时以上的操作
BCC存储性能观测工具：
[iovisor/bcc: BCC - Tools for BPF-based Linux IO analysis, networking, monitoring, and more](https://github.com/iovisor/bcc?tab=readme-ov-file#storage-and-filesystems-tools)

[程序员超实用的文件系统性能评测工具盘点 - 知乎](https://zhuanlan.zhihu.com/p/657685939)

##### nfsstat: 指标统计
##### nfstracer: 10年前，工具链陈旧，适配性差
 ##### eNFSanalyzer: 不提供nfs指标
 ##### bpfnfs: 细粒度不够
##### nfsometer:非ebpf, 粗粒度，指标分析不够完善，工具陈旧




#### VFS 检测
1. blktrace
2. atop
3. pidstat：provide only block device or per-process metrics
4. inotifywatch：file-level metrics, but only the number of read and write operations, not the latency.

### 配置解析
https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/4/html/reference_guide/s2-nfs-client-config-options#s2-nfs-client-config-options
相关工具(文档不完整)
- **`nfsconf`**：管理 NFS 配置文件。
- **`nfsdcld`**：管理 NFSv4 客户端的持久性状态。
- **`nfsdclddb`**：操作 NFSv4 客户端状态数据库。
- **`nfsdcltrack`**：跟踪 NFSv4 客户端的非持久性状态。
- **`nfsidmap`**：处理 NFS 用户和组的 ID 映射。
- **`nfsref`**：管理 NFSv4 文件系统引用。
#### Buglist 
https://lore.kernel.org/linux-nfs/?t=20190930161957
#### NFS服务端挂载选项说明：
查询命令：cat /proc/mounts | grep nfs
相关选项：
 - rw/ro：读写/只读
- rsize=N：读取块大小（字节）
- wsize=N：写入块大小（字节）
- timeo=N：超时时间（0.1秒为单位）
- retrans=N：重传次数
- ac/noac：启用/禁用属性缓存
- actimeo=N：属性缓存超时时间（秒）
- sync/async：同步/异步写入
- hard/soft：硬/软挂载
- intr/nointr：允许/禁止中断
如何修改：
sudo mount -o remount,新选项 服务器:/共享 /挂载点
永久修改：
sudo vi /etc/fstab
server:/share /mountpoint nfs4 rw,rsize=1048576,wsize=1048576 0 0
常见场景配置:
1. 优化性能配置：
2. 提高可靠性配置
3. 实时性要求高的配置
4. 缓存优化配置

## NFS-GENESHA
**NFS-Ganesha 的四大优势**
**1、灵活的内存分配**
   首先，user-space 的程序可以分配大量的内存让程序使用，这些内存可以用来建立软件内部缓存，经过测试，我们只需要 4GB 就可以实现百万级别的数据缓存。在一些 x86_64 平台的机器上，我们甚至可以分配更大的内存(16 32GB)，来实现千万级别的数据缓存
**2、更强的可移植性**
   如果 NFS Ganesha 是 kernel-space 的话，那样 NFS Ganesha 的内部结构只能适应一款特定的 OS，而很难移植到别的 OS 上。另外考虑的是代码本身：在不同的平台上编译和运行的产品比在一个单一平台上开发的产品更安全。 我们开发人员的经验表明，只在单一平台上开发会让开发后期困难重重；它通常会显示在 Linux 上不会轻易检测到的错误，因为资源不一样。
**3、更便捷的访问机制**
   内核中的 NFSv4 访问用户空间中的服务不是那么方便，因此其引入了 rpc_pipefs 机制， 用于解决用户空间服务的桥梁，并且使用 kerberos5 管理安全性或 idmapd 守护程序来进行用户名转换。然而 Ganesha 不需要这些，它使用常规 API 来对外提供服务
**4、对接FUSE**
   由于 NFS Ganesha 是一个运行在用户空间的程序，因此它还提供了对一些用户空间文件系统( FUSE )的支持，可以让我们直接把 FUSE 挂载在 NFS 上而不需要内核的帮助
[为什么对于企业NAS来说NFS-ganesha是一个更好的NFS server | 夏天的风的博客](http://xiaqunfeng.cc/2017/08/03/nfs-ganesha/)
[NFS-Ganesha 核心架构解读 - 知乎](https://zhuanlan.zhihu.com/p/34833897)
[nfs-ganesha(用户态NFS)编译、安装和使用_nfs-ganesha 编译-CSDN博客](https://blog.csdn.net/Hearz/article/details/120840448)
[nfs-ganesha路径梳理 - Ethereal's Blog](https://ethereal-o.github.io/2024/12/22/nfs-ganesha%E8%B7%AF%E5%BE%84%E6%A2%B3%E7%90%86/)
 

##  相关博客和网站，背景介绍
Linux NFS和SAMBA服务的应用场景
[Linux NFS和SAMBA服务的应用场景_samba服务器和nfs服务器分别在什么情况下使用-CSDN博客](https://blog.csdn.net/m0_46756244/article/details/105359197)

[网络文件系统（NFS）技术解析与实践-CSDN博客](https://blog.csdn.net/zhai198/article/details/146049297)（介绍了autofs？）

[NFS服务器搭建与使用-CSDN博客](https://blog.csdn.net/mushuangpanny/article/details/127097977)（各种配置参数介绍）

[NFS及RPC讲解 | 《Linux就该这么学》](https://www.linuxprobe.com/nfs-rpc.html)

[NFS 文件系统源代码剖析_nfs源码-CSDN博客](https://blog.csdn.net/yazhouren/article/details/53155458)

[Home · nfs-ganesha/nfs-ganesha Wiki](https://github.com/nfs-ganesha/nfs-ganesha/wiki) (nfs-ganesha项目)

[Main Page - Linux NFS](https://www.linux-nfs.org/wiki/index.php/Main_Page)(源码)

https://github.com/topics/nfs-server （社区资源）

[DeepSeek开源周 Day05：从3FS盘点分布式文件存储系统-腾讯云开发者社区-腾讯云](https://cloud.tencent.com/developer/article/2501140) （DFS分布式文件系统DS）

## 原理
### NFS原理
源码仓库[nfs - fs/nfs - Linux source code (v6.13.7) - Bootlin Elixir Cross Referencer](https://elixir.bootlin.com/linux/v6.13.7/source/fs/nfs)
NFS架构：
![[Pasted image 20250312125240.png]]


### RPC原理：
![[Pasted image 20250327140712.png]]


### 以创建目录为例，NFS调用的基本流程为：
![[Pasted image 20250327144030.png]]
1. 可以监测客户端所有文件系统操作，如下图所示
![[Pasted image 20250327144522.png]]
2. 可以监测服务端与之对应的函数nfsd_xxx

### RPC消息传送详解
![[Pasted image 20250327151332.png]]

根据 **RFC 3530**（NFSv4 协议规范），NFSv4 定义了 **38种文件系统操作** 和 **3种回调操作**。以下是对这些操作的总结，按 **常用文件系统操作** 和 **NFS 特有的文件系统操作** 分类。

---

### **一、常用文件系统操作**

这些操作与传统文件系统的功能类似，主要用于文件和目录的基本管理。

#### **1. 文件和目录操作**

- **CREATE**：创建文件或目录。
- **REMOVE**：删除文件或目录。
- **LOOKUP**：根据路径名查找文件或目录。
- **OPEN**：打开文件。
- **CLOSE**：关闭文件。
- **READ**：读取文件数据。
- **WRITE**：写入文件数据。
- **RENAME**：重命名文件或目录。
- **LINK**：创建硬链接。
- **SYMLINK**：创建符号链接。
- **READLINK**：读取符号链接的目标路径。
- **MKDIR**：创建目录。
- **RMDIR**：删除目录。
#### **2. 属性操作**

- **GETATTR**：获取文件或目录的属性。
- **SETATTR**：设置文件或目录的属性。
- **ACCESS**：检查文件或目录的访问权限。

#### **3. 文件锁定**

- **LOCK**：对文件的字节范围加锁。
- **LOCKU**：释放文件的字节范围锁。
- **OPEN_CONFIRM**：确认文件打开操作。
- **OPEN_DOWNGRADE**：降级文件的打开模式（如从写模式降级为读模式）。

#### **4. 文件系统操作**

- **FSINFO**：获取文件系统的信息。
- **FSSTAT**：获取文件系统的统计信息。
- **PATHCONF**：获取文件系统的路径配置信息（如最大文件名长度）。

#### **5. 目录操作**

- **READDIR**：读取目录内容。

### **二、NFS 特有的文件系统操作**

这些操作是 NFSv4 协议特有的，主要用于支持分布式文件系统的功能，如状态管理、委托、回调等。

#### **1. 状态管理**

- **OPENATTR**：打开文件的命名属性。
- **DELEGRETURN**：客户端向服务器归还文件委托。
- **RENEW**：客户端续约租约（lease）。
- **SETCLIENTID**：客户端向服务器注册。
- **SETCLIENTID_CONFIRM**：确认客户端注册。
- **RELEASE_LOCKOWNER**：释放锁的所有者。

#### **2. 文件委托**

- **DELEGRETURN**：客户端归还文件的委托。
- **GETFH**：获取文件句柄。
- **PUTFH**：设置当前文件句柄。
- **PUTROOTFH**：设置当前文件句柄为根文件句柄。

#### **3. 文件系统迁移和复制**

- **GETFSLOCATION**：获取文件系统的位置，用于支持文件系统迁移和复制。
#### **4. 复合操作**

- **COMPOUND**：NFSv4 的核心操作，用于将多个操作组合成一个请求，减少客户端与服务器之间的通信次数。

#### **5. 安全和访问控制**

- **SECINFO**：获取文件系统的安全信息。
- **VERIFY**：验证文件属性。
- **NVERIFY**：验证文件属性不匹配。

---

### **三、NFSv4 的回调操作**

NFSv4 定义了 **3种回调操作**，用于服务器与客户端之间的双向通信，特别是在文件委托和锁管理中。

1. **CB_GETATTR**：服务器请求客户端返回文件的属性。
2. **CB_RECALL**：服务器通知客户端回收文件的委托。
3. **CB_NOTIFY**：服务器通知客户端文件系统的状态变化

### 相关博客连接
1. pnfs介绍：https://cloud.tencent.cn/developer/article/2547389
2. nfs使用经验：https://blog.csdn.net/qq_31815769/article/details/149726708