# NFSDig Docker 使用说明

## 构建镜像

```bash
# 在项目根目录下执行
docker build -t nfsdig .
```

## 运行容器

### 基本运行（需要特权模式）
```bash
docker run --privileged --rm nfsdig
```

### 带参数运行
```bash
docker run --privileged --rm nfsdig [参数]
```

### 挂载BPF文件系统
```bash
docker run --privileged \
  --mount type=bind,source=/sys/fs/bpf,target=/sys/fs/bpf \
  --rm nfsdig
```

### 挂载主机文件系统（用于监控特定目录）
```bash
docker run --privileged \
  --mount type=bind,source=/sys/fs/bpf,target=/sys/fs/bpf \
  --mount type=bind,source=/path/to/monitor,target=/path/to/monitor \
  --rm nfsdig
```

### 后台运行
```bash
docker run --privileged -d --name nfsdig-container nfsdig
```

## 注意事项

1. **特权模式**: eBPF程序需要特权模式才能访问内核功能
2. **BPF文件系统**: 需要挂载 `/sys/fs/bpf` 目录
3. **内核版本**: 确保主机内核版本支持eBPF功能
4. **权限**: 容器需要足够的权限来加载和运行eBPF程序

## 故障排除

### 权限错误
如果遇到权限错误，确保使用 `--privileged` 标志：
```bash
docker run --privileged --rm nfsdig
```

### BPF加载失败
如果BPF程序加载失败，检查：
1. 内核版本是否支持eBPF
2. 是否正确挂载了BPF文件系统
3. 容器是否有足够权限

### 编译错误
如果构建时出现编译错误，确保：
1. 所有依赖包都已正确安装
2. CGO已启用
3. 目标架构设置正确

## 开发模式

### 调试运行
```bash
docker run --privileged -it --rm nfsdig /bin/bash
```

### 查看日志
```bash
docker logs nfsdig-container
``` 