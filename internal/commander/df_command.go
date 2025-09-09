package commander

import (
	"bufio"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
)

// DFCommand 存储磁盘统计信息
// 实现了 Command 接口
type DFCommand struct {
	Filesystem string  // 文件系统
	Size       float64 // 总大小 (GB)
	Used       float64 // 已使用 (GB)
	Avail      float64 // 可用 (GB)
	UsePercent float64 // 使用率 (%)
	MountedOn  string  // 挂载点
}

// GetCommand 返回要执行的命令
func (c *DFCommand) GetCommand() string {
	return "df -h"
}

// Parse 解析命令输出
func (c *DFCommand) Parse(input string) error {
	scanner := bufio.NewScanner(strings.NewReader(input))
	var foundNFS bool

	for scanner.Scan() {
		line := scanner.Text()
		// 只处理包含 nfs 的行
		if !strings.Contains(line, "nfs") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) < 6 {
			continue
		}

		// 解析大小，将 GB 转换为 float64
		size, err := parseSize(fields[1])
		if err != nil {
			return fmt.Errorf("解析总大小失败: %v", err)
		}

		used, err := parseSize(fields[2])
		if err != nil {
			return fmt.Errorf("解析已用大小失败: %v", err)
		}

		avail, err := parseSize(fields[3])
		if err != nil {
			return fmt.Errorf("解析可用大小失败: %v", err)
		}

		// 解析使用率，去掉 % 符号
		usePercent, err := strconv.ParseFloat(strings.TrimSuffix(fields[4], "%"), 64)
		if err != nil {
			return fmt.Errorf("解析使用率失败: %v", err)
		}

		c.Filesystem = fields[0]
		c.Size = size
		c.Used = used
		c.Avail = avail
		c.UsePercent = usePercent
		c.MountedOn = fields[5]
		foundNFS = true
		break
	}

	if !foundNFS {
		return fmt.Errorf("未找到 NFS 文件系统")
	}

	// fmt.Println("====DF====")
	// fmt.Printf("Filesystem: %s\n", c.Filesystem)
	// fmt.Printf("Size: %.1fGB\n", c.Size)
	// fmt.Printf("Used: %.1fGB\n", c.Used)
	// fmt.Printf("Avail: %.1fGB\n", c.Avail)
	// fmt.Printf("Use%%: %.1f%%\n", c.UsePercent)
	// fmt.Printf("Mounted on: %s\n", c.MountedOn)
	// fmt.Println("==========")

	return nil
}

// Execute 执行命令并解析结果
func (c *DFCommand) Execute() (map[string]string, error) {
	// 执行 df -h 命令
	cmd := exec.Command("df", "-h")
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("执行 df 命令失败: %v", err)
	}

	// 解析 df 输出
	if err := c.Parse(string(output)); err != nil {
		return nil, fmt.Errorf("解析 df 输出失败: %v", err)
	}

	// 返回结果字典
	return map[string]string{
		"filesystem":  c.Filesystem,
		"size_gb":     fmt.Sprintf("%.1f", c.Size),
		"used_gb":     fmt.Sprintf("%.1f", c.Used),
		"avail_gb":    fmt.Sprintf("%.1f", c.Avail),
		"use_percent": fmt.Sprintf("%.1f", c.UsePercent),
		"mounted_on":  c.MountedOn,
	}, nil
}

// parseSize 解析带单位的大小字符串 (如 "188G", "9.3G")
func parseSize(sizeStr string) (float64, error) {
	// 去掉单位
	sizeStr = strings.TrimSuffix(sizeStr, "G")
	sizeStr = strings.TrimSuffix(sizeStr, "T")
	sizeStr = strings.TrimSuffix(sizeStr, "M")
	sizeStr = strings.TrimSuffix(sizeStr, "K")

	// 转换为 float64
	return strconv.ParseFloat(sizeStr, 64)
}
