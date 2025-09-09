# 构建阶段 - 使用Go官方镜像（已经装好Go 1.23）
FROM golang:1.23 AS builder

# 安装eBPF相关工具, apt install clang libelf1 libelf-dev zlib1g-dev (libbpf相关依赖) 
# libbfd, llvm, libcap， libbfd-dev libcap-dev， bpftool
RUN apt-get update && apt-get install -y \
    clang \
    llvm \
    libelf1 \
    libelf-dev \
    zlib1g-dev \
    libbfd-dev \
    libcap-dev \
    libbpf-dev \
    linux-headers-generic \
    bpftool \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY go.mod go.sum ./

# 清除系统代理设置，避免影响Go模块下载
# ENV HTTP_PROXY=
# ENV HTTPS_PROXY=
# ENV http_proxy=
# ENV https_proxy=
# ENV no_proxy=*

# 配置Go代理 - 使用国内镜像源
ENV GOPROXY=https://goproxy.cn,direct
ENV GOSUMDB=sum.golang.google.cn

# 下载依赖
RUN go mod download

# 安装 bpf2go
RUN go install github.com/cilium/ebpf/cmd/bpf2go@latest

# 复制源码
COPY . .

# 构建参数
ARG TARGETARCH
ARG TARGETOS

# 设置环境变量
ENV TARGET_GOARCH=$TARGETARCH
ENV CGO_ENABLED=1

# 编译
RUN make build GOARCH=$TARGETARCH GOOS=$TARGETOS

# 运行阶段 - 轻量级镜像
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    ca-certificates \
    libelf1 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root/

# 复制编译结果
COPY --from=builder /app/nfsdig ./nfsdig

# 创建必要的目录
RUN mkdir -p /sys/fs/bpf

# 启动
CMD ["./nfsdig"]