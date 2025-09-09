#!/bin/bash

# 设置错误时退出
set -e

echo "=== Starting NFS Anomaly Detection Test ==="
echo "Time: $(date)"
echo ""

# 检查必要文件是否存在
if [ ! -f "./nfsdig" ]; then
    echo "Error: ./nfsdig not found"
    exit 1
fi

if [ ! -f "./benchmark/fio/simple_test.fio" ]; then
    echo "Error: ./benchmark/fio/simple_test.fio not found"
    exit 1
fi

if [ ! -f "anomaly_detection/scripts/nfs_op_polling_detector.py" ]; then
    echo "Error: anomaly_detection/scripts/nfs_op_polling_detector.py not found"
    exit 1
fi

# 创建输出目录
mkdir -p nfs_output/op_latency
mkdir -p traceOutput/op

# 函数：清理所有进程
cleanup() {
    echo ""
    echo "=== Stopping all processes ==="
    
    # 停止 FIO
    if [ ! -z "$FIO_PID" ] && kill -0 $FIO_PID 2>/dev/null; then
        echo "Stopping FIO (PID: $FIO_PID)..."
        kill $FIO_PID
    fi
    
    # 停止 nfsdig
    if [ ! -z "$NFSDIG_PID" ] && kill -0 $NFSDIG_PID 2>/dev/null; then
        echo "Stopping nfsdig (PID: $NFSDIG_PID)..."
        sudo kill $NFSDIG_PID
    fi
    echo "All processes stopped"
    exit 0
}

# 设置信号处理
trap cleanup INT TERM

echo "=== Step 1: Starting nfsdig in background ==="
# 启动 nfsdig 在后台运行，重定向输出到文件
sudo ./nfsdig -o > nfsdig.log 2>&1 &
NFSDIG_PID=$!
echo "nfsdig started with PID: $NFSDIG_PID (output redirected to nfsdig.log)"

# 等待一下让 nfsdig 完全启动
sleep 10

echo "=== Step 2: Starting FIO benchmark ==="
# 启动 FIO 在后台运行，添加运行时限制，重定向输出到文件
fio --runtime=60 ./benchmark/fio/simple_test.fio > fio.log 2>&1 &
FIO_PID=$!
echo "FIO started with PID: $FIO_PID (output redirected to fio.log)"

# 等待一下让 FIO 开始运行
sleep 3

echo "=== Step 3: Starting anomaly detection ==="
# 启动异常检测器（前台运行，输出显示在控制台）
echo "Anomaly detector will run in foreground and show output..."
echo "Press Ctrl+C to stop all processes"
echo ""

# 在前台运行异常检测器（这样输出会显示在控制台）
python3 anomaly_detection/nfs_op_polling_detector.py

echo "=== Test completed ==="
echo "Time: $(date)" 