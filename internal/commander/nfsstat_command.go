package commander

import (
	"bufio"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// NfsstatCommand 存储 NFS 客户端统计信息
// 实现了 Command 接口
type NfsstatCommand struct {
	Headers []string           // 统计项名称
	Values  map[string]float64 // 统计值
}

// GetCommand 返回要执行的命令
func (c *NfsstatCommand) GetCommand() string {
	return "nfsstat -c"
}

// Parse 解析 nfsstat -c 命令输出
func (c *NfsstatCommand) Parse(input string) error {
	scanner := bufio.NewScanner(strings.NewReader(input))
	c.Values = make(map[string]float64)

	var currentHeaders []string
	var currentValues []string

	for scanner.Scan() {
		line := scanner.Text()

		// 跳过空行和客户端标识行
		if strings.TrimSpace(line) == "" || strings.HasPrefix(line, "Client") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) == 0 {
			continue
		}

		// 判断是否是表头行（包含非数字字段）
		isHeader := true
		for _, field := range fields {
			// 尝试解析为数字，如果成功则不是表头
			if _, err := strconv.ParseFloat(strings.TrimRight(field, "%"), 64); err == nil {
				isHeader = false
				break
			}
		}

		if isHeader {
			// 表头行
			currentHeaders = append(currentHeaders, fields...)
		} else {
			// 数据行 - 过滤掉百分比字段
			for _, field := range fields {
				if !strings.Contains(field, "%") {
					currentValues = append(currentValues, field)
				}
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("读取输入错误: %v", err)
	}

	// 确保表头和数值数量匹配
	if len(currentHeaders) != len(currentValues) {
		return fmt.Errorf("表头和数值数量不匹配: headers=%d, values=%d",
			len(currentHeaders), len(currentValues))
	}

	// 存储表头
	c.Headers = currentHeaders

	// 解析并存储数值
	for i, header := range currentHeaders {
		if i < len(currentValues) {
			value, err := strconv.ParseFloat(currentValues[i], 64)
			if err != nil {
				return fmt.Errorf("解析数值 %s 失败: %v", currentValues[i], err)
			}
			c.Values[header] = value
		}
	}

	// 输出部分关键统计信息
	// fmt.Println("====NFSSTAT====")

	// // 显示一些关键的NFS操作统计
	// keyStats := []string{"null", "getattr", "setattr", "lookup", "access", "readlink",
	// 	"read", "write", "create", "mkdir", "remove", "rmdir"}

	// for _, stat := range keyStats {
	// 	if value, exists := c.Values[stat]; exists {
	// 		fmt.Printf("%s: %.0f\n", stat, value)
	// 	}
	// }
	// fmt.Println("===============")

	return nil
}

// Execute 执行命令并解析结果，间隔1秒运行两次并返回差值
func (c *NfsstatCommand) Execute() (map[string]string, error) {
	// 第一次采集
	first := &NfsstatCommand{}
	cmd1 := exec.Command("nfsstat", "-c")
	output1, err := cmd1.Output()
	if err != nil {
		return nil, fmt.Errorf("执行第一次 nfsstat 命令失败: %v", err)
	}
	if err := first.Parse(string(output1)); err != nil {
		return nil, fmt.Errorf("解析第一次 nfsstat 输出失败: %v", err)
	}

	// 等待1秒
	time.Sleep(1 * time.Second)

	// 第二次采集
	second := &NfsstatCommand{}
	cmd2 := exec.Command("nfsstat", "-c")
	output2, err := cmd2.Output()
	if err != nil {
		return nil, fmt.Errorf("执行第二次 nfsstat 命令失败: %v", err)
	}
	if err := second.Parse(string(output2)); err != nil {
		return nil, fmt.Errorf("解析第二次 nfsstat 输出失败: %v", err)
	}

	// 计算差值并返回结果字典
	result := make(map[string]string)
	for header, value2 := range second.Values {
		if value1, exists := first.Values[header]; exists {
			diff := value2 - value1
			// 使用 nfs_ 前缀避免字段名冲突
			result["nfs_"+header] = fmt.Sprintf("%.0f", diff)
		}
	}

	return result, nil
}
