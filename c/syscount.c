// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright (c) 2020 Anton Protopopov
//
// Based on syscount(8) from BCC by Sasha Goldshtein
#include <unistd.h>
#include <signal.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
#include <argp.h>
#include <bpf/bpf.h>
#include "syscount.h"
#include "syscount.skel.h"
#include "errno_helpers.h"
#include "syscall_helpers.h"
#include "btf_helpers.h"
#include "trace_helpers.h"

/**
 * 扩展的数据结构，用于排序和显示
 * 在data_t基础上添加了key字段，用于排序
 */
struct data_ext_t {
	__u64 count;                    /**< 系统调用次数 */
	__u64 total_ns;                 /**< 总延迟时间（纳秒） */
	char comm[TASK_COMM_LEN];       /**< 进程名称 */
	__u32 key;                      /**< 系统调用ID或进程ID */
};


/** 警告输出宏，将消息输出到标准错误流 */
#define warn(...) fprintf(stderr, __VA_ARGS__)

const char *argp_program_version = "syscount 0.1";
const char *argp_program_bug_address =
	"https://github.com/iovisor/bcc/tree/master/libbpf-tools";
static const char argp_program_doc[] =
"\nsyscount: summarize syscall counts and latencies\n"
"\n"
"EXAMPLES:\n"
"    syscount                 # print top 10 syscalls by count every second\n"
"    syscount -p $(pidof dd)  # look only at a particular process\n"
"    syscount -L              # measure and sort output by latency\n"
"    syscount -P              # group statistics by pid, not by syscall\n"
"    syscount -x -i 5         # count only failed syscalls\n"
"    syscount -e ENOENT -i 5  # count only syscalls failed with a given errno\n"
"    syscount -c CG           # Trace process under cgroupsPath CG\n";
;

/**
 * 命令行选项定义数组
 * 定义所有可用的命令行参数
 */
static const struct argp_option opts[] = {
	{ "verbose", 'v', NULL, 0, "Verbose debug output", 0 },
	{ "pid", 'p', "PID", 0, "Process PID to trace", 0 },
	{ "interval", 'i', "INTERVAL", 0, "Print summary at this interval"
				" (seconds), 0 for infinite wait (default)", 0 },
	{ "duration", 'd', "DURATION", 0, "Total tracing duration (seconds)", 0 },

	{ "cgroup", 'c', "/sys/fs/cgroup/unified/<CG>", 0, "Trace process in cgroup path", 0 },
	{ "failures", 'x', NULL, 0, "Trace only failed syscalls", 0 },
	{ "latency", 'L', NULL, 0, "Collect syscall latency", 0 },
	{ "milliseconds", 'm', NULL, 0, "Display latency in milliseconds"
					" (default: microseconds)", 0 },
	{ "process", 'P', NULL, 0, "Count by process and not by syscall", 0 },
	{ "errno", 'e', "ERRNO", 0, "Trace only syscalls that return this error"
				 "(numeric or EPERM, etc.)", 0 },
	{ "syscalls", 'S', "SYSCALLS", 0, "Trace multiple syscalls (comma-separated list like 'read,write,open')", 0 },
	{ "list", 'l', NULL, 0, "Print list of recognized syscalls and exit", 0 },
	{ "outdir", 'o', "OUTDIR", 0, "指定输出目录，默认: ../traceOutput/", 0 },
	{ "trace", 't', NULL, 0, "启用跟踪输出模式（输出每个系统调用事件）", 0 },
	{ NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help", 0 },
	{},
};

/**
 * 全局环境变量结构体
 * 存储程序运行时的各种配置参数
 */
static struct env {
	bool list_syscalls;             /**< 是否列出所有系统调用并退出 */
	bool milliseconds;              /**< 是否以毫秒为单位显示时间 */
	bool failures;                  /**< 是否只跟踪失败的系统调用 */
	bool verbose;                   /**< 是否启用详细输出 */
	bool latency;                   /**< 是否测量和显示延迟 */
	bool process;                   /**< 是否按进程分组而不是按系统调用分组 */
	int filter_errno;               /**< 过滤特定的错误码 */
	char *filter_syscalls;          /**< 过滤特定的系统调用列表 */
	int interval;                   /**< 输出间隔（秒） */
	int duration;                   /**< 总运行时间（秒） */
	pid_t pid;                      /**< 过滤特定进程ID */
	char *cgroupspath;              /**< cgroup路径 */
	bool cg;                        /**< 是否启用cgroup过滤 */
	char *out_dir;                 /**< 输出目录 */
	bool trace_mode;                /**< 是否启用跟踪输出模式 */
} env = {
	.interval = 1,  /**< 默认每秒输出一次 */
	.out_dir = "/home/shasha/nfsdig/traceOutput",
	.latency = 1,
	.filter_syscalls = "read,write,open,close,lseek,mmap,munmap,flock,fsync,mkdir,rmdir,readahead,fsopen,fsconfig,fstat",
	.trace_mode = true, 
};

/**
 * 解析字符串为整数，并验证范围
 * @param arg: 要解析的字符串
 * @param ret: 输出参数，存储解析后的整数值
 * @param min: 最小值限制
 * @param max: 最大值限制
 * @return: 0表示成功，-1表示失败
 */
static int get_int(const char *arg, int *ret, int min, int max)
{
	char *end;
	long val;

	errno = 0;
	val = strtol(arg, &end, 10);
	if (errno) {
		warn("strtol: %s: %s\n", arg, strerror(errno));
		return -1;
	} else if (end == arg || val < min || val > max) {
		return -1;
	}
	if (ret)
		*ret = val;
	return 0;
}

/**
 * libbpf库的打印回调函数
 * 根据verbose模式控制是否输出调试信息
 * @param level: 打印级别
 * @param format: 格式化字符串
 * @param args: 可变参数列表
 * @return: 打印的字符数
 */
static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
	if (level == LIBBPF_DEBUG && !env.verbose)
		return 0;

	return vfprintf(stderr, format, args);
}








/**
 * 解析env.filter_syscalls，得到系统调用号数组
 * 只需要传入env.filter_syscalls，返回实际数量，syscall_ids数组存放结果
 * 只校验系统调用名是否规范
 */
static int parse_filter_syscalls(const char *filter_syscalls, int *syscall_ids, int max_ids)
{

	int count = 0;
	char *tmp = strdup(filter_syscalls);
	char *saveptr = NULL;
	char *token = strtok_r(tmp, ",", &saveptr);

	while (token && count < max_ids) {
		// 去除前后空格
		while (*token == ' ' || *token == '\t') token++;
		char *end = token + strlen(token) - 1;
		while (end > token && (*end == ' ' || *end == '\t')) *end-- = '\0';

		int id = syscall_id(token);
		if (id >= 0) {
			syscall_ids[count++] = id;
		} else {
			warn("无效的系统调用名: %s\n", token);
		}
		token = strtok_r(NULL, ",", &saveptr);
	}
	free(tmp);
	return count;
}

/**
 * 解析vals数组，输出filter_syscalls指定的系统调用信息，格式为：
 * Time,<syscall1>_latency,<syscall2>_latency,...
 * @param vals: 数据数组
 * @param count: vals数组长度
 * @param syscall_ids: 需要输出的系统调用号数组
 * @param filter_count: syscall_ids数组长度
 * @param fp: 输出文件指针
 */
static void print_metric(struct data_ext_t *vals, size_t count, const int *syscall_ids, int filter_count, FILE *fp)
{
	size_t i, j;
	double latencies[filter_count];

	// 初始化延迟和计数为0
	for (i = 0; i < (size_t)filter_count; i++) {
		latencies[i] = 0.0;
	}

	// 遍历vals，找到每个syscall_id对应的数据
	for (i = 0; i < (size_t)filter_count; i++) {
		int id = syscall_ids[i];
		for (j = 0; j < count; j++) {
			if ((int)vals[j].key == id) {
				if (vals[j].count > 0) {
					if (env.milliseconds)
						latencies[i] = (double)vals[j].total_ns / 1000000.0 / vals[j].count;
					else
						latencies[i] = (double)vals[j].total_ns / 1000.0 / vals[j].count;
				} else {
					latencies[i] = 0.0;
				}
				break;
			}
		}
		// 如果没有找到，latencies[i]和counts[i]已经是0
	}

	// 打印时间戳
	time_t now = time(NULL);
	struct tm tm;
	char timebuf[32] = "";
	if (localtime_r(&now, &tm))
		snprintf(timebuf, sizeof(timebuf), "%02d:%02d:%02d", tm.tm_hour, tm.tm_min, tm.tm_sec);

	// 输出一行，格式为：Time,<syscall1>_latency,<syscall2>_latency,...
	fprintf(fp, "%s", timebuf);
	for (i = 0; i < (size_t)filter_count; i++) {
		fprintf(fp, ",%.3lf", latencies[i]);
	}
	fprintf(fp, "\n");
	fflush(fp);  /* 立即刷新缓冲区，确保数据写入文件 */
}


	



/** 是否启用批量映射操作，用于提高性能 */
static bool batch_map_ops = true; /* hope for the best */

/**
 * 批量读取BPF映射中的数据（高性能版本）
 * 使用bpf_map_lookup_and_delete_batch API批量操作
 * @param fd: BPF映射文件描述符
 * @param vals: 输出数据数组
 * @param count: 输入输出参数，输入为最大数量，输出为实际读取数量
 * @return: 0表示成功，负数表示错误码
 */
static int read_vals_batch(int fd, struct data_ext_t *vals, __u32 *count)
{
	struct data_t orig_vals[*count];
	void *in = NULL, *out;
	__u32 i, n, n_read = 0;
	__u32 keys[*count];
	int err = 0;

	while (n_read < *count && !err) {
		n = *count - n_read;
		err = bpf_map_lookup_and_delete_batch(fd, &in, &out,
				keys + n_read, orig_vals + n_read, &n, NULL);
		if (err < 0 && err != -ENOENT) {
			/* we want to propagate EINVAL upper, so that
			 * the batch_map_ops flag is set to false */
			if (err != -EINVAL)
				warn("bpf_map_lookup_and_delete_batch: %s\n",
				     strerror(-err));
			return err;
		}
		n_read += n;
		in = out;
	}

	for (i = 0; i < n_read; i++) {
		vals[i].count = orig_vals[i].count;
		vals[i].total_ns = orig_vals[i].total_ns;
		vals[i].key = keys[i];
		strncpy(vals[i].comm, orig_vals[i].comm, TASK_COMM_LEN);
	}

	*count = n_read;
	return 0;
}

/**
 * 读取BPF映射中的数据
 * 优先使用批量操作，失败时回退到逐个操作
 * @param fd: BPF映射文件描述符
 * @param vals: 输出数据数组
 * @param count: 输入输出参数，输入为最大数量，输出为实际读取数量
 * @return: true表示成功，false表示失败
 */
static bool read_vals(int fd, struct data_ext_t *vals, __u32 *count)
{
	__u32 keys[MAX_ENTRIES];
	struct data_t val;
	__u32 key = -1;
	__u32 next_key;
	int i = 0, j;
	int err;

	if (batch_map_ops) {
		err = read_vals_batch(fd, vals, count);
		if (err < 0 && err == -EINVAL) {
			/* fall back to a racy variant */
			batch_map_ops = false;
		} else {
			return err >= 0;
		}
	}

	if (!vals || !count || !*count)
		return true;

	for (key = -1; i < *count; ) {
		err = bpf_map_get_next_key(fd, &key, &next_key);
		if (err && errno != ENOENT) {
			warn("failed to get next key: %s\n", strerror(errno));
			return false;
		} else if (err) {
			break;
		}
		key = keys[i++] = next_key;
	}

	for (j = 0; j < i; j++) {
		err = bpf_map_lookup_elem(fd, &keys[j], &val);
		if (err && errno != ENOENT) {
			warn("failed to lookup element: %s\n", strerror(errno));
			return false;
		}
		vals[j].count = val.count;
		vals[j].total_ns = val.total_ns;
		vals[j].key = keys[j];
		memcpy(vals[j].comm, val.comm, TASK_COMM_LEN);
	}

	/* There is a race here: system calls which are represented by keys
	 * above and happened between lookup and delete will be ignored.  This
	 * will be fixed in future by using bpf_map_lookup_and_delete_batch,
	 * but this function is too fresh to use it in bcc. */

	for (j = 0; j < i; j++) {
		err = bpf_map_delete_elem(fd, &keys[j]);
		if (err) {
			warn("failed to delete element: %s\n", strerror(errno));
			return false;
		}
	}

	*count = i;
	return true;
}

// 添加读取event映射的函数
/**
 * 读取BPF ring buffer中的事件数据
 * @param ringbuf: ring buffer对象
 * @param events: 输出事件数组
 * @param max_events: 最大事件数量
 * @return: 实际读取的事件数量
 */
static int event_count = 0;
static struct sys_event_t *g_events = NULL;
static int g_max_events = 0;

/* 接收来自ring buffer的事件 */
static int event_handler(void *ctx, void *data, size_t size)
{
	struct sys_event_t *event = data;
	
	if (event_count >= g_max_events)
		return 0; // 停止处理
		
	g_events[event_count++] = *event;
	return 0;
}

static int read_events(struct ring_buffer *ringbuf, struct sys_event_t *events, int max_events)
{
	// 设置全局变量供回调函数使用
	g_events = events;
	g_max_events = max_events;
	event_count = 0;
	
	// 处理ring buffer中的数据
	ring_buffer__poll(ringbuf, 100); // 100ms超时
	
	return event_count;
}

// 添加跟踪输出格式的打印函数
/**
 * 打印跟踪输出格式（每个系统调用事件一行）
 * @param events: 事件数组
 * @param event_count: 事件数量
 * @param syscall_ids: 过滤的系统调用ID数组
 * @param filter_count: 过滤的系统调用数量
 * @param fp: 输出文件指针
 */
static void print_trace(struct sys_event_t *events, int event_count, const int *syscall_ids, int filter_count, FILE *fp)
{
	int i, j;
	char namebuf[64];
	
	for (i = 0; i < event_count; i++) {
		// 检查是否在过滤列表中
		int found = 0;
		for (j = 0; j < filter_count; j++) {
			if (events[i].id == syscall_ids[j]) {
				found = 1;
				break;
			}
		}
		if (!found)
			continue;
		
		// 获取系统调用名称
		if (syscall_name(events[i].id, namebuf, sizeof(namebuf)) < 0)
			snprintf(namebuf, sizeof(namebuf), "[unknown:%ld]", events[i].id);
		
		// 计算延迟时间
		double latency = env.milliseconds ? (events[i].latency / 1000000.0) : (events[i].latency / 1000.0);
		
		// 生成时间戳
		time_t now = time(NULL);
		struct tm tm;
		char timebuf[32] = "";
		if (localtime_r(&now, &tm))
			snprintf(timebuf, sizeof(timebuf), "%02d:%02d:%02d", tm.tm_hour, tm.tm_min, tm.tm_sec);
		
		// 输出格式：Time,PID,Comm,Syscall,Latency,Return
		fprintf(fp, "%s,%d,%s,%s,%.3lf,%ld\n",
			timebuf, events[i].pid, events[i].comm, namebuf, latency, events[i].ret);
		fflush(fp);  /* 立即刷新缓冲区，确保数据写入文件 */
	}
}

/**
 * 命令行参数解析函数
 * 处理各种命令行选项，设置相应的环境变量
 * @param key: 参数键值
 * @param arg: 参数值
 * @param state: argp状态
 * @return: 0表示成功，ARGP_ERR_UNKNOWN表示未知参数
 */
static error_t parse_arg(int key, char *arg, struct argp_state *state)
{
	int number;
	int err;

	switch (key) {
	case 'h':
		argp_state_help(state, stderr, ARGP_HELP_STD_HELP);
		break;
	case 'v':
		env.verbose = true;
		break;
	case 'x':
		env.failures = true;
		break;
	case 'L':
		env.latency = true;
		break;
	case 'm':
		env.milliseconds = true;
		break;
	case 'P':
		env.process = true;
		break;
	case 'p':
		err = get_int(arg, &env.pid, 1, INT_MAX);
		if (err) {
			warn("invalid PID: %s\n", arg);
			argp_usage(state);
		}
		break;
	case 'i':
		err = get_int(arg, &env.interval, 0, INT_MAX);
		if (err) {
			warn("invalid INTERVAL: %s\n", arg);
			argp_usage(state);
		}
		break;
	case 'd':
		err = get_int(arg, &env.duration, 1, INT_MAX);
		if (err) {
			warn("invalid DURATION: %s\n", arg);
			argp_usage(state);
		}
		break;

	case 'c':
		env.cgroupspath = arg;
		env.cg = true;
		break;
	case 'e':
		err = get_int(arg, &number, 1, INT_MAX);
		if (err) {
			number = errno_by_name(arg);
			if (number < 0) {
				warn("invalid errno: %s (bad, or can't "
				     "parse dynamically; consider using "
				     "numeric value and/or installing the "
				     "errno program from moreutils)\n", arg);
				argp_usage(state);
			}
		}
		env.filter_errno = number;
		break;
	case 'l':
		env.list_syscalls = true;
		break;
	case 'S':
		env.filter_syscalls = arg;
		break;
	case 'o':
		env.out_dir = arg;
		break;
	case 't':
		env.trace_mode = true;
		break;
	default:
		return ARGP_ERR_UNKNOWN;
	}
	return 0;
}

/** 控制主循环的标志，1表示继续运行，0表示退出 */
static volatile sig_atomic_t hang_on = 1;

/**
 * SIGINT信号处理函数
 * 当用户按Ctrl+C时，设置hang_on为false，退出主循环
 * @param signo: 信号编号
 */
void sig_int(int signo)
{
	hang_on = 0;
}

/**
 * 主函数
 * 程序入口点，负责：
 * 1. 解析命令行参数
 * 2. 初始化BPF程序和映射
 * 3. 设置信号处理
 * 4. 进入主循环，定期读取和显示统计数据
 * @param argc: 参数个数
 * @param argv: 参数数组
 * @return: 0表示成功，非0表示失败
 */
int main(int argc, char **argv)
{
	LIBBPF_OPTS(bpf_object_open_opts, open_opts);  /**< BPF对象打开选项 */
	// void (*print)(struct data_ext_t *, size_t);    /**< 打印函数指针 */
	// int (*compar)(const void *, const void *);     /**< 比较函数指针 */
	/**
	 * argp配置结构体
	 * 用于命令行参数解析
	 */
	static const struct argp argp = {
		.options = opts,        /**< 选项定义数组 */
		.parser = parse_arg,    /**< 参数解析函数 */
		.doc = argp_program_doc, /**< 程序文档 */
	};
	struct data_ext_t vals[MAX_ENTRIES];  /**< 数据数组，存储从BPF映射读取的数据 */
	struct syscount_bpf *obj;             /**< BPF程序对象 */
	int seconds = 0;                      /**< 运行时间计数器 */
	__u32 count;                          /**< 数据项数量 */
	int err;                              /**< 错误码 */
	int idx, cg_map_fd;                   /**< cgroup相关变量 */
	int cgfd = -1;                        /**< cgroup文件描述符 */

	// 初始化系统调用名称映射表
	init_syscall_names();

	// 解析命令行参数
	err = argp_parse(&argp, argc, argv, 0, NULL, NULL);

	// 如果开启了 verbose 模式，调试系统调用名称映射
	if (env.verbose) {
		printf("DEBUG: Testing syscall name mapping...\n");
		int test_ids[] = {0, 1, 2, 3, 4};  // read, write, open, close, stat
		char *test_names[] = {"read", "write", "open", "close", "stat"};
		for (int i = 0; i < 5; i++) {
			int id = syscall_id(test_names[i]);
			char name[64];
			if (syscall_name(test_ids[i], name, sizeof(name)) == 0) {
				printf("DEBUG: %s -> %d, %d -> %s\n", test_names[i], id, test_ids[i], name);
			}
		}
	}
	// 如果参数解析出错，释放资源并退出
	if (err)
		goto free_names;

	// 如果指定了 --list 选项，打印所有支持的系统调用并退出
	if (env.list_syscalls) {
		list_syscalls();
		goto free_names;
	}

	// 设置 libbpf 的打印回调
	libbpf_set_print(libbpf_print_fn);

	// 检查并加载 CO-RE 需要的 BTF 信息
	err = ensure_core_btf(&open_opts);
	if (err) {
		fprintf(stderr, "failed to fetch necessary BTF for CO-RE: %s\n", strerror(-err));
		return 1;
	}

	// 打开 BPF 对象
	obj = syscount_bpf__open_opts(&open_opts);
	if (!obj) {
		warn("failed to open BPF object\n");
		err = 1;
		goto free_names;
	}

	// 根据命令行参数设置 BPF 程序的过滤条件
	if (env.pid)
		obj->rodata->filter_pid = env.pid;
	if (env.failures)
		obj->rodata->filter_failed = true;
	if (env.latency)
		obj->rodata->measure_latency = true;
	if (env.process)
		obj->rodata->count_by_process = true;
	if (env.filter_errno)
		obj->rodata->filter_errno = env.filter_errno;
	if (env.cg)
		obj->rodata->filter_cg = env.cg;

	// 加载 BPF 程序
	err = syscount_bpf__load(obj);
	if (err) {
		warn("failed to load BPF object: %s\n", strerror(-err));
		goto cleanup_obj;
	}

	// 如果指定了 cgroup 路径，则将 cgroup fd 写入 BPF 映射
	if (env.cg) {
		idx = 0;
		cg_map_fd = bpf_map__fd(obj->maps.cgroup_map);
		cgfd = open(env.cgroupspath, O_RDONLY);
		if (cgfd < 0) {
			fprintf(stderr, "Failed opening Cgroup path: %s", env.cgroupspath);
			goto cleanup_obj;
		}
		if (bpf_map_update_elem(cg_map_fd, &idx, &cgfd, BPF_ANY)) {
			fprintf(stderr, "Failed adding target cgroup to map");
			goto cleanup_obj;
		}
	}

	// 挂载 sys_exit 程序
	obj->links.sys_exit = bpf_program__attach(obj->progs.sys_exit);
	if (!obj->links.sys_exit) {
		err = -errno;
		warn("failed to attach sys_exit program: %s\n", strerror(-err));
		goto cleanup_obj;
	}

	
	// 如果需要统计延迟，则还要挂载 sys_enter 程序
	if (env.latency) {
		obj->links.sys_enter = bpf_program__attach(obj->progs.sys_enter);
		if (!obj->links.sys_enter) {
			err = -errno;
			warn("failed to attach sys_enter programs: %s\n",
			     strerror(-err));
			goto cleanup_obj;
		}
	}

	// 设置信号处理函数，支持 Ctrl+C 退出
	if (signal(SIGINT, sig_int) == SIG_ERR) {
		warn("can't set signal handler: %s\n", strerror(errno));
		goto cleanup_obj;
	}

	FILE *fp = NULL;
	int syscall_ids[MAX_ENTRIES];
	int filter_count = 0;
	char out_path[512];
	struct ring_buffer *ring_buf = NULL;
	struct sys_event_t events[MAX_ENTRIES];  // 改为数组而不是指针
	
	// 解析系统调用过滤列表
	if (env.filter_syscalls && env.filter_syscalls[0]) {
		filter_count = parse_filter_syscalls(env.filter_syscalls, syscall_ids, MAX_ENTRIES);
		if (filter_count <= 0) {
			warn("未指定有效的系统调用过滤列表\n");
			goto cleanup_obj;
		}
	} else {
		warn("未指定系统调用过滤列表\n");
		goto cleanup_obj;
	}
	
	// 构造输出文件路径
	if (env.out_dir && env.out_dir[0]) {
		if (env.trace_mode) {
			snprintf(out_path, sizeof(out_path), "%s/syscall_trace.csv", env.out_dir);
		} else {
			snprintf(out_path, sizeof(out_path), "%s/syscall_metric.csv", env.out_dir);
		}
		fp = fopen(out_path, "w");
		if (!fp) {
			warn("无法打开输出文件: %s\n", out_path);
			return 0;
		}
		
		// 根据输出模式打印不同的表头
		if (env.trace_mode) {
			// 跟踪模式表头：Time,PID,Comm,Syscall,Latency,Return
			fprintf(fp, "Time,PID,Comm,Syscall,Latency,Return\n");
			fflush(fp);
		} else {
			// 指标模式表头：Time + 每个系统调用的Latency
			fprintf(fp, "Time");
			for (int i = 0; i < filter_count; i++) {
				char namebuf[64];
				if (syscall_name(syscall_ids[i], namebuf, sizeof(namebuf)) < 0)
					snprintf(namebuf, sizeof(namebuf), "[unknown:%d]", syscall_ids[i]);
				fprintf(fp, ",%s_latency", namebuf);
			}
			fprintf(fp, "\n");
			fflush(fp);
		}
	} else {
		fp = stdout;
	}
	
	// 如果是跟踪模式，初始化ring buffer
	if (env.trace_mode) {
		ring_buf = ring_buffer__new(bpf_map__fd(obj->maps.events), event_handler, NULL, NULL);
		if (!ring_buf) {
			warn("无法创建ring buffer\n");
			goto cleanup_obj;
		}
	}
	
	// 主循环：定时读取BPF映射数据，排序并打印
	printf("Tracing syscalls, %s mode, printing results every %d second(s)... Ctrl+C to quit.\n", 
		env.trace_mode ? "trace" : "metric", env.interval ?: 1);
	
	while (hang_on) {
		// 休眠 interval 秒
		sleep(env.interval ?: 1);
		// 如果设置了 duration，累加秒数，到达后退出
		if (env.duration) {
			seconds += env.interval ?: 1;
			if (seconds >= env.duration)
				hang_on = 0;
		}
		// interval 为 0 时只打印一次
		if (hang_on && !env.interval)
			continue;

		if (env.trace_mode) {
			// 跟踪模式：读取并输出每个事件
			int event_count = read_events(ring_buf, events, MAX_ENTRIES);
			if (event_count > 0) {
				print_trace(events, event_count, syscall_ids, filter_count, fp);
			}
		} else {
			// 指标模式：读取聚合数据并输出
			count = MAX_ENTRIES;
			if (!read_vals(bpf_map__fd(obj->maps.data), vals, &count))
				break;
			if (!count)
				continue;
			print_metric(vals, count, syscall_ids, filter_count, fp);
		}
	}
	
	// 清理资源
cleanup_obj:
	syscount_bpf__destroy(obj);
	if (ring_buf) {
		ring_buffer__free(ring_buf);
	}
	if (fp && fp != stdout) {
		fclose(fp);
		fp = NULL;
	}
	// ... rest of cleanup ...
free_names:
	free_syscall_names();
	cleanup_core_btf(&open_opts);
	if (cgfd > 0)
		close(cgfd);

	return err != 0;
}
