package commander

import (
	"bufio"
	"fmt"
	"io"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// NfsiostatCommand 存储 NFS I/O 统计信息
// 实现了 Command 接口
type NfsiostatCommand struct {
	// Read operation stats
	ReadOpsPerSec float64 // 读操作每秒次数
	ReadKBPerSec  float64 // 读操作每秒KB数
	ReadKBPerOp   float64 // 读操作每次KB数
	ReadRetrans   float64 // 读操作重传次数
	ReadAvgRTT    float64 // 读操作平均RTT(ms)
	ReadAvgExe    float64 // 读操作平均执行时间(ms)
	ReadAvgQueue  float64 // 读操作平均队列时间(ms)
	ReadErrors    float64 // 读操作错误次数

	// Write operation stats
	WriteOpsPerSec float64 // 写操作每秒次数
	WriteKBPerSec  float64 // 写操作每秒KB数
	WriteKBPerOp   float64 // 写操作每次KB数
	WriteRetrans   float64 // 写操作重传次数
	WriteAvgRTT    float64 // 写操作平均RTT(ms)
	WriteAvgExe    float64 // 写操作平均执行时间(ms)
	WriteAvgQueue  float64 // 写操作平均队列时间(ms)
	WriteErrors    float64 // 写操作错误次数
}

// GetCommand 返回要执行的命令
func (c *NfsiostatCommand) GetCommand() string {
	return "nfsiostat" // 运行1秒，输出1次
}

// Parse 解析 nfsiostat 命令输出，支持多个挂载点数据累加
func (c *NfsiostatCommand) Parse(input string) error {
	// 清零所有字段，避免累加上次的结果
	c.ReadOpsPerSec = 0
	c.ReadKBPerSec = 0
	c.ReadKBPerOp = 0
	c.ReadRetrans = 0
	c.ReadAvgRTT = 0
	c.ReadAvgExe = 0
	c.ReadAvgQueue = 0
	c.ReadErrors = 0
	c.WriteOpsPerSec = 0
	c.WriteKBPerSec = 0
	c.WriteKBPerOp = 0
	c.WriteRetrans = 0
	c.WriteAvgRTT = 0
	c.WriteAvgExe = 0
	c.WriteAvgQueue = 0
	c.WriteErrors = 0

	scanner := bufio.NewScanner(strings.NewReader(input))
	var currentOp string // "read" or "write"

	// 用于计算平均值的计数器
	readCount := 0
	writeCount := 0

	for scanner.Scan() {
		line := scanner.Text()
		fields := strings.Fields(line)

		if len(fields) == 0 {
			continue
		}

		// 检查是否是操作类型行
		if fields[0] == "read:" {
			currentOp = "read"
			continue
		} else if fields[0] == "write:" {
			currentOp = "write"
			continue
		}

		// 解析数据行 - nfsiostat 输出格式：
		// ops/s kB/s kB/op retrans (retrans%) avg_RTT avg_exe avg_queue errors (errors%)
		if currentOp != "" && len(fields) >= 10 {
			if currentOp == "read" {
				// 累加读操作数据
				opsPerSec, err := strconv.ParseFloat(fields[0], 64)
				if err != nil {
					return fmt.Errorf("解析读操作ops/s失败: %v", err)
				}
				c.ReadOpsPerSec += opsPerSec

				kbPerSec, err := strconv.ParseFloat(fields[1], 64)
				if err != nil {
					return fmt.Errorf("解析读操作kB/s失败: %v", err)
				}
				c.ReadKBPerSec += kbPerSec

				kbPerOp, err := strconv.ParseFloat(fields[2], 64)
				if err != nil {
					return fmt.Errorf("解析读操作kB/op失败: %v", err)
				}

				retrans, err := strconv.ParseFloat(fields[3], 64)
				if err != nil {
					return fmt.Errorf("解析读操作retrans失败: %v", err)
				}
				c.ReadRetrans += retrans

				// 跳过 fields[4] 因为它是 "(xx.x%)" 格式
				avgRTT, err := strconv.ParseFloat(fields[5], 64)
				if err != nil {
					return fmt.Errorf("解析读操作RTT失败: %v", err)
				}

				avgExe, err := strconv.ParseFloat(fields[6], 64)
				if err != nil {
					return fmt.Errorf("解析读操作执行时间失败: %v", err)
				}

				avgQueue, err := strconv.ParseFloat(fields[7], 64)
				if err != nil {
					return fmt.Errorf("解析读操作队列时间失败: %v", err)
				}

				errors, err := strconv.ParseFloat(fields[8], 64)
				if err != nil {
					return fmt.Errorf("解析读操作错误数失败: %v", err)
				}
				c.ReadErrors += errors

				// 对于时间相关指标，计算加权平均值
				if opsPerSec > 0 {
					c.ReadKBPerOp = (c.ReadKBPerOp*float64(readCount) + kbPerOp*opsPerSec) / (float64(readCount) + opsPerSec)
					c.ReadAvgRTT = (c.ReadAvgRTT*float64(readCount) + avgRTT*opsPerSec) / (float64(readCount) + opsPerSec)
					c.ReadAvgExe = (c.ReadAvgExe*float64(readCount) + avgExe*opsPerSec) / (float64(readCount) + opsPerSec)
					c.ReadAvgQueue = (c.ReadAvgQueue*float64(readCount) + avgQueue*opsPerSec) / (float64(readCount) + opsPerSec)
					readCount++
				}

			} else if currentOp == "write" {
				// 累加写操作数据
				opsPerSec, err := strconv.ParseFloat(fields[0], 64)
				if err != nil {
					return fmt.Errorf("解析写操作ops/s失败: %v", err)
				}
				c.WriteOpsPerSec += opsPerSec

				kbPerSec, err := strconv.ParseFloat(fields[1], 64)
				if err != nil {
					return fmt.Errorf("解析写操作kB/s失败: %v", err)
				}
				c.WriteKBPerSec += kbPerSec

				kbPerOp, err := strconv.ParseFloat(fields[2], 64)
				if err != nil {
					return fmt.Errorf("解析写操作kB/op失败: %v", err)
				}

				retrans, err := strconv.ParseFloat(fields[3], 64)
				if err != nil {
					return fmt.Errorf("解析写操作retrans失败: %v", err)
				}
				c.WriteRetrans += retrans

				// 跳过 fields[4] 因为它是 "(xx.x%)" 格式
				avgRTT, err := strconv.ParseFloat(fields[5], 64)
				if err != nil {
					return fmt.Errorf("解析写操作RTT失败: %v", err)
				}

				avgExe, err := strconv.ParseFloat(fields[6], 64)
				if err != nil {
					return fmt.Errorf("解析写操作执行时间失败: %v", err)
				}

				avgQueue, err := strconv.ParseFloat(fields[7], 64)
				if err != nil {
					return fmt.Errorf("解析写操作队列时间失败: %v", err)
				}

				errors, err := strconv.ParseFloat(fields[8], 64)
				if err != nil {
					return fmt.Errorf("解析写操作错误数失败: %v", err)
				}
				c.WriteErrors += errors

				// 对于时间相关指标，计算加权平均值
				if opsPerSec > 0 {
					c.WriteKBPerOp = (c.WriteKBPerOp*float64(writeCount) + kbPerOp*opsPerSec) / (float64(writeCount) + opsPerSec)
					c.WriteAvgRTT = (c.WriteAvgRTT*float64(writeCount) + avgRTT*opsPerSec) / (float64(writeCount) + opsPerSec)
					c.WriteAvgExe = (c.WriteAvgExe*float64(writeCount) + avgExe*opsPerSec) / (float64(writeCount) + opsPerSec)
					c.WriteAvgQueue = (c.WriteAvgQueue*float64(writeCount) + avgQueue*opsPerSec) / (float64(writeCount) + opsPerSec)
					writeCount++
				}
			}
			currentOp = "" // 重置操作类型
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("读取输入错误: %v", err)
	}

	// fmt.Println("====NFSIOSTAT====")
	// fmt.Printf("Read: %.2f ops/s, %.2f kB/s, %.2f kB/op, %.0f retrans\n",
	// 	c.ReadOpsPerSec, c.ReadKBPerSec, c.ReadKBPerOp, c.ReadRetrans)
	// fmt.Printf("Read Timing: RTT=%.2fms, Exe=%.2fms, Queue=%.2fms, Errors=%.0f\n",
	// 	c.ReadAvgRTT, c.ReadAvgExe, c.ReadAvgQueue, c.ReadErrors)
	// fmt.Printf("Write: %.2f ops/s, %.2f kB/s, %.2f kB/op, %.0f retrans\n",
	// 	c.WriteOpsPerSec, c.WriteKBPerSec, c.WriteKBPerOp, c.WriteRetrans)
	// fmt.Printf("Write Timing: RTT=%.2fms, Exe=%.2fms, Queue=%.2fms, Errors=%.0f\n",
	// 	c.WriteAvgRTT, c.WriteAvgExe, c.WriteAvgQueue, c.WriteErrors)
	// fmt.Println("=================")

	return nil
}

// Execute 执行命令并解析结果，获取1秒间隔的真实增量数据
func (c *NfsiostatCommand) Execute() (map[string]string, error) {
	// 创建命令
	cmd := exec.Command("/usr/sbin/nfsiostat", "1")

	// 创建管道来捕获输出
	pr, pw := io.Pipe()
	cmd.Stdout = pw
	cmd.Stderr = pw

	// 启动命令
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("启动 nfsiostat 失败: %v", err)
	}

	// 创建一个通道来存储输出
	outputChan := make(chan string)
	go func() {
		scanner := bufio.NewScanner(pr)
		var output strings.Builder
		for scanner.Scan() {
			output.WriteString(scanner.Text() + "\n")
		}
		outputChan <- output.String()
	}()

	// 等待3秒后停止命令（需要足够时间获取两次输出）
	time.Sleep(3 * time.Second)

	// 停止命令
	if err := cmd.Process.Kill(); err != nil {
		return nil, fmt.Errorf("停止 nfsiostat 失败: %v", err)
	}

	// 关闭写入端
	pw.Close()

	// 等待命令结束
	cmd.Wait()

	// 获取收集到的输出
	outputStr := <-outputChan

	// 找到所有挂载点的位置
	lines := strings.Split(outputStr, "\n")
	mountPoints := []int{}

	for i, line := range lines {
		if strings.Contains(line, "mounted on") {
			mountPoints = append(mountPoints, i)
		}
	}

	var secondOutput string
	if len(mountPoints) >= 2 {
		// 如果有多个挂载点，从第二轮开始取（通常是第3个挂载点开始）
		// 因为第一轮是累计数据，第二轮才是增量数据
		halfPoint := len(mountPoints) / 2
		if halfPoint > 0 {
			startLine := mountPoints[halfPoint]
			secondOutput = strings.Join(lines[startLine:], "\n")
		}
	}

	// 如果没有找到第二次输出，使用完整输出
	if secondOutput == "" {
		secondOutput = outputStr
	}

	// 解析第二次的 nfsiostat 输出（增量数据）
	if err := c.Parse(secondOutput); err != nil {
		return nil, fmt.Errorf("解析 nfsiostat 输出失败: %v", err)
	}

	// 返回结果字典
	return map[string]string{
		"read_ops_per_sec":  fmt.Sprintf("%.2f", c.ReadOpsPerSec),
		"read_kb_per_sec":   fmt.Sprintf("%.2f", c.ReadKBPerSec),
		"read_kb_per_op":    fmt.Sprintf("%.2f", c.ReadKBPerOp),
		"read_retrans":      fmt.Sprintf("%.0f", c.ReadRetrans),
		"read_avg_rtt":      fmt.Sprintf("%.2f", c.ReadAvgRTT),
		"read_avg_exe":      fmt.Sprintf("%.2f", c.ReadAvgExe),
		"read_avg_queue":    fmt.Sprintf("%.2f", c.ReadAvgQueue),
		"read_errors":       fmt.Sprintf("%.0f", c.ReadErrors),
		"write_ops_per_sec": fmt.Sprintf("%.2f", c.WriteOpsPerSec),
		"write_kb_per_sec":  fmt.Sprintf("%.2f", c.WriteKBPerSec),
		"write_kb_per_op":   fmt.Sprintf("%.2f", c.WriteKBPerOp),
		"write_retrans":     fmt.Sprintf("%.0f", c.WriteRetrans),
		"write_avg_rtt":     fmt.Sprintf("%.2f", c.WriteAvgRTT),
		"write_avg_exe":     fmt.Sprintf("%.2f", c.WriteAvgExe),
		"write_avg_queue":   fmt.Sprintf("%.2f", c.WriteAvgQueue),
		"write_errors":      fmt.Sprintf("%.0f", c.WriteErrors),
	}, nil
}
