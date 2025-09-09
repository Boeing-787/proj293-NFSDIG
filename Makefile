# Makefile

# 定义变量
TARGET_GOARCH := amd64
BPFTOOL := go install github.com/cilium/ebpf/cmd/bpf2go@latest
EXECUTABLE := nfstrace
CC ?= gcc

# 默认目标
all: build

# 确保 bpf2go 工具已安装
dlv:
	sudo dlv --headless --listen=:2345 --api-version=2 exec ./exe/nfstrace --check-go-version=false

bpf2go:
	$(BPFTOOL)

generate: bpf2go
	TARGET_GOARCH=amd64 go generate

# 构建可执行文件
build: generate
	CGO_ENABLED=0  go build -o exe/$(EXECUTABLE)

# 构建XDP程序
build-xdp:
	cd bpf && bpf2go -cc clang -cflags "-O2 -g" xdp bpf/xdp.c

# 构建所有内容
build-all: build-xdp build

run: build
	sudo ./exe/$(EXECUTABLE)

# 清理生成的文件
clean:
	@rm -f *_bpfel.go
	@rm -f *_bpfel.o

cleanlog:
	@rm -f ./traceOutput/**/*.log
	@rm -f ./output/**/*.csv
	@rm -f ./nfs_output/**/*.csv
	@rm -f ./nfs_op_anomalies.csv
# 打印帮助信息
help:
	@echo "Available targets:"
	@echo "  all         - Build the project (default)"
	@echo "  bpf2go      - Install bpf2go tool"
	@echo "  generate    - Run go generate"
	@echo "  build       - Build the executable"
	@echo "  build-xdp   - Build XDP eBPF program"
	@echo "  build-all   - Build XDP program and executable"
	@echo "  install-deps- Install required dependencies"
	@echo "  clean       - Clean up generated files"
	@echo "  help        - Print this help message"

.PHONY: all bpf2go generate build build-xdp build-all run clean cleanlog install-deps help