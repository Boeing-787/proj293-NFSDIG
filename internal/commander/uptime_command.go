package commander

import (
	"fmt"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
)

// UptimeCommand 存储系统负载信息
// 实现了 Command 接口
type UptimeCommand struct {
	Load1  float64 // 1分钟负载
	Load5  float64 // 5分钟负载
	Load15 float64 // 15分钟负载
	Users  int     // 当前用户数
}

// GetCommand 返回要执行的命令
func (c *UptimeCommand) GetCommand() string {
	return "uptime"
}

// Parse 解析命令输出
func (c *UptimeCommand) Parse(input string) error {

	// 去除空白字符
	input = strings.TrimSpace(input)

	// 示例: " 22:27:58 up 26 days,  7:53, 10 users,  load average: 0.36, 0.19, 0.16"
	parts := strings.Fields(input)

	if len(parts) < 10 {
		return fmt.Errorf("uptime 输出格式不正确: %s", input)
	}

	// 解析用户数
	for i, part := range parts {
		if strings.Contains(part, "user") {
			if i > 0 && strings.ContainsAny(parts[i-1], "0123456789") {
				users, err := strconv.Atoi(parts[i-1])
				if err == nil {
					c.Users = users
					break
				}
			}
		}
	}

	// 如果上面的方法没有找到用户数，尝试另一种方式
	if c.Users == 0 {
		userRe := regexp.MustCompile(`(\d+) users`)
		matches := userRe.FindStringSubmatch(input)
		if len(matches) == 2 {
			users, err := strconv.Atoi(matches[1])
			if err == nil {
				c.Users = users
			}
		}
	}

	// 解析负载
	loadIdx := -1
	for i, part := range parts {
		if part == "average:" {
			loadIdx = i
			break
		}
	}

	if loadIdx != -1 && loadIdx+3 < len(parts) {
		load1Str := strings.TrimSuffix(parts[loadIdx+1], ",")
		load5Str := strings.TrimSuffix(parts[loadIdx+2], ",")
		load15Str := parts[loadIdx+3]

		var err error
		c.Load1, err = strconv.ParseFloat(load1Str, 64)
		if err != nil {
			return fmt.Errorf("解析 1分钟负载失败: %v", err)
		}
		c.Load5, err = strconv.ParseFloat(load5Str, 64)
		if err != nil {
			return fmt.Errorf("解析 5分钟负载失败: %v", err)
		}
		c.Load15, err = strconv.ParseFloat(load15Str, 64)
		if err != nil {
			return fmt.Errorf("解析 15分钟负载失败: %v", err)
		}
	}
	// fmt.Println("====Uptime====")
	// fmt.Printf("Load 1m: %.2f\n", c.Load1)
	// fmt.Printf("Load 5m: %.2f\n", c.Load5)
	// fmt.Printf("Load 15m: %.2f\n", c.Load15)
	// fmt.Printf("Users: %d\n", c.Users)
	// fmt.Println("==============")
	return nil
}

// Execute 执行命令并解析结果
func (c *UptimeCommand) Execute() (map[string]string, error) {
	// 执行 uptime 命令
	cmd := exec.Command("uptime")
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("执行 uptime 命令失败: %v", err)
	}

	// 解析 uptime 输出
	if err := c.Parse(string(output)); err != nil {
		return nil, fmt.Errorf("解析 uptime 输出失败: %v", err)
	}

	// 返回结果字典
	return map[string]string{
		"load_1m":  fmt.Sprintf("%.2f", c.Load1),
		"load_5m":  fmt.Sprintf("%.2f", c.Load5),
		"load_15m": fmt.Sprintf("%.2f", c.Load15),
		"users":    fmt.Sprintf("%d", c.Users),
	}, nil
}
