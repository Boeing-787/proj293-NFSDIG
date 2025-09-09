OUTPUT := .output
CLANG ?= clang
CC ?= gcc
LIBBPF_SRC := ./libbpf/src
LIBBPF_OBJ := $(abspath $(OUTPUT)/libbpf.a)
LIBBLAZESYM_SRC := $(abspath ./blazesym/)
LIBBLAZESYM_INC := $(abspath $(LIBBLAZESYM_SRC)/capi/include)
LIBBLAZESYM_OBJ := $(abspath $(OUTPUT)/libblazesym_c.a)
VMLINUX := ../bpf/headers/vmlinux.h
INCLUDES := -I$(OUTPUT) -I../libbpf/include/uapi -I$(dir $(VMLINUX)) -I$(LIBBLAZESYM_INC)
BPFTOOL_OUTPUT ?= $(abspath $(OUTPUT)/bpftool)
CFLAGS := -g -Wall
ALL_LDFLAGS := $(LDFLAGS) $(EXTRA_LDFLAGS) # LDFLAGS 没有在 Makefile 里定义，是为了让用户可以自定义。这是 Makefile 的通用写法，方便灵活扩展和兼容不同环境。
ARCH := $(shell uname -m | sed 's/x86_64/x86/')

APPS = minimal_ns ps_time bootstrap vfsstat syscount opensnoop

CARGO ?= $(shell which cargo) # 判断系统中是否安装了 cargo 工具，并据此决定是否编译与 blazesym 相关的 progile 程序。
ifeq ($(strip $(CARGO)),)
BZS_APPS :=
else
BZS_APPS := profile
APPS += $(BZS_APPS)
# Required by libblazesym
ALL_LDFLAGS += -lrt -ldl -lpthread -lm
endif

# 这行代码会自动获取 Clang 默认的系统 include 路径，并将其转换为 -idirafter 形式。
# -idirafter 选项告诉编译器：只有在前面的 -I 路径找不到头文件时，才去这些目录查找，避免系统头文件“抢优先级”。
# 这样做的目的是保证 BPF 程序编译时能找到必要的内核头文件（如 asm/types.h、asm/byteorder.h 等），而不会因为系统架构或发行版不同而缺失。
CLANG_BPF_SYS_INCLUDES ?= $(shell $(CLANG) -v -E - </dev/null 2>&1 \
	| sed -n '/<...> search starts here:/,/End of search list./{ s| \(/.*\)|-idirafter \1|p }')

COMMON_OBJ = \
	$(OUTPUT)/trace_helpers.o \
	$(OUTPUT)/btf_helpers.o \
	$(OUTPUT)/uprobe_helpers.o \
	$(OUTPUT)/syscall_helpers.o \
	$(OUTPUT)/errno_helpers.o \
	# $(OUTPUT)/compat.o \
	# $(OUTPUT)/path_helpers.o \
	# $(OUTPUT)/map_helpers.o \



# 美化输出
ifeq ($(V),1)
	Q =
	msg =
else
	Q = @
	msg = @printf '  %-8s %s%s\n'					\
		      "$(1)"						\
		      "$(patsubst $(abspath $(OUTPUT))/%,%,$(2))"	\
		      "$(if $(3), $(3))";
	MAKEFLAGS += --no-print-directory
endif

.PHONY: all
all: $(APPS)

.PHONY: clean
clean:
	$(call msg,CLEAN)
	$(Q)rm -rf $(OUTPUT) ../exe/$(APPS)

# 创建必要的目录
$(OUTPUT) $(OUTPUT)/libbpf $(BPFTOOL_OUTPUT) :
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@


# Build libbpf
$(LIBBPF_OBJ): $(wildcard $(LIBBPF_SRC)/*.[ch] $(LIBBPF_SRC)/Makefile) | $(OUTPUT)/libbpf
	$(call msg,LIB,$@)
	$(Q)$(MAKE) -C $(LIBBPF_SRC) BUILD_STATIC_ONLY=1		      \
		    OBJDIR=$(dir $@)/libbpf DESTDIR=$(dir $@)		      \
		    INCLUDEDIR= LIBDIR= UAPIDIR=			      \
		    install

$(LIBBLAZESYM_SRC)/target/release/libblazesym_c.a::
	$(Q)cd $(LIBBLAZESYM_SRC) && $(CARGO) build --package=blazesym-c --release

$(LIBBLAZESYM_OBJ): $(LIBBLAZESYM_SRC)/target/release/libblazesym_c.a | $(OUTPUT)
	$(call msg,LIB, $@)
	$(Q)cp $(LIBBLAZESYM_SRC)/target/release/libblazesym_c.a $@

# Build BPF code
$(OUTPUT)/%.bpf.o: %.bpf.c $(LIBBPF_OBJ) $(wildcard %.h) $(VMLINUX) | $(OUTPUT) 
	$(call msg,BPF,$@)
	$(Q)$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH)		      \
		     $(INCLUDES) $(CLANG_BPF_SYS_INCLUDES)		      \
		     -c $(filter %.c,$^) -o $(patsubst %.bpf.o,%.tmp.bpf.o,$@)
	$(Q)bpftool gen object $@ $(patsubst %.bpf.o,%.tmp.bpf.o,$@)

# Generate BPF skeletons
$(OUTPUT)/%.skel.h: $(OUTPUT)/%.bpf.o | $(OUTPUT)
	$(call msg,GEN-SKEL,$@)
	$(Q)bpftool gen skeleton $< > $@

# Build user-space code，对于 APPS 列表中的每个程序（如 minimal、kprobe 等），其对应的 .o 文件都依赖于对应的 .skel.h 文件
$(patsubst %,$(OUTPUT)/%.o,$(APPS)): %.o: %.skel.h

$(OUTPUT)/%.o: %.c $(wildcard %.h) | $(OUTPUT)
	$(call msg,CC,$@)
	$(Q)$(CC) $(CFLAGS) $(INCLUDES) -c $(filter %.c,$^) -o $@

$(patsubst %,$(OUTPUT)/%.o,$(BZS_APPS)): $(LIBBLAZESYM_OBJ)

$(BZS_APPS): $(LIBBLAZESYM_OBJ)

# Build application binary
$(APPS): %: $(OUTPUT)/%.o $(LIBBPF_OBJ) $(COMMON_OBJ) |  $(OUTPUT)
	$(call msg,BINARY,$@)
	$(Q)$(CC) $(CFLAGS) $^ $(ALL_LDFLAGS) -lelf -lz -o ../exe/$@

# delete failed targets
.DELETE_ON_ERROR:

# keep intermediate (.skel.h, .bpf.o, etc) targets
.SECONDARY: