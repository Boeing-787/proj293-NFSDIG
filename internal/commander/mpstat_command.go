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

// MpstatCommand 存储 CPU 统计信息
// 实现了 Command 接口
type MpstatCommand struct {
	Usage     float64 // CPU 使用率
	Timestamp string  // 时间戳
	CPU       string  // CPU 标识
	Usr       float64 // 用户态 CPU 使用率
	Nice      float64 // 低优先级进程 CPU 使用率
	Sys       float64 // 内核态 CPU 使用率
	Idle      float64 // 空闲率
}

// GetCommand 返回要执行的命令
func (c *MpstatCommand) GetCommand() string {
	return "mpstat -P ALL 1"
}

// Parse 解析命令输出
func (c *MpstatCommand) Parse(input string) error {
	var foundHeader bool
	var lastData []string

	scanner := bufio.NewScanner(strings.NewReader(input))
	lineNum := 0
	for scanner.Scan() {
		lineNum++
		line := scanner.Text()

		// 跳过空行
		if len(line) == 0 {
			continue
		}

		// 检查是否是表头行
		if strings.Contains(line, "%usr") {
			foundHeader = true
			continue
		}

		// 只有在找到表头后才开始处理数据
		if !foundHeader {
			continue
		}

		// 解析每一行数据
		fields := strings.Fields(line)

		// 检查是否是有效的 CPU 数据行
		if len(fields) < 11 {
			continue
		}

		// 检查是否是 'all' 行
		if fields[2] == "all" {
			lastData = fields
		}
	}

	// 使用最后一组数据
	if len(lastData) >= 13 {
		// 解析时间戳
		c.Timestamp = lastData[0] + " " + lastData[1]
		c.CPU = lastData[2]

		// 解析关键指标
		var err error
		c.Usr, err = strconv.ParseFloat(lastData[3], 64)
		if err != nil {
			return fmt.Errorf("解析 usr 值失败: %v", err)
		}
		c.Nice, err = strconv.ParseFloat(lastData[4], 64)
		if err != nil {
			return fmt.Errorf("解析 nice 值失败: %v", err)
		}
		c.Sys, err = strconv.ParseFloat(lastData[5], 64)
		if err != nil {
			return fmt.Errorf("解析 sys 值失败: %v", err)
		}
		c.Idle, err = strconv.ParseFloat(lastData[12], 64)
		if err != nil {
			return fmt.Errorf("解析 idle 值失败: %v", err)
		}
	}

	// fmt.Println("====MPSTAT====")
	// fmt.Printf("CPU: %s\n", c.CPU)
	// fmt.Printf("Usr: %.2f%%\n", c.Usr)
	// fmt.Printf("Sys: %.2f%%\n", c.Sys)
	// fmt.Printf("Idle: %.2f%%\n", c.Idle)
	// fmt.Println("==============")

	return nil
}

// Execute 执行命令并解析结果
func (c *MpstatCommand) Execute() (map[string]string, error) {
	// 创建命令
	cmd := exec.Command("mpstat", "-P", "ALL", "1")

	// 创建管道来捕获输出
	pr, pw := io.Pipe()
	cmd.Stdout = pw
	cmd.Stderr = pw

	// 启动命令
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("启动 mpstat 失败: %v", err)
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

	// 等待2秒后停止命令
	time.Sleep(2 * time.Second)

	// 停止命令
	if err := cmd.Process.Kill(); err != nil {
		return nil, fmt.Errorf("停止 mpstat 失败: %v", err)
	}

	// 关闭写入端
	pw.Close()

	// 等待命令结束
	cmd.Wait()

	// 获取收集到的输出
	output := <-outputChan
	// 解析 mpstat 输出
	if err := c.Parse(output); err != nil {
		return nil, fmt.Errorf("解析 mpstat 输出失败: %v", err)
	}

	// 计算 CPU 使用率
	c.Usage = 100 - c.Idle

	// 返回结果字典
	return map[string]string{
		"cpu_usage": fmt.Sprintf("%.2f", c.Usage),
		"cpu_usr":   fmt.Sprintf("%.2f", c.Usr),
		"cpu_nice":  fmt.Sprintf("%.2f", c.Nice),
		"cpu_sys":   fmt.Sprintf("%.2f", c.Sys),
		"cpu_idle":  fmt.Sprintf("%.2f", c.Idle),
	}, nil
}
