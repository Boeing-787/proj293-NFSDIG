package commander

import (
	"bufio"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
)

// NicstatCommand 存储网络接口统计信息
// 实现了 Command 接口
type NicstatCommand struct {
	Timestamp string  // 时间戳
	Interface string  // 接口名称
	ReadKB    float64 // 每秒读取的KB数
	WriteKB   float64 // 每秒写入的KB数
	ReadPk    float64 // 每秒读取的数据包数
	WritePk   float64 // 每秒写入的数据包数
	ReadAvg   float64 // 读取数据包的平均大小
	WriteAvg  float64 // 写入数据包的平均大小
	Util      float64 // 接口使用率
	Sat       float64 // 接口饱和度
}

// GetCommand 返回要执行的命令
func (c *NicstatCommand) GetCommand() string {
	// nicstat by default runs for 1 second and outputs 2 lines (header + data)
	return "nicstat -i lo"
}

// Parse 解析 nicstat -i lo 命令输出
func (c *NicstatCommand) Parse(input string) error {
	scanner := bufio.NewScanner(strings.NewReader(input))
	var foundHeader bool
	var dataLineProcessed bool

	for scanner.Scan() {
		line := scanner.Text()
		fields := strings.Fields(line)

		// 跳过空行
		if len(fields) == 0 {
			continue
		}

		// 查找表头行
		if !foundHeader {
			if len(fields) >= 10 && fields[0] == "Time" && fields[1] == "Int" {
				foundHeader = true
			}
			continue
		}

		// 表头已找到，处理下一行（数据行）
		if !dataLineProcessed && len(fields) >= 10 {
			c.Timestamp = fields[0]
			c.Interface = fields[1]
			var err error
			c.ReadKB, err = strconv.ParseFloat(fields[2], 64)
			if err != nil {
				return fmt.Errorf("解析 ReadKB 失败: %v", err)
			}
			c.WriteKB, err = strconv.ParseFloat(fields[3], 64)
			if err != nil {
				return fmt.Errorf("解析 WriteKB 失败: %v", err)
			}
			c.ReadPk, err = strconv.ParseFloat(fields[4], 64)
			if err != nil {
				return fmt.Errorf("解析 ReadPk 失败: %v", err)
			}
			c.WritePk, err = strconv.ParseFloat(fields[5], 64)
			if err != nil {
				return fmt.Errorf("解析 WritePk 失败: %v", err)
			}
			c.ReadAvg, err = strconv.ParseFloat(fields[6], 64)
			if err != nil {
				return fmt.Errorf("解析 ReadAvg 失败: %v", err)
			}
			c.WriteAvg, err = strconv.ParseFloat(fields[7], 64)
			if err != nil {
				return fmt.Errorf("解析 WriteAvg 失败: %v", err)
			}
			c.Util, err = strconv.ParseFloat(fields[8], 64)
			if err != nil {
				return fmt.Errorf("解析 Util 失败: %v", err)
			}
			c.Sat, err = strconv.ParseFloat(fields[9], 64)
			if err != nil {
				return fmt.Errorf("解析 Sat 失败: %v", err)
			}
			dataLineProcessed = true // 标记数据行已处理
			break                    // 只需要第一行数据
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("读取输入错误: %v", err)
	}

	if !dataLineProcessed {
		return fmt.Errorf("未找到或解析 nicstat 数据行")
	}

	// fmt.Println("====NICSTAT====")
	// fmt.Printf("Interface: %s\n", c.Interface)
	// fmt.Printf("Read: %.2f KB/s (%.0f Pk/s, Avg: %.0f B/Pk)\n", c.ReadKB, c.ReadPk, c.ReadAvg)
	// fmt.Printf("Write: %.2f KB/s (%.0f Pk/s, Avg: %.0f B/Pk)\n", c.WriteKB, c.WritePk, c.WriteAvg)
	// fmt.Printf("Util: %.2f%%\n", c.Util)
	// fmt.Printf("Sat: %.2f%%\n", c.Sat)
	// fmt.Println("===============")

	return nil
}

// Execute 执行命令并解析结果
func (c *NicstatCommand) Execute() (map[string]string, error) {
	// 执行 nicstat -i lo 命令
	// nicstat 默认运行1秒，输出包含表头和数据行
	cmd := exec.Command("nicstat", "-i", "lo", "1", "1") // Run for 1 interval, 1 time
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("执行 nicstat 命令失败: %v", err)
	}

	// 解析 nicstat 输出
	if err := c.Parse(string(output)); err != nil {
		return nil, fmt.Errorf("解析 nicstat 输出失败: %v", err)
	}

	// 返回结果字典
	return map[string]string{
		"iface_read_kb":  fmt.Sprintf("%.2f", c.ReadKB),
		"iface_write_kb": fmt.Sprintf("%.2f", c.WriteKB),
		"iface_read_pk":  fmt.Sprintf("%.2f", c.ReadPk),
		"iface_write_pk": fmt.Sprintf("%.2f", c.WritePk),
		"iface_util":     fmt.Sprintf("%.2f", c.Util),
	}, nil
}
