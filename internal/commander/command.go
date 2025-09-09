package commander

import (
	"context"
	"encoding/csv"
	"fmt"
	"os"
	"time"
)

// Command 定义了命令执行接口
type Command interface {
	// Execute 执行命令并返回结果
	Execute() (map[string]string, error)

	// Parse 解析命令输出
	Parse(output string) error

	// GetCommand 返回要执行的命令
	GetCommand() string
}

// CommandCategory 定义命令类别配置
type CommandCategory struct {
	Name       string        // 类别名称
	Commands   []string      // 该类别包含的命令
	Interval   time.Duration // 执行间隔
	OutputFile string        // 输出文件名
}

// CommandRegistry 存储命令名称到命令实现的映射
var CommandRegistry = map[string]func() Command{
	"mpstat":    func() Command { return &MpstatCommand{} },
	"uptime":    func() Command { return &UptimeCommand{} },
	"df":        func() Command { return &DFCommand{} },
	"nicstat":   func() Command { return &NicstatCommand{} },
	"free":      func() Command { return &FreeCommand{} },
	"nfsiostat": func() Command { return &NfsiostatCommand{} },
	"nfsstat":   func() Command { return &NfsstatCommand{} },
}

// CommandCategories 静态定义的命令分类配置
var CommandCategories = map[string]CommandCategory{
	"cpu": {
		Name:       "CPU",
		Commands:   []string{"mpstat", "uptime"},
		Interval:   1 * time.Second,
		OutputFile: "cpu_stats",
	},
	"memory": {
		Name:       "Memory",
		Commands:   []string{"free"},
		Interval:   1 * time.Second,
		OutputFile: "memory_stats",
	},
	"disk": {
		Name:       "Disk",
		Commands:   []string{"df"},
		Interval:   1 * time.Second,
		OutputFile: "disk_stats",
	},
	"network": {
		Name:       "Network",
		Commands:   []string{"nicstat"},
		Interval:   1 * time.Second,
		OutputFile: "network_stats",
	},
	"nfs": {
		Name:       "NFS",
		Commands:   []string{"nfsstat", "nfsiostat"},
		Interval:   1 * time.Second,
		OutputFile: "nfs_stats",
	},
}

// GetCommand 根据命令名称获取命令实例
func GetCommand(name string) (Command, error) {
	if factory, ok := CommandRegistry[name]; ok {
		return factory(), nil
	}
	return nil, fmt.Errorf("未知的命令: %s", name)
}

// GetCommandsByCategory 根据类别名称获取该类别的所有命令实例
func GetCommandsByCategory(categoryName string) ([]Command, error) {
	category, exists := CommandCategories[categoryName]
	if !exists {
		return nil, fmt.Errorf("未知的类别: %s", categoryName)
	}

	var commands []Command
	for _, cmdName := range category.Commands {
		cmd, err := GetCommand(cmdName)
		if err != nil {
			return nil, fmt.Errorf("获取命令 %s 失败: %v", cmdName, err)
		}
		commands = append(commands, cmd)
	}

	return commands, nil
}

// ShowStatsByCategoryWithContext 根据类别执行命令并收集数据（支持 context 取消）
func ShowStatsByCategoryWithContext(ctx context.Context, categoryName string, outputDir string) error {
	category, exists := CommandCategories[categoryName]
	if !exists {
		return fmt.Errorf("未知的类别: %s", categoryName)
	}

	// 获取该类别的所有命令
	commands, err := GetCommandsByCategory(categoryName)
	if err != nil {
		return fmt.Errorf("获取类别 %s 的命令失败: %v", categoryName, err)
	}

	// 生成带时间戳和CSV后缀的输出文件名
	// now := time.Now()
	// timestamp := now.Format("2006-01-02-15-04-05")

	// 创建类别子目录
	categoryDir := fmt.Sprintf("%s/%s", outputDir, categoryName)
	if err := os.MkdirAll(categoryDir, 0755); err != nil {
		return fmt.Errorf("创建类别目录失败: %v", err)
	}

	// 构建文件路径：./output/category_name/category_name_timestamp.csv
	// filename := fmt.Sprintf("%s_%s.csv", categoryName, timestamp)
	filename := fmt.Sprintf("%s.csv", categoryName)
	outputFile := fmt.Sprintf("%s/%s", categoryDir, filename)

	// 使用该类别的配置执行命令
	return ShowStatsWithContext(ctx, commands, category.Interval, outputFile)
}

// ShowStatsByCategory 根据类别执行命令并收集数据（保持向后兼容）
func ShowStatsByCategory(categoryName string, duration time.Duration, outputDir string) error {
	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()
	return ShowStatsByCategoryWithContext(ctx, categoryName, outputDir)
}

// ShowStatsWithContext 执行命令并收集数据（支持 context 取消）
func ShowStatsWithContext(ctx context.Context, commands []Command, interval time.Duration, outputFile string) error {
	// 创建输出文件
	file, err := os.Create(outputFile)
	if err != nil {
		return fmt.Errorf("创建输出文件失败: %v", err)
	}
	defer file.Close()
	// print commands
	// 创建 CSV writer
	writer := csv.NewWriter(file)
	defer writer.Flush()

	// 获取所有可能的表头
	headers := []string{"timestamp"}
	headerSet := make(map[string]bool)
	for _, cmd := range commands {
		result, _ := cmd.Execute()
		for k := range result {
			if !headerSet[k] {
				headers = append(headers, k)
				headerSet[k] = true
			}
		}
	}

	// 写入表头
	if err := writer.Write(headers); err != nil {
		return fmt.Errorf("写入表头失败: %v", err)
	}

	// 设置定时器
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	// 主循环
	for {
		select {
		case <-ctx.Done():
			// 收到取消信号或超时
			fmt.Printf("停止数据收集，文件已保存: %s\n", outputFile)
			return ctx.Err()

		case <-ticker.C:
			// 存储所有命令的结果
			allResults := make(map[string]string)
			allResults["timestamp"] = time.Now().Format("2006-01-02 15:04:05")

			// 执行每个命令并合并结果
			for _, cmd := range commands {
				result, err := cmd.Execute()
				if err != nil {
					fmt.Printf("执行命令失败: %v\n", err)
					continue
				}

				// 合并结果
				for k, v := range result {
					allResults[k] = v
				}
			}

			// 准备数据行
			var row []string
			for _, header := range headers {
				row = append(row, allResults[header])
			}

			// 写入数据
			if err := writer.Write(row); err != nil {
				fmt.Printf("写入数据失败: %v\n", err)
				continue
			}
			writer.Flush()
		}
	}
}

// ShowStats 执行命令并收集数据（保持向后兼容）
func ShowStats(commands []Command, interval time.Duration, duration time.Duration, outputFile string) error {
	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()
	return ShowStatsWithContext(ctx, commands, interval, outputFile)
}
