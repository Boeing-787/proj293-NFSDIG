// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2020 Anton Protopopov
//
// Based on vfsstat(8) from BCC by Brendan Gregg
#include <argp.h>
#include <unistd.h>
#include <time.h>
#include <bpf/bpf.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>
#include <string.h>
#include "vfsstat.h"
#include "vfsstat.skel.h"
#include "btf_helpers.h"
#include "trace_helpers.h"

const char *argp_program_version = "vfsstat 0.1";
const char *argp_program_bug_address =
	"https://github.com/iovisor/bcc/tree/master/libbpf-tools";
static const char argp_program_doc[] =
	"\nvfsstat: Count some VFS calls\n"
	"\n"
	"EXAMPLES:\n"
	"    vfsstat      # interval one second\n"
	"    vfsstat 5 3  # interval five seconds, three output lines\n"
	"    vfsstat -o vfs.csv  # output to CSV file\n";
static char args_doc[] = "[interval [count]]";

static const struct argp_option opts[] = {
	{ "verbose", 'v', NULL, 0, "Verbose debug output", 0 },
	{ "output", 'o', "FILE", 0, "Output file (default: ./traceOutput/vfs.csv)", 0 },
	{ NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help", 0 },
	{},
};

static struct env {
	bool verbose;
	int count;
	int interval;
	char *output_file;
	FILE *output_fp;
} env = {
	.interval = 1,	/* once a second */
	.output_file = "./traceOutput/vfs.csv",
	.output_fp = NULL,
};

static int ensure_directory_exists(const char *path)
{
	char *dir_path = strdup(path);
	char *last_slash = strrchr(dir_path, '/');
	
	if (last_slash) {
		*last_slash = '\0';
		if (strlen(dir_path) > 0) {
			if (mkdir(dir_path, 0755) != 0 && errno != EEXIST) {
				free(dir_path);
				return -1;
			}
		}
	}
	
	free(dir_path);
	return 0;
}

static error_t parse_arg(int key, char *arg, struct argp_state *state)
{
	long interval;
	long count;

	switch (key) {
	case 'h':
		argp_state_help(state, stderr, ARGP_HELP_STD_HELP);
		break;
	case 'v':
		env.verbose = true;
		break;
	case 'o':
		env.output_file = arg;
		break;
	case ARGP_KEY_ARG:
		switch (state->arg_num) {
		case 0:
			errno = 0;
			interval = strtol(arg, NULL, 10);
			if (errno || interval <= 0 || interval > INT_MAX) {
				fprintf(stderr, "invalid interval: %s\n", arg);
				argp_usage(state);
			}
			env.interval = interval;
			break;
		case 1:
			errno = 0;
			count = strtol(arg, NULL, 10);
			if (errno || count < 0 || count > INT_MAX) {
				fprintf(stderr, "invalid count: %s\n", arg);
				argp_usage(state);
			}
			env.count = count;
			break;
		default:
			argp_usage(state);
			break;
		}
		break;
	default:
		return ARGP_ERR_UNKNOWN;
	}
	return 0;
}

static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
	if (level == LIBBPF_DEBUG && !env.verbose)
		return 0;
	return vfprintf(stderr, format, args);
}

static const char *stat_types_names[] = {
	[S_READ] = "READ",
	[S_WRITE] = "WRITE",
	[S_FSYNC] = "FSYNC",
	[S_OPEN] = "OPEN",
	[S_CREATE] = "CREATE",
	[S_UNLINK] = "UNLINK",
	[S_MKDIR] = "MKDIR",
	[S_RMDIR] = "RMDIR",
};

static void print_header(void)
{
	int i;

	if (env.output_fp) {
		/* CSV header */
		fprintf(env.output_fp, "TIME");
		for (i = 0; i < S_MAXSTAT; i++)
			fprintf(env.output_fp, ",%s", stat_types_names[i]);
		fprintf(env.output_fp, "\n");
	} else {
		/* Console header */
		printf("%-8s  ", "TIME");
		for (i = 0; i < S_MAXSTAT; i++)
			printf(" %6s/s", stat_types_names[i]);
		printf("\n");
	}
}

static void print_and_reset_stats(__u64 stats[S_MAXSTAT])
{
	char s[16];
	__u64 val;
	int i;

	str_timestamp("%H:%M:%S", s, sizeof(s));
	
	if (env.output_fp) {
		/* CSV format */
		fprintf(env.output_fp, "%s", s);
		for (i = 0; i < S_MAXSTAT; i++) {
			val = __atomic_exchange_n(&stats[i], 0, __ATOMIC_RELAXED);
			fprintf(env.output_fp, ",%llu", val / env.interval);
		}
		fprintf(env.output_fp, "\n");
		fflush(env.output_fp);  /* Ensure data is written immediately */
	} else {
		/* Console format */
		printf("%-8s: ", s);
		for (i = 0; i < S_MAXSTAT; i++) {
			val = __atomic_exchange_n(&stats[i], 0, __ATOMIC_RELAXED);
			printf(" %8llu", val / env.interval);
		}
		printf("\n");
	}
}

int main(int argc, char **argv)
{
	LIBBPF_OPTS(bpf_object_open_opts, open_opts);
	static const struct argp argp = {
		.options = opts,
		.parser = parse_arg,
		.doc = argp_program_doc,
		.args_doc = args_doc,
	};
	struct vfsstat_bpf *skel;
	int err;

	err = argp_parse(&argp, argc, argv, 0, NULL, NULL);
	if (err)
		return err;

	/* Setup output file if specified */
	if (env.output_file && strcmp(env.output_file, "-") != 0) {
		/* Ensure directory exists */
		if (ensure_directory_exists(env.output_file) != 0) {
			fprintf(stderr, "Failed to create directory for output file: %s\n", env.output_file);
			return 1;
		}
		
		/* Open output file */
		env.output_fp = fopen(env.output_file, "w");
		if (!env.output_fp) {
			fprintf(stderr, "Failed to open output file %s: %s\n", env.output_file, strerror(errno));
			return 1;
		}
	}

	libbpf_set_print(libbpf_print_fn);


	err = ensure_core_btf(&open_opts);
	if (err) {
		fprintf(stderr, "failed to fetch necessary BTF for CO-RE: %s\n", strerror(-err));
		return 1;
	}

	skel = vfsstat_bpf__open();
	if (!skel) {
		fprintf(stderr, "failed to open BPF skelect\n");
		return 1;
	}


	/* It fallbacks to kprobes when kernel does not support fentry. */
	if (fentry_can_attach("vfs_read", NULL)) {
		bpf_program__set_autoload(skel->progs.kprobe_vfs_read, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_write, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_fsync, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_open, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_create, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_unlink, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_mkdir, false);
		bpf_program__set_autoload(skel->progs.kprobe_vfs_rmdir, false);
	} else {
		bpf_program__set_autoload(skel->progs.fentry_vfs_read, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_write, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_fsync, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_open, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_create, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_unlink, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_mkdir, false);
		bpf_program__set_autoload(skel->progs.fentry_vfs_rmdir, false);
	}

	err = vfsstat_bpf__load(skel);
	if (err) {
		fprintf(stderr, "failed to load BPF skelect: %d\n", err);
		goto cleanup;
	}

	if (!skel->bss) {
		fprintf(stderr, "Memory-mapping BPF maps is supported starting from Linux 5.7, please upgrade.\n");
		goto cleanup;
	}

	err = vfsstat_bpf__attach(skel);
	if (err) {
		fprintf(stderr, "failed to attach BPF programs: %s\n",
				strerror(-err));
		goto cleanup;
	}

	print_header();
	do {
		sleep(env.interval);
		print_and_reset_stats(skel->bss->stats);
	} while (!env.count || --env.count);

cleanup:
	/* Close output file if opened */
	if (env.output_fp) {
		fclose(env.output_fp);
		env.output_fp = NULL;
	}
	
	vfsstat_bpf__destroy(skel);
	cleanup_core_btf(&open_opts);

	return err != 0;
}
