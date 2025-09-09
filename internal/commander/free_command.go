package commander

import (
	"bufio"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
)

// FreeCommand 存储内存统计信息
// 实现了 Command 接口
type FreeCommand struct {
	Timestamp string // 时间戳
	Total     int64  // 总内存 (MB)
	Used      int64  // 已使用内存 (MB)
	Free      int64  // 空闲内存 (MB)
	Shared    int64  // 共享内存 (MB)
	BuffCache int64  // 缓冲/缓存内存 (MB)
	Available int64  // 可用内存 (MB)
	SwapTotal int64  // 总交换空间 (MB)
	SwapUsed  int64  // 已使用交换空间 (MB)
	SwapFree  int64  // 空闲交换空间 (MB)
}

// GetCommand 返回要执行的命令
func (c *FreeCommand) GetCommand() string {
	return "free -m"
}

// Parse 解析 free -m 命令输出
func (c *FreeCommand) Parse(input string) error {
	scanner := bufio.NewScanner(strings.NewReader(input))
	var foundMem bool
	var foundSwap bool

	for scanner.Scan() {
		line := scanner.Text()
		fields := strings.Fields(line)

		// 跳过空行
		if len(fields) == 0 {
			continue
		}

		// 解析 Mem 行
		if fields[0] == "Mem:" {
			foundMem = true
			if len(fields) < 7 {
				return fmt.Errorf("invalid Mem line format")
			}
			var err error
			c.Total, err = strconv.ParseInt(fields[1], 10, 64)
			if err != nil {
				return fmt.Errorf("解析总内存失败: %v", err)
			}
			c.Used, err = strconv.ParseInt(fields[2], 10, 64)
			if err != nil {
				return fmt.Errorf("解析已用内存失败: %v", err)
			}
			c.Free, err = strconv.ParseInt(fields[3], 10, 64)
			if err != nil {
				return fmt.Errorf("解析空闲内存失败: %v", err)
			}
			c.Shared, err = strconv.ParseInt(fields[4], 10, 64)
			if err != nil {
				return fmt.Errorf("解析共享内存失败: %v", err)
			}
			c.BuffCache, err = strconv.ParseInt(fields[5], 10, 64)
			if err != nil {
				return fmt.Errorf("解析缓冲内存失败: %v", err)
			}
			c.Available, err = strconv.ParseInt(fields[6], 10, 64)
			if err != nil {
				return fmt.Errorf("解析可用内存失败: %v", err)
			}
		}

		// 解析 Swap 行
		if fields[0] == "Swap:" {
			foundSwap = true
			if len(fields) < 4 {
				return fmt.Errorf("invalid Swap line format")
			}
			var err error
			c.SwapTotal, err = strconv.ParseInt(fields[1], 10, 64)
			if err != nil {
				return fmt.Errorf("解析交换空间总量失败: %v", err)
			}
			c.SwapUsed, err = strconv.ParseInt(fields[2], 10, 64)
			if err != nil {
				return fmt.Errorf("解析交换空间使用量失败: %v", err)
			}
			c.SwapFree, err = strconv.ParseInt(fields[3], 10, 64)
			if err != nil {
				return fmt.Errorf("解析交换空间空闲量失败: %v", err)
			}
		}
	}

	if !foundMem || !foundSwap {
		return fmt.Errorf("missing required memory information")
	}

	// 计算使用率
	// memUsagePercent := float64(c.Used) / float64(c.Total) * 100
	// swapUsagePercent := float64(0)
	// if c.SwapTotal > 0 {
	// 	swapUsagePercent = float64(c.SwapUsed) / float64(c.SwapTotal) * 100
	// }

	// fmt.Println("====FREE====")
	// fmt.Printf("Memory Total: %dMB\n", c.Total)
	// fmt.Printf("Memory Used: %dMB (%.2f%%)\n", c.Used, memUsagePercent)
	// fmt.Printf("Memory Available: %dMB\n", c.Available)
	// fmt.Printf("Swap Total: %dMB\n", c.SwapTotal)
	// fmt.Printf("Swap Used: %dMB (%.2f%%)\n", c.SwapUsed, swapUsagePercent)
	// fmt.Println("============")

	return nil
}

// Execute 执行命令并解析结果
func (c *FreeCommand) Execute() (map[string]string, error) {
	// 执行 free -m 命令
	cmd := exec.Command("free", "-m")
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("执行 free 命令失败: %v", err)
	}

	// 解析 free 输出
	if err := c.Parse(string(output)); err != nil {
		return nil, fmt.Errorf("解析 free 输出失败: %v", err)
	}

	// 计算使用率
	memUsagePercent := float64(c.Used) / float64(c.Total) * 100
	swapUsagePercent := float64(0)
	if c.SwapTotal > 0 {
		swapUsagePercent = float64(c.SwapUsed) / float64(c.SwapTotal) * 100
	}

	// 返回结果字典
	return map[string]string{
		"mem_total":      strconv.FormatInt(c.Total, 10),
		"mem_used":       strconv.FormatInt(c.Used, 10),
		"mem_free":       strconv.FormatInt(c.Free, 10),
		"mem_available":  strconv.FormatInt(c.Available, 10),
		"mem_usage_pct":  fmt.Sprintf("%.2f", memUsagePercent),
		"swap_total":     strconv.FormatInt(c.SwapTotal, 10),
		"swap_used":      strconv.FormatInt(c.SwapUsed, 10),
		"swap_free":      strconv.FormatInt(c.SwapFree, 10),
		"swap_usage_pct": fmt.Sprintf("%.2f", swapUsagePercent),
	}, nil
}
