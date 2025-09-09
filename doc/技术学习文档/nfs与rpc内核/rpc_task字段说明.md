## rpc_task:
### flags:
支持的 flag 列表如下：
0x0001: ASYNC —— 异步执行模式。
0x0002: SWAPPER —— 由 swapper 线程处理。
0x0004: MOVEABLE —— 可移动的任务。
0x0010: NULLCREDS —— 不需要凭证。
0x0020: MAJORSEEN —— 已经看到主要请求。
0x0080: DYNAMIC —— 动态分配的任务。
0x0100: NO_ROUND_ROBIN —— 不使用轮询调度。
0x0200: SOFT —— 软超时。
0x0400: SOFTCONN —— 软连接。
0x0800: SENT —— 请求已发送。
0x1000: TIMEOUT —— 设置了超时。
0x2000: NOCONNECT —— 不尝试连接。
0x4000: NORTO —— 不使用 RTT（往返时间）估算。
0x8000: CRED_NOREF —— 凭证没有引用计数。

### runstate:
支持的状态如下：
(1UL << 0): RUNNING —— 正在运行。
(1UL << 1): QUEUED —— 处于队列中等待执行。
(1UL << 2): ACTIVE —— 活跃状态（可能正在通信）。
(1UL << 3): NEED_XMIT —— 需要发送数据。
(1UL << 4): NEED_RECV —— 需要接收数据。
(1UL << 5): MSG_PIN_WAIT —— 等待消息 pin。
(1UL << 6): SIGNALLED —— 被信号中断。

### action:
表示当前任务所执行的具体操作函数指针。

### status:
表示当前任务的执行状态或错误代码。