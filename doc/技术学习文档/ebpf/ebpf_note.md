# Part 0: Introduction

+ eBPF简介
  eBPF技术是一种可以在操作系统的内核运行沙盒程序的技术，主要被用来安全和有效的扩展内核的功能。一个eBPF程序主要由内核态部分和用户态部分构成，支持的语言包括 `Python、C、GO、Rust`但是每种语言使用的框架可能并不相同，同时内核态部分的代码需要符合eBPF的语法和指令集，eBPF程序主要由若干个函数组成，每个函数都有其特定的作用，可以使用的函数类型包括：
  + kprobe：插探函数，在指定的内核函数前后执行
  + tracepoint：跟踪点函数，在指定的内核跟踪点处执行
  + raw_tracepoint：原始跟踪点函数，在指定的内核原始跟踪点处执行
  + xdp：网络数据处理函数，拦截和处理网络数据包
  + perf_event：性能事件函数，用于处理内核性能事件
  + kretprobe：函数返回插探函数，在指定的内核函数返回时执行
  + tracepoint_return：跟踪点函数返回，在指定的内核跟踪点返回时执行
  + raw_tracepoint_return：原始跟踪点函数返回，在指定的内核原始跟踪点返回时执行
+ BCC
  BCC全称为BPF Compiler Collection，该项目是一个python库，包含了完整的编写、编译、和加载BPF程序的工具链，以及用于调试和诊断性能问题的工具，自2015年发布以来，BCC经过上百位贡献者地不断完善后，目前已经包含了大量随时可用的跟踪工具。虽然BCC可以使用高级语言进行编程，但是BCC存在一个缺点就是其兼容性并不好，基于BCC的eBPF程序每次执行的时候都需要进行编译，编译则需要用户配置相关的头文件和对应的实现，在实际应用中
+ libbpf
  `libbpf-booststrap`是一个基于 `libbpf`库的BPF开发脚手架，基于 `libbpf-booststrap`的程序对于源文件有一定的命名规则，用于生成内核态字节码的bpf文件必须以 `.bpf.c`结尾，用户态加载字节码的文件以 `.c`结尾，且二者的前缀必须相同，而在编译的时候 `libbpf-booststrap`会先将 `.bpf.c`文件编译为对应的 .o文件，然后根据这个文件生成skeleton文件，即 `.skel.h`，这个文件会包含内核态中定义的一些数据结构，以及用于装载内核态代码的关键函数

# Part 1: Hello World!

+ 下面是一个最简单的eBPF程序的实现

  ```c
  /* SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause) */
  #define BPF_NO_GLOBAL_DATA
  #include <linux/bpf.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>

  typedef unsigned int u32;
  typedef int pid_t;
  const pid_t pid_filter = 0;

  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  SEC("tp/syscalls/sys_enter_write")
  int handle_tp(void *ctx)
  {
   pid_t pid = bpf_get_current_pid_tgid() >> 32;
   if (pid_filter && pid != pid_filter)
    return 0;
   bpf_printk("BPF triggered from PID %d.\n", pid);
   return 0;
  }

  ```

  这段程序通过定义一个handler函数并使用SEC宏把它附加到 `sys_enter_write_tracepoint`（即在进入write系统调用的时候执行，该函数通过使用 `bpf_get_current_pid_tgid`和 `bpf_printk`函数获取调用write系统调用，有几个重要的地方：

  + `bpf_trace_printk()：`是一种将信息输出到 `trace_pipe`文件的一种简单机制，在一些简单用例中这样使用并没有问题，但是它也有一些限制：最多三个参数，第一参数必须是字符串，同 `trace_pipe`在内核中全局共享，显然会受到并行的影响，因此一个更好的方式是通过 `BPF_PERF_OUTPUT()`输出
  + `void* ctx()：`由于没用到ctx参数，因此写成 `void*`简化书写
  + `return 0：`必须返回0
+ eBPF程序的基本框架

  + 包含头文件：需要包含bpf相关的头文件
  + 定义许可证：一般使用 `Dual BSD/GPL`
  + 定义BPF函数：需要至少一个BPF函数并使用SEC定义挂载点
  + 只能调用BPF辅助函数
+ tracepoint
  跟踪点是内核静态插桩技术，本质是在源码中插入的一些带有控制条件的探测点，这些探测点允许事后再添加处理函数，比如在内核中，最常见的静态跟踪方法就是printk，即输出日志

# Part 2：kprobe

+ kprobes技术背景
  kprobes为内核提供了三种探测手段，分别是 `kprobe` 、`jprobe`和 `kretprobe`，其中kprobe是最基本的探测方式，是实现后两种的基础，可以在任意的位置放置探测点，提供了包括探测点调用前、调用后和内存访问出错3种回调方式，分别是pre_handler、post_handler和falut_handler，其中pre_handler函数将在被探测指令被执行前回调，post_handler会在被探测指令执行完毕之后回调，fault_handler会在内存访问出错时被调用；jprobe基于kprobe实现，它用于获取被探测函数的入参值；最后kretprobe从名字中就可以看出其用途了，它同样基于kprobe实现，用于获取被探测函数的返回值
  但是kprobes技术并不仅仅 包含软件的实现方案，它也需要硬件架构支持，即CPU的异常处理和单步调试的功能，因此并不是所有的架构均支持
+ 特点与使用限制

  + kprobes允许同一个位置注册多个kprobe，但是jprobe不行，也不能以其他的probe回调函数作为探测点
  + 一般情况下们可以探测内核中的任何函数，除了与probe自身相关的函数
  + 探测内联函数时，可能会达不到预期的效果
  + 一个探测点的回调函数可以修改被探测函数运行时的上下文
  + kprobes的注册和注销过程不会使用mutex锁和动态的申请内存
  + 不能在回调函数中使用会放弃CPU的函数
+ 使用kprobe监测和捕获unlink系统调用

  ```c
  #include "vmlinux.h"
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>
  #include <bpf/bpf_core_read.h>

  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  SEC("kprobe/do_unlinkat")
  int BPF_KPROBE(do_unlinkat, int dfd, struct filename *name)
  {
   pid_t pid;
   const char *filename;

   pid = bpf_get_current_pid_tgid() >> 32;
   filename = BPF_CORE_READ(name, name);
   bpf_printk("KPROBE ENTRY pid = %d, filename = %s\n", pid, filename);
   return 0;
  }

  SEC("kretprobe/do_unlinkat")
  int BPF_KRETPROBE(do_unlinkat_exit, long ret)
  {
   pid_t pid;

   pid = bpf_get_current_pid_tgid() >> 32;
   bpf_printk("KPROBE EXIT: pid = %d, ret = %ld\n", pid, ret);
   return 0;
  }

  ```

  `BPF_KPROBE`函数用于获取当前进程的 `PID`并读取文件名，`BPF_KRETPROBE`用于捕获函数的返回值

# Part 3：fentry

+ function entry和function exit
  entry和fexit是eBPF中的两种探针类型，用于在内核函数的入口和出口处进行跟踪，允许开发者在内核函数执行的特点阶段收集信息、修改参数或者观察返回值，相较于传统kprobes动态追踪方案，新型插桩机制在参数访问方式上实现了架构级优化。通过编译器辅助的地址解析技术，开发者可直接以原生指针形式操作函数参数结构，消除了传统方案中通过寄存器解析参数带来的性能损耗。特别在函数退出监控场景中，fexit机制突破了kretprobe仅能获取返回值的局限，实现了输入参数与输出结果的全量关联分析。
+ fentry和fexit的使用例子

  ```c
  #include "vmlinux.h"
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>

  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  SEC("fentry/do_unlinkat")
  int BPF_PROG(do_unlinkat, int dfd, struct filename *name)
  {
   pid_t pid;

   pid = bpf_get_current_pid_tgid() >> 32;
   bpf_printk("fentry: pid = %d, filename = %s\n", pid, name->name);
   return 0;
  }

  SEC("fexit/do_unlinkat")
  int BPF_PROG(do_unlinkat_exit, int dfd, struct filename *name, long ret)
  {
   pid_t pid;

   pid = bpf_get_current_pid_tgid() >> 32;
   bpf_printk("fexit: pid = %d, filename = %s, ret = %ld\n", pid, name->name, ret);
   return 0;
  }

  ```

  可以看到对于fexit探针不仅可以获取到程序的返回值，还可以获取到文件名
  注意上述kprobe和fentry的例子中，`BPF_KPROBE`和 `BPF_PROG`均为宏定义，用于获取探测函数的参数

# Part 4：opensnoop

+ `sys_openat`
  在Linux系统中，当一个进程打开文件时，会向内核发出 `sys_openat`的系统调用集合，并传递相关参数（例如文件路径、打开模式等），内核在处理完这个请求之后，会返回一个文件描述符，这个描述符将在后续的文件操作中用作引用，首先我们可以利用 `tracepoint`编写一段eBPF程序来捕获进程打开文件的系统调用，代码如下：

  ```c
  #include <vmlinux.h>
  #include <bpf/bpf_helpers.h>

  /// @description "Process ID to trace"
  const volatile int pid_target = 0;

  SEC("tracepoint/syscalls/sys_enter_openat")
  int tracepoint__syscalls__sys_enter_openat(struct trace_event_raw_sys_enter* ctx)
  {
   u64 id = bpf_get_current_pid_tgid();
   u32 pid = id;

   if (pid_target && pid_target != pid)
    return false;
   // Use bpf_printk to print the process information
   bpf_printk("Process ID: %d enter sys openat\n", pid);
   return 0;
  }

  /// "Trace open family syscalls."
  char LICENSE[] SEC("license") = "GPL";

  ```

  上述代码通过全局变量 `pid_target`实现了对特定程序的过滤，全局变量在eBPF程序中充当一种数据共享机制，它们允许用户态程序与eBPF程序之间进行数据交互，这在过滤特定条件或者修改eBPF程序行为时十分有用，可以使得用户态程序能够在运行时动态的控制eBPF程序的行为，在上述例子中，全局变量 `pid_target`用于过滤进程的PID，用户态可以设置此变量的值，以便只捕获和指定PID相关的 `sys_openat`系统调用
+ 全局变量
  全局变量的原理是，全局变量在eBPF程序的数据段(data section)中定义并存储，当eBPF程序加载到内核执行时，这些全局变量会保持在内核中，而用户态程序可以使用BPF系统调用的某些特性，如 `bpf_obj_get_info_by_fd`和 `bpf_obj_get_info`，获取eBPF对象的信息，包括全局变量的位置和信息

# Part 5： uprobe

+ uprobe介绍
  uprobe是一种用户空间探针，uprobe探针允许在用户空间程序中动态插桩，插桩位置包括：函数入口、特定偏移处、以及函数返回处，当我们定义uprobe时，内核会在附加的指令上创建快速断点指令，当程序执行到该指令的时候，内核会触发事件，并以回调函数的方式调用探针函数，执行完探针函数之后再返回到用户态继续执行之后的指令，uprobe基于文件，当一个二进制文件中的一个函数被跟踪时，所有使用到这个文件的进程都会被插桩，包括那些尚未启动的进程，这样就可以再全系统范围内跟踪系统调用。因此uprobe适用于在用户态去解析一些内核态探针无法解析的流量，例如http2流量（报文header被编码，内核无法解码），https流量（加密流量，内核无法解密）
+ uprobe捕获bash的readline函数调用例子

  ```c
  #include <vmlinux.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>

  #define TASK_COMM_LEN 16
  #define MAX_LINE_SIZE 80

  /* Format of u[ret]probe section definition supporting auto-attach:
   * u[ret]probe/binary:function[+offset]
   *
   * binary can be an absolute/relative path or a filename; the latter is resolved to a
   * full binary path via bpf_program__attach_uprobe_opts.
   *
   * Specifying uprobe+ ensures we carry out strict matching; either "uprobe" must be
   * specified (and auto-attach is not possible) or the above format is specified for
   * auto-attach.
   */
  SEC("uretprobe//bin/bash:readline")
  int BPF_KRETPROBE(printret, const void *ret)
  {
   char str[MAX_LINE_SIZE];
   char comm[TASK_COMM_LEN];
   u32 pid;

   if (!ret)
    return 0;

   bpf_get_current_comm(&comm, sizeof(comm));

   pid = bpf_get_current_pid_tgid() >> 32;
   bpf_probe_read_user_str(str, sizeof(str), ret);

   bpf_printk("PID %d (%s) read: %s ", pid, comm, str);

   return 0;
  };

  char LICENSE[] SEC("license") = "GPL";

  ```

  在上述代码中，使用了SEC宏定义了uprobe的类型，以及要捕获的二进制文件的路径和要捕获的函数名称，例如在上述代码中，我们需要捕获的是/bin/bash:readline，即二进制文件中的readline函数

# Part 6：sigsnoop

+ 本Part主要介绍了一个eBPF工具，用于捕获进程发送信号的系统调用集合，并且使用hash map保存相关的信息，具体代码如下：

  ```c
  #include <vmlinux.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>

  #define MAX_ENTRIES 10240
  #define TASK_COMM_LEN 16

  struct event {
   unsigned int pid;
   unsigned int tpid;
   int sig;
   int ret;
   char comm[TASK_COMM_LEN];
  };

  struct {
   __uint(type, BPF_MAP_TYPE_HASH);
   __uint(max_entries, MAX_ENTRIES);
   __type(key, __u32);
   __type(value, struct event);
  } values SEC(".maps");


  static int probe_entry(pid_t tpid, int sig)
  {
   struct event event = {};
   __u64 pid_tgid;
   __u32 tid;

   pid_tgid = bpf_get_current_pid_tgid();
   tid = (__u32)pid_tgid;
   event.pid = pid_tgid >> 32;
   event.tpid = tpid;
   event.sig = sig;
   bpf_get_current_comm(event.comm, sizeof(event.comm));
   bpf_map_update_elem(&values, &tid, &event, BPF_ANY);
   return 0;
  }

  static int probe_exit(void *ctx, int ret)
  {
   __u64 pid_tgid = bpf_get_current_pid_tgid();
   __u32 tid = (__u32)pid_tgid;
   struct event *eventp;

   eventp = bpf_map_lookup_elem(&values, &tid);
   if (!eventp)
    return 0;

   eventp->ret = ret;
   bpf_printk("PID %d (%s) sent signal %d to PID %d, ret = %d",
       eventp->pid, eventp->comm, eventp->sig, eventp->tpid, ret);

  cleanup:
   bpf_map_delete_elem(&values, &tid);
   return 0;
  }

  SEC("tracepoint/syscalls/sys_enter_kill")
  int kill_entry(struct trace_event_raw_sys_enter *ctx)
  {
   pid_t tpid = (pid_t)ctx->args[0];
   int sig = (int)ctx->args[1];

   return probe_entry(tpid, sig);
  }

  SEC("tracepoint/syscalls/sys_exit_kill")
  int kill_exit(struct trace_event_raw_sys_exit *ctx)
  {
   return probe_exit(ctx, ctx->ret);
  }

  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  ```

  上述代码定义了一个eBPF程序，使用tracepoint来捕获系统调用的进入和退出事件，在上述代码中主要是指kill这个事件。在探针函数中，我们使用bpf_map存储捕获的信息，包括发送信号的进程ID、接受信号的进程ID、信号值和系统调用的返回值。在系统调用退出时，我们将获取原先存储在map中的事件信息，并使用bpf_printk打印进程的ID、进程名称、发送的信号和系统调用的返回值
+ hash map的定义
  一个完整的hash map结构体的定义必须包含以下部分：

  ```c
  struct {
   __uint(type, BPF_MAP_TYPE_HASH);
   __uint(max_entries, MAX_ENTRIES);
   __type(key, __u32);
   __type(value, struct event);
  } values SEC(".maps");

  ```

  + 类型
  + 能包含的最多键值对的数量
  + 索引键的类型
  + 值的类型
  + `SEC(".maps")`宏定义

# Part 7：execsnoop

eBPF提供了两个环形缓冲区，可以用来将信息从eBPF程序传输到用户区控制器，第一个是perf环形缓冲区，第二个是后来引入的BPF环形缓冲区，本文只考虑perf环形缓冲区

+ map结构体
  为了使用perf event array向用户态命令行打印输出，我们需要定义一个bpf map：

  ```c

  struct {
   __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
   __uint(key_size, sizeof(u32));
   __uint(value_size, sizeof(u32));
  } events SEC(".maps");

  struct event {
   int pid;
   int ppid;
   int uid;
   int retval;
   bool is_exit;
   char comm[TASK_COMM_LEN];
  };

  ```

  通过定义 `PERF_EVENT_ARRAY`类型的 `BPF_MAP`我们可以通过调用函数 `bpf_perf_event_output`函数我们可以将event结构体中的数据以数组形式输出到终端中，不再需要通过查看 `/sys/kernel/debug/tracing/trace_pipe`文件来查看 eBPF 程序的输出
+ execsnoop

  ```c
  #include <vmlinux.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_core_read.h>
  #include "execsnoop.h"

  struct {
   __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
   __uint(key_size, sizeof(u32));
   __uint(value_size, sizeof(u32));
  } events SEC(".maps");

  SEC("tracepoint/syscalls/sys_enter_execve")
  int tracepoint__syscalls__sys_enter_execve(struct trace_event_raw_sys_enter* ctx)
  {
   u64 id;
   pid_t pid, tgid;
   struct event event={0};
   struct task_struct *task;

   uid_t uid = (u32)bpf_get_current_uid_gid();
   id = bpf_get_current_pid_tgid();
   pid = (pid_t)id;
   tgid = id >> 32;

   event.pid = tgid;
   event.uid = uid;
   task = (struct task_struct*)bpf_get_current_task();
   event.ppid = BPF_CORE_READ(task, real_parent, tgid);
   bpf_get_current_comm(&event.comm, sizeof(event.comm));
   bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
   return 0;
  }

  char LICENSE[] SEC("license") = "GPL";

  ```

  本质上 `bpf_perf_event_output`函数只会将进程执行事件输出到perf buffer（用户态可以获取到其中数据），只不过ecli程序自动将其中内容进行了解包，并按格式输出到了终端中

# Part 8：exitsnoop

+ eBPF环形缓冲区（ring buffer）
  perf buffer是每一个CPU循环缓冲区的集合，它允许在内核和用户空间之间有效地交换数据，它在实践中的效果很好，但是由于其按照CPU进行设计（不同CPU之间不共享），它有两个主要的缺点，在实践中被证明是不方便的：内存的低效使用和事件的重新排序
  BPF环形缓冲区（ring buffer）是一个多生产者、单消费者（MPSC）队列，可以同时在多个CPU上安全共享，其主要的功能如下：

  + 支持变长数据记录
  + 能够通过内存映射区域有效地从用户空间读取数据，而不需要额外的内存拷贝或者进入内核的系统调用
  + 即支持epoll通知又能以绝对最小的延迟进行忙环操作
  + 解决了perf buffer的内存开销和数据排序的问题，且不需要额外的数据复制
+ map定义
  和perf buffer的使用一样，我们同样需要先定义一个ring buffer类型map才能够往ring buffer中注入数据，map定义如下：

  ```c
  struct {
   __uint(type, BPF_MAP_TYPE_RINGBUF);
   __uint(max_entries, 256 * 1024);
  } rb SEC(".maps");

  ```

  之后为了往ring buffer注入数据，我们需要先在ring buffer中为数据预定一个位置，通过调用函数 `bpf_ringbuf_reserve`即可；之后再通过函数 `bpf_ringbuf_submit`进行提交，下面给出一个监控进程退出的ring buffer使用示例
+ exitsnoop

  ```c
  #include "vmlinux.h"
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>
  #include <bpf/bpf_core_read.h>
  #include "exitsnoop.h"
  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  struct {
   __uint(type, BPF_MAP_TYPE_RINGBUF);
   __uint(max_entries, 256 * 1024);
  } rb SEC(".maps");

  SEC("tp/sched/sched_process_exit")
  int handle_exit(struct trace_event_raw_sched_process_template* ctx)
  {
   struct task_struct *task;
   struct event *e;
   pid_t pid, tid;
   u64 id, ts, *start_ts, duration_ns = 0;

   /* get PID and TID of exiting thread/process */
   id = bpf_get_current_pid_tgid();
   pid = id >> 32;
   tid = (u32)id;

   /* ignore thread exits */
   if (pid != tid)
    return 0;

   /* reserve sample from BPF ringbuf */
   e = bpf_ringbuf_reserve(&rb, sizeof(*e), 0);
   if (!e)
    return 0;

   /* fill out the sample with data */
   task = (struct task_struct *)bpf_get_current_task();

   e->duration_ns = duration_ns;
   e->pid = pid;
   e->ppid = BPF_CORE_READ(task, real_parent, tgid);
   e->exit_code = (BPF_CORE_READ(task, exit_code) >> 8) & 0xff;
   bpf_get_current_comm(&e->comm, sizeof(e->comm));

   /* send data to user-space for post-processing */
   bpf_ringbuf_submit(e, 0);
   return 0;
  }

  ```

# Part 9：runqlat

+ runqlat原理
  runqlat程序的作用是以直方图的形式记录进程调度的延迟，Linux操作系统使用进程来执行所有的系统和用户任务，这些进程可能被阻塞、杀死、运行或者正在等待运行，处在后两种状态的进程数量决定了CPU运行队列的长度。具体而言，进程的几种可能的运行状态如下：

  + 可运行或者正在运行
  + 可中断睡眠
  + 不可中断睡眠
  + 停止
  + 僵尸进程

  在一个理想的CPU利用率下，运行队列的长度应该等于系统中的核心数量，进程调度延迟，也被称之为”run queue latency“，是衡量线程从变得可运行到实际在CPU上运行的时间，在CPU饱和的情况下，可以想象线程必须等待其他轮次，但在其他奇特的场景中，这也可能发生，通过调度调优，我们可以提高整个系统的性能。runqlat的实现利用了eBPF程序，它通过内核跟踪点和函数探针来测量进程在队列中的运行时间，当进程被排队时，`trace_enqueue`函数会在一个映射中记录时间戳，当进程被调度到CPU上运行的时候，handle_switch函数会检索时间戳，并计算当前时间和排队时间的时间差，这个差值就被用于更新进程的直方图
+ runqlat代码

  ```c
  // SPDX-License-Identifier: GPL-2.0
  // Copyright (c) 2020 Wenbo Zhang
  #include <vmlinux.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_core_read.h>
  #include <bpf/bpf_tracing.h>
  #include "runqlat.h"
  #include "bits.bpf.h"
  #include "maps.bpf.h"
  #include "core_fixes.bpf.h"

  #define MAX_ENTRIES 10240
  #define TASK_RUNNING  0

  const volatile bool filter_cg = false;
  const volatile bool targ_per_process = false;
  const volatile bool targ_per_thread = false;
  const volatile bool targ_per_pidns = false;
  const volatile bool targ_ms = false;
  const volatile pid_t targ_tgid = 0;

  struct {
   __uint(type, BPF_MAP_TYPE_CGROUP_ARRAY);
   __type(key, u32);
   __type(value, u32);
   __uint(max_entries, 1);
  } cgroup_map SEC(".maps");

  struct {
   __uint(type, BPF_MAP_TYPE_HASH);
   __uint(max_entries, MAX_ENTRIES);
   __type(key, u32);
   __type(value, u64);
  } start SEC(".maps");

  static struct hist zero;

  /// @sample {"interval": 1000, "type" : "log2_hist"}
  struct {
   __uint(type, BPF_MAP_TYPE_HASH);
   __uint(max_entries, MAX_ENTRIES);
   __type(key, u32);
   __type(value, struct hist);
  } hists SEC(".maps");

  static int trace_enqueue(u32 tgid, u32 pid)
  {
   u64 ts;

   if (!pid)
    return 0;
   if (targ_tgid && targ_tgid != tgid)
    return 0;

   ts = bpf_ktime_get_ns();
   bpf_map_update_elem(&start, &pid, &ts, BPF_ANY);
   return 0;
  }

  static unsigned int pid_namespace(struct task_struct *task)
  {
   struct pid *pid;
   unsigned int level;
   struct upid upid;
   unsigned int inum;

   /*  get the pid namespace by following task_active_pid_ns(),
    *  pid->numbers[pid->level].ns
    */
   pid = BPF_CORE_READ(task, thread_pid);
   level = BPF_CORE_READ(pid, level);
   bpf_core_read(&upid, sizeof(upid), &pid->numbers[level]);
   inum = BPF_CORE_READ(upid.ns, ns.inum);

   return inum;
  }

  static int handle_switch(bool preempt, struct task_struct *prev, struct task_struct *next)
  {
   struct hist *histp;
   u64 *tsp, slot;
   u32 pid, hkey;
   s64 delta;

   if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0))
    return 0;

   if (get_task_state(prev) == TASK_RUNNING)
    trace_enqueue(BPF_CORE_READ(prev, tgid), BPF_CORE_READ(prev, pid));

   pid = BPF_CORE_READ(next, pid);

   tsp = bpf_map_lookup_elem(&start, &pid);
   if (!tsp)
    return 0;
   delta = bpf_ktime_get_ns() - *tsp;
   if (delta < 0)
    goto cleanup;

   if (targ_per_process)
    hkey = BPF_CORE_READ(next, tgid);
   else if (targ_per_thread)
    hkey = pid;
   else if (targ_per_pidns)
    hkey = pid_namespace(next);
   else
    hkey = -1;
   histp = bpf_map_lookup_or_try_init(&hists, &hkey, &zero);
   if (!histp)
    goto cleanup;
   if (!histp->comm[0])
    bpf_probe_read_kernel_str(&histp->comm, sizeof(histp->comm),
       next->comm);
   if (targ_ms)
    delta /= 1000000U;
   else
    delta /= 1000U;
   slot = log2l(delta);
   if (slot >= MAX_SLOTS)
    slot = MAX_SLOTS - 1;
   __sync_fetch_and_add(&histp->slots[slot], 1);

  cleanup:
   bpf_map_delete_elem(&start, &pid);
   return 0;
  }

  SEC("raw_tp/sched_wakeup")
  int BPF_PROG(handle_sched_wakeup, struct task_struct *p)
  {
   if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0))
    return 0;

   return trace_enqueue(BPF_CORE_READ(p, tgid), BPF_CORE_READ(p, pid));
  }

  SEC("raw_tp/sched_wakeup_new")
  int BPF_PROG(handle_sched_wakeup_new, struct task_struct *p)
  {
   if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0))
    return 0;

   return trace_enqueue(BPF_CORE_READ(p, tgid), BPF_CORE_READ(p, pid));
  }

  SEC("raw_tp/sched_switch")
  int BPF_PROG(handle_sched_switch, bool preempt, struct task_struct *prev, struct task_struct *next)
  {
   return handle_switch(preempt, prev, next);
  }

  char LICENSE[] SEC("license") = "GPL";

  ```

  通过实现runqlat，我们可以通过其输出的直方图分析Linux内核调度的性能

# Part 10：hardirqs

+ hardirqs和softirqs
  hardirqs是指硬件中断处理程序，当硬件设备产生一个中断请求的时候，内核会将该请求映射到一个特定的中断向量，然后执行与之关联的硬件中断处理程序，硬件中断处理程序通常用于处理设备驱动中的事件，例如**设备数据传输完成或者设备错误**。softirqs是指软件中断处理程序，它们是内核中的一种底层异步事件处理机制，用于处理内核中的高优先级任务，softirqs则**通常用于处理网络协议栈、磁盘子系统和其他内核组件中的事件**，软件中断处理程序具有更高的灵活性和可配置性
+ 捕获中断事件
  在eBPF中，我们可以通过挂载特定的kprobe或者tracepoint来捕获和分析hardirqs和softirqs，需要在相关的内核函数上放置eBPF程序，这些函数包括：

  + hardirqs：`irq_handler_entry`和 `irq_handler_exit`
  + softirqs：`softirq_entry`和 `softirq_exit`

  当内核在处理hardirqs和softirqs时，这些eBPF程序会被执行，从而收集相关信息，如中断向量、中断处理程序的执行时间等等，收集到的信息可以用于分析内核中的性能问题和其他与中断处理相关的问题，下面针对hardirqs实现跟踪代码：

  ```c
  #include <vmlinux.h>
  #include <bpf/bpf_core_read.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>
  #include "hardirqs.h"
  #include "bits.bpf.h"
  #include "maps.bpf.h"

  #define MAX_ENTRIES 256

  const volatile bool filter_cg = false;
  const volatile bool targ_dist = false;
  const volatile bool targ_ns = false;
  const volatile bool do_count = false;

  struct {
   __uint(type, BPF_MAP_TYPE_CGROUP_ARRAY);
   __type(key, u32);
   __type(value, u32);
   __uint(max_entries, 1);
  } cgroup_map SEC(".maps");

  struct {
   __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
   __uint(max_entries, 1);
   __type(key, u32);
   __type(value, u64);
  } start SEC(".maps");

  struct {
   __uint(type, BPF_MAP_TYPE_HASH);
   __uint(max_entries, MAX_ENTRIES);
   __type(key, struct irq_key);
   __type(value, struct info);
  } infos SEC(".maps");

  static struct info zero;

  static int handle_entry(int irq, struct irqaction *action)
  {
   if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0))
    return 0;

   if (do_count) {
    struct irq_key key = {};
    struct info *info;

    bpf_probe_read_kernel_str(&key.name, sizeof(key.name), BPF_CORE_READ(action, name));
    info = bpf_map_lookup_or_try_init(&infos, &key, &zero);
    if (!info)
     return 0;
    info->count += 1;
    return 0;
   } else {
    u64 ts = bpf_ktime_get_ns();
    u32 key = 0;

    if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0))
     return 0;

    bpf_map_update_elem(&start, &key, &ts, BPF_ANY);
    return 0;
   }
  }

  static int handle_exit(int irq, struct irqaction *action)
  {
   struct irq_key ikey = {};
   struct info *info;
   u32 key = 0;
   u64 delta;
   u64 *tsp;

   if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0))
    return 0;

   tsp = bpf_map_lookup_elem(&start, &key);
   if (!tsp)
    return 0;

   delta = bpf_ktime_get_ns() - *tsp;
   if (!targ_ns)
    delta /= 1000U;

   bpf_probe_read_kernel_str(&ikey.name, sizeof(ikey.name), BPF_CORE_READ(action, name));
   info = bpf_map_lookup_or_try_init(&infos, &ikey, &zero);
   if (!info)
    return 0;

   if (!targ_dist) {
    info->count += delta;
   } else {
    u64 slot;

    slot = log2(delta);
    if (slot >= MAX_SLOTS)
     slot = MAX_SLOTS - 1;
    info->slots[slot]++;
   }

   return 0;
  }

  SEC("tp_btf/irq_handler_entry")
  int BPF_PROG(irq_handler_entry_btf, int irq, struct irqaction *action)
  {
   return handle_entry(irq, action);
  }

  SEC("tp_btf/irq_handler_exit")
  int BPF_PROG(irq_handler_exit_btf, int irq, struct irqaction *action)
  {
   return handle_exit(irq, action);
  }

  SEC("raw_tp/irq_handler_entry")
  int BPF_PROG(irq_handler_entry, int irq, struct irqaction *action)
  {
   return handle_entry(irq, action);
  }

  SEC("raw_tp/irq_handler_exit")
  int BPF_PROG(irq_handler_exit, int irq, struct irqaction *action)
  {
   return handle_exit(irq, action);
  }

  char LICENSE[] SEC("license") = "GPL";
  ```

  上述代码定义了四个eBPF程序的入口，其中 `tp_bpf`和 `raw_tp`分别代表使用 BPF Type Format（BTF）和原始 tracepoints 捕获事件。这样可以确保程序在不同内核版本上可以移植和运行

# Part 11：booststrap

+ libbpf简介
  libbpf是一个C语言库，伴随内核版本的分发，用于辅助eBPF程序的加载和运行，它提供了用于与eBPF系统交互的一组C API，使得开发者能够轻松地编写用户态程序来加载和管理eBPF程序，这些用户态程序通常用于分析、监控或者优化系统性能，libbpf的优势如下：

  + 简化eBPF程序的加载、更新和运行过程
  + 它提供了一组易于使用的API，使得开发者能够专注于编写核心逻辑，而不是处理底层的细节
  + 能够确保程序的兼容性
+ BTF简介
  同时libbpf和BTF都是eBPF生态系统的重要组成部分，它们各自在实现跨内核版本兼容方面发挥着关键作用，BTF是一种元数据格式，用于描述eBPF程序中的类型信息，BTF的主要目的是提供一种结构化的方式，以描述内核中的数据结构，以便eBPF程序可以更加轻松地访问和操作它们，BTF在实现跨内核版本兼容方面的关键作用如下：

  + BTF允许eBPF程序访问内核数据结构的详细类型信息，而无需对特定内核版本进行硬编码。这使得eBPF程序可以适应不同版本的内核，从而实现跨内核版本的兼容
  + 通过使用BPF CO-RE（Compile Once，Run Everywhere）技术，eBPF程序可以利用BTF在编译时解析内核数据结构的类型信息，进而生成在不同内核版本上运行的eBPF程序

  结合libbpf和BTF，eBPF程序可以在各种不同版本的内核上运行，而无需为每个内核版本单独编译，这极大地提高了eBPF生态系统的可移植性和兼容性
+ 
+ booststrap
  Booststrap是一个使用libbpf的完整应用，它利用eBPF程序来跟踪内核中的exec()系统调用以及进程的exit()函数，以了解每一个进程何时退出和创建，这两个BPF程序共同工作，使我们能够捕获关于新进程的有趣信息，例如一个进程的生命周期，二进制文件的文件名，并在进程结束的时候收集有趣的统计信息，例如退出代码或者消耗的资源量等，这是深入了解内核内部并观察事物如何真正运作的良好起点，相较于eunomia-bpf工具，libbpf可以在用户态提供更高的可扩展性，不过也带来了额外的复杂度
  Booststrap实际上分为两个部分：内核态和用户态，内核态是一个eBPF程序，它跟踪exec()和exit()系统调用，用户态是一个C语言程序，它使用libbpf库来加载和运行内核态程序，并处理从内核态收集到的信息，下面是Booststrap在内核态中的代码：

  ```c
  #include "vmlinux.h"
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>
  #include <bpf/bpf_core_read.h>
  #include "bootstrap.h"

  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  struct {
      __uint(type, BPF_MAP_TYPE_HASH);
      __uint(max_entries, 8192);
      __type(key, pid_t);
      __type(value, u64);
  } exec_start SEC(".maps");

  struct {
      __uint(type, BPF_MAP_TYPE_RINGBUF);
      __uint(max_entries, 256 * 1024);
  } rb SEC(".maps");

  const volatile unsigned long long min_duration_ns = 0;

  SEC("tp/sched/sched_process_exec")
  int handle_exec(struct trace_event_raw_sched_process_exec *ctx)
  {
      struct task_struct *task;
      unsigned fname_off;
      struct event *e;
      pid_t pid;
      u64 ts;

      /* remember time exec() was executed for this PID */
      pid = bpf_get_current_pid_tgid() >> 32;
      ts = bpf_ktime_get_ns();
      bpf_map_update_elem(&exec_start, &pid, &ts, BPF_ANY);

      /* don't emit exec events when minimum duration is specified */
      if (min_duration_ns)
          return 0;

      /* reserve sample from BPF ringbuf */
      e = bpf_ringbuf_reserve(&rb, sizeof(*e), 0);
      if (!e)
          return 0;

      /* fill out the sample with data */
      task = (struct task_struct *)bpf_get_current_task();

      e->exit_event = false;
      e->pid = pid;
      e->ppid = BPF_CORE_READ(task, real_parent, tgid);
      bpf_get_current_comm(&e->comm, sizeof(e->comm));

      fname_off = ctx->__data_loc_filename & 0xFFFF;
      bpf_probe_read_str(&e->filename, sizeof(e->filename), (void *)ctx + fname_off);

      /* successfully submit it to user-space for post-processing */
      bpf_ringbuf_submit(e, 0);
      return 0;
  }

  SEC("tp/sched/sched_process_exit")
  int handle_exit(struct trace_event_raw_sched_process_template* ctx)
  {
      struct task_struct *task;
      struct event *e;
      pid_t pid, tid;
      u64 id, ts, *start_ts, duration_ns = 0;

      /* get PID and TID of exiting thread/process */
      id = bpf_get_current_pid_tgid();
      pid = id >> 32;
      tid = (u32)id;

      /* ignore thread exits */
      if (pid != tid)
          return 0;

      /* if we recorded start of the process, calculate lifetime duration */
      start_ts = bpf_map_lookup_elem(&exec_start, &pid);
      if (start_ts)
          duration_ns = bpf_ktime_get_ns() - *start_ts;
      else if (min_duration_ns)
          return 0;
      bpf_map_delete_elem(&exec_start, &pid);

      /* if process didn't live long enough, return early */
      if (min_duration_ns && duration_ns < min_duration_ns)
          return 0;

      /* reserve sample from BPF ringbuf */
      e = bpf_ringbuf_reserve(&rb, sizeof(*e), 0);
      if (!e)
          return 0;

      /* fill out the sample with data */
      task = (struct task_struct *)bpf_get_current_task();

      e->exit_event = true;
      e->duration_ns = duration_ns;
      e->pid = pid;
      e->ppid = BPF_CORE_READ(task, real_parent, tgid);
      e->exit_code = (BPF_CORE_READ(task, exit_code) >> 8) & 0xff;
      bpf_get_current_comm(&e->comm, sizeof(e->comm));

      /* send data to user-space for post-processing */
      bpf_ringbuf_submit(e, 0);
      return 0;
  }
  ```

  下面是Booststrap的用户态程序：

  ```c
  #include <argp.h>
  #include <signal.h>
  #include <stdio.h>
  #include <time.h>
  #include <sys/resource.h>
  #include <bpf/libbpf.h>
  #include "bootstrap.h"
  #include "bootstrap.skel.h"

  static struct env {
      bool verbose;
      long min_duration_ms;
  } env;

  const char *argp_program_version = "bootstrap 0.0";
  const char *argp_program_bug_address = "<bpf@vger.kernel.org>";
  const char argp_program_doc[] =
  "BPF bootstrap demo application.\n"
  "\n"
  "It traces process start and exits and shows associated \n"
  "information (filename, process duration, PID and PPID, etc).\n"
  "\n"
  "USAGE: ./bootstrap [-d <min-duration-ms>] [-v]\n";

  static const struct argp_option opts[] = {
      { "verbose", 'v', NULL, 0, "Verbose debug output" },
      { "duration", 'd', "DURATION-MS", 0, "Minimum process duration (ms) to report" },
      {},
  };

  static error_t parse_arg(int key, char *arg, struct argp_state *state)
  {
      switch (key) {
      case 'v':
          env.verbose = true;
          break;
      case 'd':
          errno = 0;
          env.min_duration_ms = strtol(arg, NULL, 10);
          if (errno || env.min_duration_ms <= 0) {
              fprintf(stderr, "Invalid duration: %s\n", arg);
              argp_usage(state);
          }
          break;
      case ARGP_KEY_ARG:
          argp_usage(state);
          break;
      default:
          return ARGP_ERR_UNKNOWN;
      }
      return 0;
  }

  static const struct argp argp = {
      .options = opts,
      .parser = parse_arg,
      .doc = argp_program_doc,
  };

  static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
  {
      if (level == LIBBPF_DEBUG && !env.verbose)
          return 0;
      return vfprintf(stderr, format, args);
  }

  static volatile bool exiting = false;

  static void sig_handler(int sig)
  {
      exiting = true;
  }

  static int handle_event(void *ctx, void *data, size_t data_sz)
  {
      const struct event *e = data;
      struct tm *tm;
      char ts[32];
      time_t t;

      time(&t);
      tm = localtime(&t);
      strftime(ts, sizeof(ts), "%H:%M:%S", tm);

      if (e->exit_event) {
          printf("%-8s %-5s %-16s %-7d %-7d [%u]",
                 ts, "EXIT", e->comm, e->pid, e->ppid, e->exit_code);
          if (e->duration_ns)
              printf(" (%llums)", e->duration_ns / 1000000);
          printf("\n");
      } else {
          printf("%-8s %-5s %-16s %-7d %-7d %s\n",
                 ts, "EXEC", e->comm, e->pid, e->ppid, e->filename);
      }

      return 0;
  }

  int main(int argc, char **argv)
  {
      struct ring_buffer *rb = NULL;
      struct bootstrap_bpf *skel;
      int err;

      /* Parse command line arguments */
      err = argp_parse(&argp, argc, argv, 0, NULL, NULL);
      if (err)
          return err;

      /* Set up libbpf errors and debug info callback */
      libbpf_set_print(libbpf_print_fn);

      /* Cleaner handling of Ctrl-C */
      signal(SIGINT, sig_handler);
      signal(SIGTERM, sig_handler);

      /* Load and verify BPF application */
      skel = bootstrap_bpf__open();
      if (!skel) {
          fprintf(stderr, "Failed to open and load BPF skeleton\n");
          return 1;
      }

      /* Parameterize BPF code with minimum duration parameter */
      skel->rodata->min_duration_ns = env.min_duration_ms * 1000000ULL;

      /* Load & verify BPF programs */
      err = bootstrap_bpf__load(skel);
      if (err) {
          fprintf(stderr, "Failed to load and verify BPF skeleton\n");
          goto cleanup;
      }

      /* Attach tracepoints */
      err = bootstrap_bpf__attach(skel);
      if (err) {
          fprintf(stderr, "Failed to attach BPF skeleton\n");
          goto cleanup;
      }

      /* Set up ring buffer polling */
      rb = ring_buffer__new(bpf_map__fd(skel->maps.rb), handle_event, NULL, NULL);
      if (!rb) {
          err = -1;
          fprintf(stderr, "Failed to create ring buffer\n");
          goto cleanup;
      }

      /* Process events */
      printf("%-8s %-5s %-16s %-7s %-7s %s\n",
             "TIME", "EVENT", "COMM", "PID", "PPID", "FILENAME/EXIT CODE");
      while (!exiting) {
          err = ring_buffer__poll(rb, 100 /* timeout, ms */);
          /* Ctrl-C will cause -EINTR */
          if (err == -EINTR) {
              err = 0;
              break;
          }
          if (err < 0) {
              printf("Error polling perf buffer: %d\n", err);
              break;
          }
      }

  cleanup:
      /* Clean up */
      ring_buffer__free(rb);
      bootstrap_bpf__destroy(skel);

      return err < 0 ? -err : 0;
  }
  ```

# Part 12：profile

+ profile工具
  `profile`工具是基于eBPF实现的，利用了内核中的perf事件进行性能分析，`profile`工具会定期对每个处理器进行采样，以便捕获内核函数和用户空间函数的执行，它可以显示栈回溯的以下信息：

  + 地址：函数调用的内存地址
  + 符号：函数名称
  + 文件名：源代码文件名称
  + 行号：源代码中的行号

  这些信息有助于定位性能瓶颈和代码的优化，甚至可以用于生成火焰图，以便更加直观的查看性能数据
+ 实现原理
  内核态eBPF程序的实现逻辑主要是借助perf event，对程序的堆栈进行定时采样，从而捕获程序的执行流程，其代码实现如下：

  ```c
  #include "vmlinux.h"
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_tracing.h>
  #include <bpf/bpf_core_read.h>

  #include "profile.h"

  char LICENSE[] SEC("license") = "Dual BSD/GPL";

  struct {
      __uint(type, BPF_MAP_TYPE_RINGBUF);
      __uint(max_entries, 256 * 1024);
  } events SEC(".maps");

  SEC("perf_event")
  int profile(void *ctx)
  {
      int pid = bpf_get_current_pid_tgid() >> 32;
      int cpu_id = bpf_get_smp_processor_id();
      struct stacktrace_event *event;
      int cp;

      event = bpf_ringbuf_reserve(&events, sizeof(*event), 0);
      if (!event)
          return 1;

      event->pid = pid;
      event->cpu_id = cpu_id;

      if (bpf_get_current_comm(event->comm, sizeof(event->comm)))
          event->comm[0] = 0;

      event->kstack_sz = bpf_get_stack(ctx, event->kstack, sizeof(event->kstack), 0);

      event->ustack_sz = bpf_get_stack(ctx, event->ustack, sizeof(event->ustack), BPF_F_USER_STACK);

      bpf_ringbuf_submit(event, 0);

      return 0;
  }
  ```

  用户态部分主要负责为每个在线CPU设置perf event并附加eBPF程序，其代码实现如下：

  ```c
  static long perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                  int cpu, int group_fd, unsigned long flags)
  {
      int ret;

      ret = syscall(__NR_perf_event_open, hw_event, pid, cpu, group_fd, flags);
      return ret;
  }

  int main(){
      ...
      for (cpu = 0; cpu < num_cpus; cpu++) {
          /* skip offline/not present CPUs */
          if (cpu >= num_online_cpus || !online_mask[cpu])
              continue;

          /* Set up performance monitoring on a CPU/Core */
          pefd = perf_event_open(&attr, pid, cpu, -1, PERF_FLAG_FD_CLOEXEC);
          if (pefd < 0) {
              fprintf(stderr, "Fail to set up performance monitor on a CPU/Core\n");
              err = -1;
              goto cleanup;
          }
          pefds[cpu] = pefd;

          /* Attach a BPF program on a CPU */
          links[cpu] = bpf_program__attach_perf_event(skel->progs.profile, pefd);
          if (!links[cpu]) {
              err = -1;
              goto cleanup;
          }
      }
      ...
  }
  ```

# Part 13：tcpconnlat

+ TCP简介
  在进行后端开发的时候，时常会用到MySQL、Redis等数据库，或者执行一些RPC远程调用，或者调用其他的RESTful API，这些调用的底层，通常都是基于TCP协议进行的，原因是TCP协议具有可靠连接、错误重传、拥塞控制等优点，目前在网络传输层协议上，TCP的应用程度已经超过了UDP，当然TCP也有一些缺点，如建立连接的延时较长等，因此分析TCP连接延时对网络性能分析、优化以及故障排查都非常有用
  TCP连接的建立过程，通常被称之为“三次握手”（Three-way Handshake）：

  1. 客户端向服务器发送SYN包：客户端通过 `connect()`系统调用发出SYN，这取决于本地的系统调用以及软中断的CPU时间开销
  2. SYN包传送到服务器：这是一次网络传输，涉及的时间取决于网络延迟
  3. 服务器处理SYN包：服务器内核通过软中断接收包，然后将其放入半连接队列，并发送SYN/ACK响应，这主要涉及到了CPU时间开销
  4. SYN/ACK包传送到客户端：这是另外一次网络传输
  5. 客户端处理SYN/ACK：客户端内核接受并处理SYN/ACk包，然后发送ACK，这主要涉及到软中断处理开销
  6. ACK包传送到服务器：这是第三次网络传输
  7. 服务器接收ACK：服务器内核接收并处理ACK，然后将对应的连接从半连接队列移动到全连接队列，这涉及到一次软中断的CPU开销
  8. 唤醒服务端的用户程序：被 `accept`系统调用阻塞的用户进程被唤醒，然后从全队列中取出来已经建立好的连接，涉及到一次上下文切换的开销、

  完整的流程图如下：

  ![alt text](image.png)

+ tcpconnlat的eBPF实现
  
  Linux内核在处理TCP连接时会使用两个队列

  + 半连接队列（SYN队列）：存储那些正在进行三次握手操作的TCP连接，服务器在收到SYN包之后，也会将该连接信息存储在此队列中
  + 全连接队列（Accept队列）：存储已经完成三次握手，等待应用程序调用accept函数的TCP连接，服务器在收到ACK包之后，会创建一个新的连接并将其添加到此队列中
  
  因此tcpconnlat的具体实现就是在跟踪上述两个队列的情况，其中几个主要的跟踪点为：`tcp_v4_connect`、`tcp_v6_connect`、`tcp_ecv_state_process`，这些跟踪点主要位于内核中的TCP/IP网络栈。Linux内核网络栈对TCP连接建立的处理过程就是，首先调用`tcp_v4_connect`或者`tcp_v6_connect`函数，发起TCP连接，然后在收到SYN-ACK包时，通过`tcp_rcv_state_process`函数来处理，在上述关键函数上设置kprobe，就可以在关键时刻得到通知并执行相应的处理代码（对于socket的理解，在Linux网络中，socket是一个抽象的概念，表示一个网络连接的端点，内核中的`struct sock`结构就是对socket的实现）

  内核态代码如下：
  ```c
  #include <vmlinux.h>
  #include <bpf/bpf_helpers.h>
  #include <bpf/bpf_core_read.h>
  #include <bpf/bpf_tracing.h>
  #include "tcpconnlat.h"

  #define AF_INET    2
  #define AF_INET6   10

  const volatile __u64 targ_min_us = 0;
  const volatile pid_t targ_tgid = 0;

  struct piddata {
    char comm[TASK_COMM_LEN];
    u64 ts;
    u32 tgid;
  };

  struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 4096);
    __type(key, struct sock *);
    __type(value, struct piddata);
  } start SEC(".maps");

  struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(u32));
  } events SEC(".maps");

  static int trace_connect(struct sock *sk)
  {
    u32 tgid = bpf_get_current_pid_tgid() >> 32;
    struct piddata piddata = {};

    if (targ_tgid && targ_tgid != tgid)
      return 0;

    bpf_get_current_comm(&piddata.comm, sizeof(piddata.comm));
    piddata.ts = bpf_ktime_get_ns();
    piddata.tgid = tgid;
    bpf_map_update_elem(&start, &sk, &piddata, 0);
    return 0;
  }

  static int handle_tcp_rcv_state_process(void *ctx, struct sock *sk)
  {
    struct piddata *piddatap;
    struct event event = {};
    s64 delta;
    u64 ts;

    if (BPF_CORE_READ(sk, __sk_common.skc_state) != TCP_SYN_SENT)
      return 0;

    piddatap = bpf_map_lookup_elem(&start, &sk);
    if (!piddatap)
      return 0;

    ts = bpf_ktime_get_ns();
    delta = (s64)(ts - piddatap->ts);
    if (delta < 0)
      goto cleanup;

    event.delta_us = delta / 1000U;
    if (targ_min_us && event.delta_us < targ_min_us)
      goto cleanup;
    __builtin_memcpy(&event.comm, piddatap->comm,
        sizeof(event.comm));
    event.ts_us = ts / 1000;
    event.tgid = piddatap->tgid;
    event.lport = BPF_CORE_READ(sk, __sk_common.skc_num);
    event.dport = BPF_CORE_READ(sk, __sk_common.skc_dport);
    event.af = BPF_CORE_READ(sk, __sk_common.skc_family);
    if (event.af == AF_INET) {
      event.saddr_v4 = BPF_CORE_READ(sk, __sk_common.skc_rcv_saddr);
      event.daddr_v4 = BPF_CORE_READ(sk, __sk_common.skc_daddr);
    } else {
      BPF_CORE_READ_INTO(&event.saddr_v6, sk,
          __sk_common.skc_v6_rcv_saddr.in6_u.u6_addr32);
      BPF_CORE_READ_INTO(&event.daddr_v6, sk,
          __sk_common.skc_v6_daddr.in6_u.u6_addr32);
    }
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU,
        &event, sizeof(event));

  cleanup:
    bpf_map_delete_elem(&start, &sk);
    return 0;
  }

  SEC("kprobe/tcp_v4_connect")
  int BPF_KPROBE(tcp_v4_connect, struct sock *sk)
  {
    return trace_connect(sk);
  }

  SEC("kprobe/tcp_v6_connect")
  int BPF_KPROBE(tcp_v6_connect, struct sock *sk)
  {
    return trace_connect(sk);
  }

  SEC("kprobe/tcp_rcv_state_process")
  int BPF_KPROBE(tcp_rcv_state_process, struct sock *sk)
  {
    return handle_tcp_rcv_state_process(ctx, sk);
  }

  SEC("fentry/tcp_v4_connect")
  int BPF_PROG(fentry_tcp_v4_connect, struct sock *sk)
  {
    return trace_connect(sk);
  }

  SEC("fentry/tcp_v6_connect")
  int BPF_PROG(fentry_tcp_v6_connect, struct sock *sk)
  {
    return trace_connect(sk);
  }

  SEC("fentry/tcp_rcv_state_process")
  int BPF_PROG(fentry_tcp_rcv_state_process, struct sock *sk)
  {
    return handle_tcp_rcv_state_process(ctx, sk);
  }

  char LICENSE[] SEC("license") = "GPL";
  ```

  用户态数据处理是使用`perf_buffer__poll`来接收并处理从内核发送到用户态的eBPF事件，`perf_buffer__poll`是libbpf库提供的一个便捷函数，用于轮询perf event buffer并处理接收到的数据，获取数据之后调用回调函数处理内核态发送到用户态的数据：
  ```c
  void handle_event(void* ctx, int cpu, void* data, __u32 data_sz) {
      const struct event* e = data;
      char src[INET6_ADDRSTRLEN];
      char dst[INET6_ADDRSTRLEN];
      union {
          struct in_addr x4;
          struct in6_addr x6;
      } s, d;
      static __u64 start_ts;

      if (env.timestamp) {
          if (start_ts == 0)
              start_ts = e->ts_us;
          printf("%-9.3f ", (e->ts_us - start_ts) / 1000000.0);
      }
      if (e->af == AF_INET) {
          s.x4.s_addr = e->saddr_v4;
          d.x4.s_addr = e->daddr_v4;
      } else if (e->af == AF_INET6) {
          memcpy(&s.x6.s6_addr, e->saddr_v6, sizeof(s.x6.s6_addr));
          memcpy(&d.x6.s6_addr, e->daddr_v6, sizeof(d.x6.s6_addr));
      } else {
          fprintf(stderr, "broken event: event->af=%d", e->af);
          return;
      }

      if (env.lport) {
          printf("%-6d %-12.12s %-2d %-16s %-6d %-16s %-5d %.2f\n", e->tgid,
                e->comm, e->af == AF_INET ? 4 : 6,
                inet_ntop(e->af, &s, src, sizeof(src)), e->lport,
                inet_ntop(e->af, &d, dst, sizeof(dst)), ntohs(e->dport),
                e->delta_us / 1000.0);
      } else {
          printf("%-6d %-12.12s %-2d %-16s %-16s %-5d %.2f\n", e->tgid, e->comm,
                e->af == AF_INET ? 4 : 6, inet_ntop(e->af, &s, src, sizeof(src)),
                inet_ntop(e->af, &d, dst, sizeof(dst)), ntohs(e->dport),
                e->delta_us / 1000.0);
      }
  }
  ```

# Part 14：tcpstates
+ tcprtt和tcpstates
  
  当一个TCP连接建立的时候，`tcprtt`会自动根据当前系统的状况，选择合适的执行函数，在执行函数中，`tcprtt`会收集到TCP链接的各项基本信息，如源地址、目标地址、源端口、目标端口、耗时等等，并将这些信息更新到直方图型的BPF map中，运行结束之后，`tcprtt`会根据用户态代码，将收集到的信息以图形化的方式展示给用户，`tcpstates`则是一个专门用来追踪和打印TCP连接状态变化的工具，可以显示TCP连接在每一个状态中的停留时长，单位时间为毫秒，例如对于一个单独的TCP会话，`tcpstates`可以打印出类似以下的输出：

  ```console
  SKADDR           C-PID C-COMM     LADDR           LPORT RADDR           RPORT OLDSTATE    -> NEWSTATE    MS
  ffff9fd7e8192000 22384 curl       100.66.100.185  0     52.33.159.26    80    CLOSE       -> SYN_SENT    0.000
  ffff9fd7e8192000 0     swapper/5  100.66.100.185  63446 52.33.159.26    80    SYN_SENT    -> ESTABLISHED 1.373
  ffff9fd7e8192000 22384 curl       100.66.100.185  63446 52.33.159.26    80    ESTABLISHED -> FIN_WAIT1   176.042
  ffff9fd7e819

  2000 0     swapper/5  100.66.100.185  63446 52.33.159.26    80    FIN_WAIT1   -> FIN_WAIT2   0.536
  ffff9fd7e8192000 0     swapper/5  100.66.100.185  63446 52.33.159.26    80    FIN_WAIT2   -> CLOSE       0.006
  ```

  可以看出以上输出中，最多的时间被花在了ESTABLISHED状态，也就连接已经建立并在传输数据的状态，这个状态到FIN_WAIT1状态，（开始关闭连接的状态）的转变过程中耗费了176.042ms。

+ tcpstate的实现

  对于状态的转变，与之相关的系统调用为`inet_sock_set_state`，因此tcpstate的内核态代码如下：
  ```c
  const volatile bool filter_by_sport = false;
  const volatile bool filter_by_dport = false;
  const volatile short target_family = 0;

  struct {
      __uint(type, BPF_MAP_TYPE_HASH);
      __uint(max_entries, MAX_ENTRIES);
      __type(key, __u16);
      __type(value, __u16);
  } sports SEC(".maps");

  struct {
      __uint(type, BPF_MAP_TYPE_HASH);
      __uint(max_entries, MAX_ENTRIES);
      __type(key, __u16);
      __type(value, __u16);
  } dports SEC(".maps");

  struct {
      __uint(type, BPF_MAP_TYPE_HASH);
      __uint(max_entries, MAX_ENTRIES);
      __type(key, struct sock *);
      __type(value, __u64);
  } timestamps SEC(".maps");

  struct {
      __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
      __uint(key_size, sizeof(__u32));
      __uint(value_size, sizeof(__u32));
  } events SEC(".maps");

  SEC("tracepoint/sock/inet_sock_set_state")
  int handle_set_state(struct trace_event_raw_inet_sock_set_state *ctx)
  {
      struct sock *sk = (struct sock *)ctx->skaddr;
      __u16 family = ctx->family;
      __u16 sport = ctx->sport;
      __u16 dport = ctx->dport;
      __u64 *tsp, delta_us, ts;
      struct event event = {};

      if (ctx->protocol != IPPROTO_TCP)
          return 0;

      if (target_family && target_family != family)
          return 0;

      if (filter_by_sport && !bpf_map_lookup_elem(&sports, &sport))
          return 0;

      if (filter_by_dport && !bpf_map_lookup_elem(&dports, &dport))
          return 0;

      tsp = bpf_map_lookup_elem(&timestamps, &sk);
      ts = bpf_ktime_get_ns();
      if (!tsp)
          delta_us = 0;
      else
          delta_us = (ts - *tsp) / 1000;

      event.skaddr = (__u64)sk;
      event.ts_us = ts / 1000;
      event.delta_us = delta_us;
      event.pid = bpf_get_current_pid_tgid() >> 32;
      event.oldstate = ctx->oldstate;
      event.newstate = ctx->newstate;
      event.family = family;
      event.sport = sport;
      event.dport = dport;
      bpf_get_current_comm(&event.task, sizeof(event.task));

      if (family == AF_INET) {
          bpf_probe_read_kernel(&event.saddr, sizeof(event.saddr), &sk->__sk_common.skc_rcv_saddr);
          bpf_probe_read_kernel(&event.daddr, sizeof(event.daddr), &sk->__sk_common.skc_daddr);
      } else { /* family == AF_INET6 */
          bpf_probe_read_kernel(&event.saddr, sizeof(event.saddr), &sk->__sk_common.skc_v6_rcv_saddr.in6_u.u6_addr32);
          bpf_probe_read_kernel(&event.daddr, sizeof(event.daddr), &sk->__sk_common.skc_v6_daddr.in6_u.u6_addr32);
      }

      bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));

      if (ctx->newstate == TCP_CLOSE)
          bpf_map_delete_elem(&timestamps, &sk);
      else
          bpf_map_update_elem(&timestamps, &sk, &ts, BPF_ANY);

      return 0;
  }
  ```
  主要还是依赖于tracepoint来捕获TCP连接的状态变化，而在用户态中，主要是通过libbpf来加载eBPF程序，然后通过perf_event来接收内核中的事件数据：
  ```c
  static void handle_event(void* ctx, int cpu, void* data, __u32 data_sz) {
      char ts[32], saddr[26], daddr[26];
      struct event* e = data;
      struct tm* tm;
      int family;
      time_t t;

      if (emit_timestamp) {
          time(&t);
          tm = localtime(&t);
          strftime(ts, sizeof(ts), "%H:%M:%S", tm);
          printf("%8s ", ts);
      }

      inet_ntop(e->family, &e->saddr, saddr, sizeof(saddr));
      inet_ntop(e->family, &e->daddr, daddr, sizeof(daddr));
      if (wide_output) {
          family = e->family == AF_INET ? 4 : 6;
          printf(
              "%-16llx %-7d %-16s %-2d %-26s %-5d %-26s %-5d %-11s -> %-11s "
              "%.3f\n",
              e->skaddr, e->pid, e->task, family, saddr, e->sport, daddr,
              e->dport, tcp_states[e->oldstate], tcp_states[e->newstate],
              (double)e->delta_us / 1000);
      } else {
          printf(
              "%-16llx %-7d %-10.10s %-15s %-5d %-15s %-5d %-11s -> %-11s %.3f\n",
              e->skaddr, e->pid, e->task, saddr, e->sport, daddr, e->dport,
              tcp_states[e->oldstate], tcp_states[e->newstate],
              (double)e->delta_us / 1000);
      }
  }
  ```
  每当内核有新的事件到达用户态时，就会调用回调函数`handle_event`，将二进制的IP地址转换成人类可读的格式，并输出包括事件时间戳、源IP地址、源端口、目标IP地址、目标端口等信息

+ tcprtt的实现

  由于tcprtt是一个用于测量TCP往返时间（Round Trip Time，RTT）的程序，并将RTT信息统计到一个histogram中，其内核态代码如下：
  ```c
  struct {
      __uint(type, BPF_MAP_TYPE_HASH);
      __uint(max_entries, MAX_ENTRIES);
      __type(key, u64);
      __type(value, struct hist);
  } hists SEC(".maps");

  static struct hist zero;

  SEC("fentry/tcp_rcv_established")
  int BPF_PROG(tcp_rcv, struct sock *sk)
  {
      const struct inet_sock *inet = (struct inet_sock *)(sk);
      struct tcp_sock *ts;
      struct hist *histp;
      u64 key, slot;
      u32 srtt;

      if (targ_sport && targ_sport != inet->inet_sport)
          return 0;
      if (targ_dport && targ_dport != sk->__sk_common.skc_dport)
          return 0;
      if (targ_saddr && targ_saddr != inet->inet_saddr)
          return 0;
      if (targ_daddr && targ_daddr != sk->__sk_common.skc_daddr)
          return 0;

      if (targ_laddr_hist)
          key = inet->inet_saddr;
      else if (targ_raddr_hist)
          key = inet->sk.__sk_common.skc_daddr;
      else
          key = 0;
      histp = bpf_map_lookup_or_try_init(&hists, &key, &zero);
      if (!histp)
          return 0;
      ts = (struct tcp_sock *)(sk);
      srtt = BPF_CORE_READ(ts, srtt_us) >> 3;
      if (targ_ms)
          srtt /= 1000U;
      slot = log2l(srtt);
      if (slot >= MAX_SLOTS)
          slot = MAX_SLOTS - 1;
      __sync_fetch_and_add(&histp->slots[slot], 1);
      if (targ_show_ext) {
          __sync_fetch_and_add(&histp->latency, srtt);
          __sync_fetch_and_add(&histp->cnt, 1);
      }
      return 0;
  }
  ```
  tcprtt代码建议使用eunomia-bpf进行编译运行

# Part 15：javagc

  + USDT介绍

    USDT是一种在应用程序中插入静态跟踪点的机制，它允许开发者在关键的位置插入可用于调试和性能分析的探针，这些探针可以被DTrace、SystemTap或者eBPF等工具动态激活，从而在不重启应用程序或者更改程序代码的情况下，获取程序的内部状态和性能指标，USDT在很多开源软件，如MySQL、PostgreSQL、Ruby、Python和Node.js等都有广泛的应用。显然用户级的动态跟踪是一个非常强大的能力，可以解决无数的问题，然而，使用它也有一些困难：需要确定需要跟踪的代码，处理函数的参数，以及对应代码的更改。

    用户级静态定义跟踪则可以在某一些程度上解决这些问题，USDT探针是开发者在代码关键位置插入的跟踪宏，提供稳定且有文档说明的API，这使得跟踪工作变得更加简单，例如使用USDT，我们可以简单的跟踪一个名为`mysql:query__start`的探针，而不是去跟踪名为`_Z16dispatch_command19enum_server_commandP3THDPcj`的C++符号，也就是`dispatch_command()`函数

  + Java GC介绍

    Java作为一种高级语言，其自动垃圾回收（GC）是其核心特性之一，Java GC的目标是自动地回收那些不再被程序使用的内存空间，从而减轻程序员在内存管理方面的负担，然而GC过程可能会引发应用程序的卡顿，对程序的性能和响应时间产生影响，因此对Java GC事件进行监控和分析对于理解和优化Java应用的性能是非常重要的，下面是利用eBPF和USDT来监控和分析Java GC事件耗时的例子

    内核态的代码如下：
    ```c
    #include <vmlinux.h>
    #include <bpf/bpf_helpers.h>
    #include <bpf/bpf_core_read.h>
    #include <bpf/usdt.bpf.h>
    #include "javagc.h"

    struct {
        __uint(type, BPF_MAP_TYPE_HASH);
        __uint(max_entries, 100);
        __type(key, uint32_t);
        __type(value, struct data_t);
    } data_map SEC(".maps");

    struct {
        __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
        __type(key, int);
        __type(value, int);
    } perf_map SEC(".maps");

    __u32 time;

    static int gc_start(struct pt_regs *ctx)
    {
        struct data_t data = {};

        data.cpu = bpf_get_smp_processor_id();
        data.pid = bpf_get_current_pid_tgid() >> 32;
        data.ts = bpf_ktime_get_ns();
        bpf_map_update_elem(&data_map, &data.pid, &data, 0);
        return 0;
    }

    static int gc_end(struct pt_regs *ctx)
    {
        struct data_t data = {};
        struct data_t *p;
        __u32 val;

        data.cpu = bpf_get_smp_processor_id();
        data.pid = bpf_get_current_pid_tgid() >> 32;
        data.ts = bpf_ktime_get_ns();
        p = bpf_map_lookup_elem(&data_map, &data.pid);
        if (!p)
            return 0;

        val = data.ts - p->ts;
        if (val > time) {
            data.ts = val;
            bpf_perf_event_output(ctx, &perf_map, BPF_F_CURRENT_CPU, &data, sizeof(data));
        }
        bpf_map_delete_elem(&data_map, &data.pid);
        return 0;
    }

    SEC("usdt")
    int handle_gc_start(struct pt_regs *ctx)
    {
        return gc_start(ctx);
    }

    SEC("usdt")
    int handle_gc_end(struct pt_regs *ctx)
    {
        return gc_end(ctx);
    }

    SEC("usdt")
    int handle_mem_pool_gc_start(struct pt_regs *ctx)
    {
        return gc_start(ctx);
    }

    SEC("usdt")
    int handle_mem_pool_gc_end(struct pt_regs *ctx)
    {
        return gc_end(ctx);
    }

    char LICENSE[] SEC("license") = "Dual BSD/GPL";
    ```

    注意到上述内核态代码中并未声明挂载点，只是声明该钩子函数是USDT类型的，实际上具体的挂载需要在用户态代码中完成，用户态代码如下：
    ```c
    skel->links.handle_mem_pool_gc_start = bpf_program__attach_usdt(skel->progs.handle_gc_start, env.pid,
                                    binary_path, "hotspot", "mem__pool__gc__begin", NULL);
    if (!skel->links.handle_mem_pool_gc_start) {
        err = errno;
        fprintf(stderr, "attach usdt mem__pool__gc__begin failed: %s\n", strerror(err));
        goto cleanup;
    }

    skel->links.handle_mem_pool_gc_end = bpf_program__attach_usdt(skel->progs.handle_gc_end, env.pid,
                                binary_path, "hotspot", "mem__pool__gc__end", NULL);
    if (!skel->links.handle_mem_pool_gc_end) {
        err = errno;
        fprintf(stderr, "attach usdt mem__pool__gc__end failed: %s\n", strerror(err));
        goto cleanup;
    }

    skel->links.handle_gc_start = bpf_program__attach_usdt(skel->progs.handle_gc_start, env.pid,
                                    binary_path, "hotspot", "gc__begin", NULL);
    if (!skel->links.handle_gc_start) {
        err = errno;
        fprintf(stderr, "attach usdt gc__begin failed: %s\n", strerror(err));
        goto cleanup;
    }

    skel->links.handle_gc_end = bpf_program__attach_usdt(skel->progs.handle_gc_end, env.pid,
                binary_path, "hotspot", "gc__end", NULL);
    if (!skel->links.handle_gc_end) {
        err = errno;
        fprintf(stderr, "attach usdt gc__end failed: %s\n", strerror(err));
        goto cleanup;
    }
    ```
# Part 16: memleak

  + 内存泄漏
    
    内存泄漏是计算机编程中的一种常见问题，内存泄漏发生时，程序会逐渐消耗更多的内存资源，但并未正确释放，随着时间的推移，这种行为会导致系统的内存被逐渐耗尽，从而显著降低程序以及系统的整体性能。eBPF则提供了一种高效的机制来监控和追踪系统级别的事件，包括内存的分配和释放，其原理在于，eBPF可以跟踪内存分配和释放的请求，并收集每次分配的调用堆栈，之后通过分析这些信息，找出执行了内存分配但并没有执行释放操作的调用堆栈，这有助于我们找出导致内存泄漏的源头，这种方式的优点在于无需暂停正在运行的应用程序

  + memleak的实现

    对于用户态的常用内存分配函数，如`malloc`和`calloc`等，`memleak`利用了用户态探测（uprobe）技术来实现监控；对于内核态的内存分配函数，如`kmalloc`等，`memleak`使用tracepoint来实现监控，内核态的代码实现如下：
    ```c
    const volatile size_t min_size = 0;
    const volatile size_t max_size = -1;
    const volatile size_t page_size = 4096;
    const volatile __u64 sample_rate = 1;
    const volatile bool trace_all = false;
    const volatile __u64 stack_flags = 0;
    const volatile bool wa_missing_free = false;

    struct {
        __uint(type, BPF_MAP_TYPE_HASH);
        __type(key, pid_t);
        __type(value, u64);
        __uint(max_entries, 10240);
    } sizes SEC(".maps");

    struct {
        __uint(type, BPF_MAP_TYPE_HASH);
        __type(key, u64); /* address */
        __type(value, struct alloc_info);
        __uint(max_entries, ALLOCS_MAX_ENTRIES);
    } allocs SEC(".maps");

    struct {
        __uint(type, BPF_MAP_TYPE_HASH);
        __type(key, u64); /* stack id */
        __type(value, union combined_alloc_info);
        __uint(max_entries, COMBINED_ALLOCS_MAX_ENTRIES);
    } combined_allocs SEC(".maps");

    struct {
        __uint(type, BPF_MAP_TYPE_HASH);
        __type(key, u64);
        __type(value, u64);
        __uint(max_entries, 10240);
    } memptrs SEC(".maps");

    struct {
        __uint(type, BPF_MAP_TYPE_STACK_TRACE);
        __type(key, u32);
    } stack_traces SEC(".maps");

    static union combined_alloc_info initial_cinfo;

    static int gen_alloc_enter(size_t size)
    {
        if (size < min_size || size > max_size)
            return 0;

        if (sample_rate > 1) {
            if (bpf_ktime_get_ns() % sample_rate != 0)
                return 0;
        }

        const pid_t pid = bpf_get_current_pid_tgid() >> 32;
        bpf_map_update_elem(&sizes, &pid, &size, BPF_ANY);

        if (trace_all)
            bpf_printk("alloc entered, size = %lu\n", size);

        return 0;
    }

    static int gen_alloc_exit2(void *ctx, u64 address)
    {
        const pid_t pid = bpf_get_current_pid_tgid() >> 32;
        struct alloc_info info;

        const u64* size = bpf_map_lookup_elem(&sizes, &pid);
        if (!size)
            return 0; // missed alloc entry

        __builtin_memset(&info, 0, sizeof(info));

        info.size = *size;
        bpf_map_delete_elem(&sizes, &pid);

        if (address != 0) {
            info.timestamp_ns = bpf_ktime_get_ns();

            info.stack_id = bpf_get_stackid(ctx, &stack_traces, stack_flags);

            bpf_map_update_elem(&allocs, &address, &info, BPF_ANY);

            update_statistics_add(info.stack_id, info.size);
        }

        if (trace_all) {
            bpf_printk("alloc exited, size = %lu, result = %lx\n",
                    info.size, address);
        }

        return 0;
    }

    static int gen_alloc_exit(struct pt_regs *ctx)
    {
        return gen_alloc_exit2(ctx, PT_REGS_RC(ctx));
    }

    SEC("uprobe")
    int BPF_KPROBE(malloc_enter, size_t size)
    {
        // 记录分配开始的相关信息
        return gen_alloc_enter(size);
    }

    SEC("uretprobe")
    int BPF_KRETPROBE(malloc_exit)
    {
        // 记录分配结束的相关信息
        return gen_alloc_exit(ctx);
    }

    SEC("uprobe")
    int BPF_KPROBE(free_enter, void *address)
    {
        // 记录释放开始的相关信息
        return gen_free_enter(address);
    }
    ```

    用户态程序负责挂载内核态函数，设置并管理BPF map，处理从BPF程序收集到的数据，下面主要列出用户态的挂载部分：
    ```c
    int attach_uprobes(struct memleak_bpf *skel)
    {
        ATTACH_UPROBE_CHECKED(skel, malloc, malloc_enter);
        ATTACH_URETPROBE_CHECKED(skel, malloc, malloc_exit);

        ATTACH_UPROBE_CHECKED(skel, calloc, calloc_enter);
        ATTACH_URETPROBE_CHECKED(skel, calloc, calloc_exit);

        ATTACH_UPROBE_CHECKED(skel, realloc, realloc_enter);
        ATTACH_URETPROBE_CHECKED(skel, realloc, realloc_exit);

        ATTACH_UPROBE_CHECKED(skel, mmap, mmap_enter);
        ATTACH_URETPROBE_CHECKED(skel, mmap, mmap_exit);

        ATTACH_UPROBE_CHECKED(skel, posix_memalign, posix_memalign_enter);
        ATTACH_URETPROBE_CHECKED(skel, posix_memalign, posix_memalign_exit);

        ATTACH_UPROBE_CHECKED(skel, memalign, memalign_enter);
        ATTACH_URETPROBE_CHECKED(skel, memalign, memalign_exit);

        ATTACH_UPROBE_CHECKED(skel, free, free_enter);
        ATTACH_UPROBE_CHECKED(skel, munmap, munmap_enter);

        // the following probes are intentinally allowed to fail attachment

        // deprecated in libc.so bionic
        ATTACH_UPROBE(skel, valloc, valloc_enter);
        ATTACH_URETPROBE(skel, valloc, valloc_exit);

        // deprecated in libc.so bionic
        ATTACH_UPROBE(skel, pvalloc, pvalloc_enter);
        ATTACH_URETPROBE(skel, pvalloc, pvalloc_exit);

        // added in C11
        ATTACH_UPROBE(skel, aligned_alloc, aligned_alloc_enter);
        ATTACH_URETPROBE(skel, aligned_alloc, aligned_alloc_exit);

        return 0;
    }
    ```

# Part 19：lsm-connect

  + LSM概述

    LSM（Linux Security Modules）是Linux内核中用于支持各种计算机安全模型的框架，其原理是LSM在Linux内核安全相关的关键路径上预置了一批hook点，从而实现了内核和安全模块的解耦，使得不同的安全模块能够自由地在内核中加载/卸载，无需修改原有的内核代码

  + 



