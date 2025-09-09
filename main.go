package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"nfsdig/internal/commander"
	"nfsdig/internal/nfsdig"
	"net"
	"os"
	"os/signal"
	"os/exec"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	"github.com/cilium/ebpf/rlimit"
	"golang.org/x/sys/unix"
)

// RTT统计相关的定义
const MAX_SLOTS = 27

type Hist struct {
	Latency uint64
	Cnt     uint64
	Slots   [MAX_SLOTS]uint32
}

func main() {
	//命令行工具解析

	flags := nfsdig.Flags{}
	flags.SetFlags()
	flags.Parse()
	if flags.ShowHelp {
		flags.PrintHelp()
		os.Exit(0)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	bpfSpec, err := LoadNfsTrace()
	if err != nil {
		log.Fatalf("Failed to load bpf spec: %v", err)
	}

	// 控制跟踪的nfs操作
	var Funcs []string = nfsdig.NfsOpFuncs
	if flags.TRACEOPERATIONS {
		fmt.Println("--------OP_TRACK ON---------")
		fmt.Println("OP_THACK:Will trace the following nfs operations:")
		for _, fnname := range Funcs {
			fmt.Print(fnname)
			fmt.Print(",")
		}
		fmt.Print("\n")
	} else {
		var opTraceMaps = []string{
			"starts",
			"op_events",
		}
		var opTraceProgs []string
		for _, fn := range nfsdig.NfsOpFuncs {
			snake := toSnake(fn)
			opTraceProgs = append(opTraceProgs, "trace_entry_"+snake)
			opTraceProgs = append(opTraceProgs, "trace_exit_"+snake)
		}
		// 删除 programs
		for _, name := range opTraceProgs {
			if prog := bpfSpec.Programs[name]; prog != nil {
				delete(bpfSpec.Programs, name)
				//fmt.Printf("Removed program: %s\n", name)
			}
		}
		// 删除 maps
		for _, name := range opTraceMaps {
			if m := bpfSpec.Maps[name]; m != nil {
				delete(bpfSpec.Maps, name)
				//fmt.Printf("Removed map: %s\n", name)
			}
		}
	}

	// 处理 NFSD 相关的 maps 和 programs
	if !flags.TRACKNFSD {
		var nfsdTraceMaps = []string{
			"nfsd_compound_starts",
			"nfsd_op_events", 
			"nfsd_op_starts",
		}
		var nfsdTraceProgs []string
		// 使用 nfs_type.go 中定义的 NfsdFuncs
		nfsdFuncs := nfsdig.NfsdFuncs
		
		for _, fn := range nfsdFuncs {
			nfsdTraceProgs = append(nfsdTraceProgs, "trace_entry_"+fn)
			nfsdTraceProgs = append(nfsdTraceProgs, "trace_exit_"+fn)
		}
		
		// 删除 nfsd programs
		for _, name := range nfsdTraceProgs {
			if prog := bpfSpec.Programs[name]; prog != nil {
				delete(bpfSpec.Programs, name)
			}
		}
		// 删除 nfsd maps
		for _, name := range nfsdTraceMaps {
			if m := bpfSpec.Maps[name]; m != nil {
				delete(bpfSpec.Maps, name)
			}
		}
	}

	//nfsdig提升文件描述符限制，便于插入多个ebpf程序
	if err := unix.Setrlimit(unix.RLIMIT_NOFILE, &unix.Rlimit{
		Cur: 8192,
		Max: 8192,
	}); err != nil {
		log.Fatalf("failed to set temporary rlimit: %s", err)
	}
	//提升ebpf程序内核大小限制
	if err := rlimit.RemoveMemlock(); err != nil {
		log.Fatalf("Failed to set temporary rlimit: %s", err)
	}

	// 将宏变量配置写入到 bpf 程序中
	fmt.Println("----------Filter PID---------")
	if flags.FilterPid != 0 {
		fmt.Println("filter pid:", flags.FilterPid)
		pid := flags.FilterPid
		if err := bpfSpec.Variables["filter_pid"].Set(pid); err != nil {
			log.Fatalf("setting variable: %s", err)
		}
	} else {
		fmt.Println("No specific pid, the program will attach to all processes.")
	}

	//加载ebpf程序
	coll, err := ebpf.NewCollection(bpfSpec)
	if err != nil { // 捕获并处理可能的验证器错误（Verifier Error）
		var (
			ve          *ebpf.VerifierError
			verifierLog string
		)
		if errors.As(err, &ve) {
			verifierLog = fmt.Sprintf("Verifier error: %+v\n", ve)
		}

		log.Fatalf("Failed to load objects: %s\n%+v", verifierLog, err)
	}
	defer coll.Close()

	//附加TrackFILE跟踪点
	if flags.TRACKRPC {
		var trackiopslinks []link.Link
		for _, traceprog := range nfsdig.TrackIopsProgs {
			if traceprog.Type == "kprobe" {
				fnname := traceprog.Details.(nfsdig.KprobeProg).Symbol
				//fmt.Println(fnname)
				prog := coll.Programs[fnname]
				if prog == nil {
					log.Fatalf("Failed to find program %s", fnname)
				}
				link, err := link.Kprobe(fnname, prog, nil)
				if err != nil {
					log.Fatalf("Failed to attach kprobe: %s", err)
				}
				trackiopslinks = append(trackiopslinks, link)
			} else if traceprog.Type == "tracepoint" {
				fnname := traceprog.Details.(nfsdig.TracepointProg).Event
				subsystem := traceprog.Details.(nfsdig.TracepointProg).Subsystem
				prog := coll.Programs[fnname]
				if prog == nil {
					log.Fatalf("Failed to find program %s", fnname)
				}
				link, err := link.Tracepoint(subsystem, fnname, prog, nil)
				if err != nil {
					log.Fatalf("Failed to attach tracepoint %s: %v", fnname, err)
				}
				trackiopslinks = append(trackiopslinks, link)
			}
		}
		defer func() {
			for _, link := range trackiopslinks {
				if err := link.Close(); err != nil {
					log.Printf("Failed to close link: %s", err)
				}
			}
		}()
	}

	if flags.TRACKFILE {
		var trackiopslinks []link.Link
		fnnames := []string{"nfs_file_read", "nfs_file_write", "nfs_file_splice_read", "iter_file_splice_write"} //
		for _, fnname := range fnnames {
			entryField := "trace_entry_" + fnname
			exitField := "trace_exit_" + fnname
			entryProg := coll.Programs[entryField]
			exitProg := coll.Programs[exitField]
			kpEntry, err := link.Kprobe(fnname, entryProg, nil)
			if err != nil {
				log.Fatalf("Failed to attach entry for nfs_%s: %v", fnname, err)
			}
			trackiopslinks = append(trackiopslinks, kpEntry)
			kpExit, err := link.Kretprobe(fnname, exitProg, nil)
			if err != nil {
				log.Fatalf("Failed to attach exit for nfs_%s: %v", fnname, err)
			}
			trackiopslinks = append(trackiopslinks, kpExit)

		}
		defer func() {
			for _, link := range trackiopslinks {
				if err := link.Close(); err != nil {
					log.Printf("Failed to close link: %s", err)
				}
			}
		}()
	}

	//附加 OP函数点
	if flags.TRACEOPERATIONS {
		var opLinks []link.Link
		for _, opname := range Funcs {
			entryField := "TraceEntry_" + opname
			exitField := "TraceExit_" + opname
			entryProg := coll.Programs[toSnake(entryField)]
			exitProg := coll.Programs[toSnake(exitField)]

			kpEntry, err := link.Kprobe(toSnake(opname), entryProg, nil)
			if err != nil {
				log.Fatalf("Failed to attach entry for %s: %v", toSnake(opname), err)
			}
			opLinks = append(opLinks, kpEntry)
			kpExit, err := link.Kretprobe(toSnake(opname), exitProg, nil)
			if err != nil {
				log.Fatalf("Failed to attach exit for %s: %v", toSnake(opname), err)
			}
			opLinks = append(opLinks, kpExit)
		}

		defer func() {
			for _, l := range opLinks {
				l.Close()
			}
		}()
	}

	// 附加 NFSD 函数点
	if flags.TRACKNFSD {
		fmt.Println("--------NFSD_TRACK ON---------")
		fmt.Println("NFSD_TRACK: Will trace the following nfsd operations:")
		
		var nfsdLinks []link.Link
		// 使用 nfs_type.go 中定义的 NfsdFuncs
		nfsdFuncs := nfsdig.NfsdFuncs

		// 不同内核版本的符号名差异处理
		attachSymbolOverrides := map[string]string{
			"nfsd4_compound":      "nfsd4_proc_compound",
			"nfsd4_null":          "nfsd4_proc_null",
			"nfsd4_illegal":       "", // 某些内核无该符号，直接跳过
		}
		
		for _, fnname := range nfsdFuncs {
			fmt.Printf("%s,", fnname)
			
			entryField := "trace_entry_" + fnname
			exitField := "trace_exit_" + fnname
			entryProg := coll.Programs[entryField]
			exitProg := coll.Programs[exitField]
			
			if entryProg == nil || exitProg == nil {
				fmt.Printf("\nWarning: Program %s or %s not found, skipping...\n", entryField, exitField)
				continue
			}
			// 处理符号名差异
			attachSym := fnname
			if alt, ok := attachSymbolOverrides[fnname]; ok {
				if alt == "" {
					log.Printf("Skipping %s: symbol not available on this kernel", fnname)
					continue
				}
				attachSym = alt
			}

			kpEntry, err := link.Kprobe(attachSym, entryProg, nil)
			if err != nil {
				log.Printf("Failed to attach entry for %s (symbol %s): %v", fnname, attachSym, err)
				continue
			}
			nfsdLinks = append(nfsdLinks, kpEntry)

			kpExit, err := link.Kretprobe(attachSym, exitProg, nil)
			if err != nil {
				log.Printf("Failed to attach exit for %s (symbol %s): %v", fnname, attachSym, err)
				continue
			}
			nfsdLinks = append(nfsdLinks, kpExit)
		}
		fmt.Print("\n")
		
		defer func() {
			for _, l := range nfsdLinks {
				l.Close()
			}
		}()
	}

    // 如果启用XDP功能，加载XDP程序
    var xdpLink link.Link
    var xdpColl *ebpf.Collection
	if flags.TRACKXDP {
		fmt.Println("--------XDP_TRACK ON---------")
		fmt.Println("XDP_TRACK: Will track NFS packets using XDP")
		
		// 加载XDP程序
		xdpSpec, err := LoadXdpProgram()
		if err != nil {
			log.Fatalf("Failed to load XDP program: %v", err)
		}
		
		// 配置XDP过滤参数
		if err := xdpSpec.Variables["filter_src_ip"].Set(flags.GetFilterSrcIP()); err != nil {
			log.Printf("Warning: Failed to set filter_src_ip: %v", err)
		}
		if err := xdpSpec.Variables["filter_dst_ip"].Set(flags.GetFilterDstIP()); err != nil {
			log.Printf("Warning: Failed to set filter_dst_ip: %v", err)
		}
		if err := xdpSpec.Variables["filter_src_port"].Set(flags.FilterSrcPort); err != nil {
			log.Printf("Warning: Failed to set filter_src_port: %v", err)
		}
		if err := xdpSpec.Variables["filter_dst_port"].Set(flags.FilterDstPort); err != nil {
			log.Printf("Warning: Failed to set filter_dst_port: %v", err)
		}
		if err := xdpSpec.Variables["filter_protocol"].Set(flags.GetFilterProtocol()); err != nil {
			log.Printf("Warning: Failed to set filter_protocol: %v", err)
		}
		
		// 打印过滤配置
		fmt.Printf("XDP Filter Configuration:\n")
		if flags.FilterSrcIP != "" {
			fmt.Printf("  Source IP: %s\n", flags.FilterSrcIP)
		}
		if flags.FilterDstIP != "" {
			fmt.Printf("  Destination IP: %s\n", flags.FilterDstIP)
		}
		if flags.FilterSrcPort != 0 {
			fmt.Printf("  Source Port: %d\n", flags.FilterSrcPort)
		}
		if flags.FilterDstPort != 0 {
			fmt.Printf("  Destination Port: %d\n", flags.FilterDstPort)
		}
		if flags.FilterProtocol != "" {
			fmt.Printf("  Protocol: %s\n", flags.FilterProtocol)
		}
		fmt.Printf("  XDP Mode: %s\n", flags.XdpMode)
		
        // 加载XDP程序到内核
        xdpColl, err = ebpf.NewCollection(xdpSpec)
		if err != nil {
			log.Fatalf("Failed to load XDP collection: %v", err)
		}
		defer xdpColl.Close()
		
		// 获取网络接口（这里使用第一个可用接口，实际使用时可能需要指定）
		ifaces, err := net.Interfaces()
		if err != nil {
			log.Fatalf("Failed to get network interfaces: %v", err)
		}
		
		var targetIface string
		if flags.XdpInterface != "" {
			// 用户指定了接口
			targetIface = flags.XdpInterface
			// 验证接口是否存在
			found := false
			for _, iface := range ifaces {
				if iface.Name == targetIface {
					found = true
					break
				}
			}
			if !found {
				log.Fatalf("Specified network interface '%s' not found", targetIface)
			}
		} else {
			// 自动检测合适的接口
			targetIface = "lo"
		}
		
		if targetIface == "" {
			log.Fatalf("No suitable network interface found")
		}
		
		fmt.Printf("Attaching XDP program to interface: %s\n", targetIface)
		
		// 附加XDP程序到网络接口
		xdpProg := xdpColl.Programs["xdp_ingress"]
		if xdpProg == nil {
			log.Fatalf("XDP program not found in collection")
		}
		
		// 获取网络接口索引
		var targetIfaceIndex int
		for _, iface := range ifaces {
			if iface.Name == targetIface {
				targetIfaceIndex = iface.Index
				break
			}
		}
		
		// 根据用户配置选择XDP模式
		var xdpOptions link.XDPOptions
		switch flags.XdpMode {
		case "native":
			xdpOptions = link.XDPOptions{
				Program:   xdpProg,
				Interface: targetIfaceIndex,
				Flags:     link.XDPGenericMode,
			}
		case "skb":
			// 注意：XDPSKBMode 在新版本中可能已被移除，使用 GenericMode 作为替代
			xdpOptions = link.XDPOptions{
				Program:   xdpProg,
				Interface: targetIfaceIndex,
				Flags:     link.XDPGenericMode,
			}
		case "offload":
			xdpOptions = link.XDPOptions{
				Program:   xdpProg,
				Interface: targetIfaceIndex,
				Flags:     link.XDPOffloadMode,
			}
		default:
			log.Printf("Warning: Unknown XDP mode '%s', using native mode", flags.XdpMode)
			xdpOptions = link.XDPOptions{
				Program:   xdpProg,
				Interface: targetIfaceIndex,
				Flags:     link.XDPGenericMode,
			}
		}
		
		xdpLink, err = link.AttachXDP(xdpOptions)
		if err != nil {
			log.Fatalf("Failed to attach XDP program: %v", err)
		}
		
		fmt.Printf("XDP program attached successfully to %s\n", targetIface)
		
		// 将XDP maps添加到主bpfSpec中，以便后续访问
		// 注意：这里需要将 *ebpf.Map 转换为 *ebpf.MapSpec
		// 由于类型不匹配，我们暂时注释掉这部分代码
		// 如果需要访问XDP maps，应该通过 xdpColl 来访问
		/*
		for name, m := range xdpColl.Maps {
			// 这里需要类型转换，暂时跳过
			// bpfSpec.Maps[name] = m
		}
		*/
		
		defer func() {
			if xdpLink != nil {
				if err := xdpLink.Close(); err != nil {
					log.Printf("Failed to close XDP link: %v", err)
				}
			}
		}()
	}

	// 开始输出监听事件
	// 开始系统监听, 另开协程处理监听输出

	if flags.MONITOR {
		fmt.Println("---------System Monitoring---------")
		var validCategories []string
		for _, category := range flags.CATEGORY {
			if _, exists := commander.CommandCategories[category]; exists {
				validCategories = append(validCategories, category)
			} else {
				fmt.Printf("警告: 未知的类别 '%s'，已跳过\n", category)
			}
		}
		if len(validCategories) == 0 {
			log.Fatalf("未指定有效的类别")
			fmt.Println("Available categories:")
			for category := range commander.CommandCategories {
				fmt.Println(category)
			}
			flags.PrintHelp()
			os.Exit(0)
		}
		// 创建输出目录
		if err := os.MkdirAll(flags.StatOutputPath, 0755); err != nil {
			fmt.Printf("创建输出目录失败: %v\n", err)
			os.Exit(1)
		}

		for _, categoryName := range validCategories {
			fmt.Println("categoryName", categoryName)
			go func(cat string) {
				fmt.Printf("启动类别 %s 的监控...\n", cat)

				if err := commander.ShowStatsByCategoryWithContext(ctx, cat, flags.StatOutputPath); err != nil {
					if err == context.Canceled {
						fmt.Printf("类别 %s 监控被用户中断\n", cat)
					} else if err == context.DeadlineExceeded {
						fmt.Printf("类别 %s 监控正常完成\n", cat)
					} else {
						fmt.Printf("类别 %s 执行失败: %v\n", cat, err)
					}
				} else {
					fmt.Printf("类别 %s 监控完成\n", cat)
				}
			}(categoryName)
		}

	}

	if flags.ConfigOptim {
		fmt.Println("Start Analyzing System Workload")
		exePath := "/home/lll/nfsdig/configuration_optimizer/tuning/auto_tuning.py"
		cmd := exec.CommandContext(ctx, "/home/lll/anaconda3/bin/python3", exePath)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err := cmd.Start(); err != nil {
			log.Fatalf("Failed to start optimizer: %v", err)
		}
		go func() {
			if err := cmd.Wait(); err != nil {
				log.Printf("Optimizer exited with error: %v", err)
			} else {
				fmt.Println("Optimizer finished.")
			}
		}()
	}

	fmt.Println("\n\nStart Tracing......")
	var configs []nfsdig.PrinterConfig
	if configs, err = flags.GetPrinterConfigs(); err != nil {
		log.Fatalf("Failed to get printer configs: %s", err)
	}
	output, err := nfsdig.NewOutput(&flags, configs)
	// 启动一个goroutine定期读取数据

	interval := flags.INTERVVAL
	fmt.Println("Will collect data every", interval, "seconds")
	ticker := time.NewTicker(time.Duration(interval) * time.Second)
	defer ticker.Stop()

	if err != nil {
		log.Fatalf("Failed to create output: %s", err)
	}

	// 定义一个等待组用于管理子协程
	var wg sync.WaitGroup

	// 启动单独的goroutine用于处理errorPrinter
	wg.Add(1)
	go func() {
		defer wg.Done()
		errorPrinter := output.GetPrinter("error")
		for {
			select {
			case <-ticker.C:

				errorPrinter.PrintEvent(coll)
			case <-ctx.Done():
				return
			}
		}
	}()

	if flags.TRACKRPC {

		wg.Add(1)
		go func() {
			defer wg.Done()
			rpcPrinter := output.GetPrinter("rpc")
			rpcPrinter.PrintHeader()
			for {
				select {
				case <-ticker.C:

					rpcPrinter.PrintEvent(coll)
				case <-ctx.Done():
					return
				}
			}
		}()
	}

	// 启动单独的goroutine用于处理ioPrinter
	if flags.TRACKFILE {

		wg.Add(1)
		go func() {
			defer wg.Done()
			ioPrinter := output.GetPrinter("io")
			ioPrinter.PrintHeader()
			for {
				select {
				case <-ticker.C:

					ioPrinter.PrintEvent(coll)

				case <-ctx.Done():
					return
				}
			}
		}()
	}

	// 启动单独的goroutine用于处理opPrinter
	if flags.TRACEOPERATIONS {
		wg.Add(1)
		go func() {
			defer wg.Done()
			opPrinter := output.GetPrinter("op")
			opPrinter.PrintHeader()
			for {
				select {
				case <-ticker.C:

					opPrinter.PrintEvent(coll)

				case <-ctx.Done():
					return
				}
			}
		}()
	}

	// 启动单独的goroutine用于处理nfsdPrinter
	if flags.TRACKNFSD {
		wg.Add(1)
		go func() {
			defer wg.Done()
			nfsdPrinter := output.GetPrinter("nfsd")
			nfsdPrinter.PrintHeader()
			for {
				select {
				case <-ticker.C:

					nfsdPrinter.PrintEvent(coll)

				case <-ctx.Done():
					return
				}
			}
		}()
	}

	// 启动单独的goroutine用于处理xdpPrinter
	if flags.TRACKXDP {
		wg.Add(1)
		go func() {
			defer wg.Done()
			xdpPrinter := output.GetPrinter("xdp")
			xdpPrinter.PrintHeader()
			
			// 定期清理XDP统计信息
			cleanupTicker := time.NewTicker(time.Duration(interval*5) * time.Second)
			defer cleanupTicker.Stop()
			
            for {
				select {
				case <-ticker.C:
                    xdpPrinter.PrintEvent(xdpColl)
				case <-cleanupTicker.C:
					// 清理过期的NFS操作统计
                    cleanupXdpStats(xdpColl)
				case <-ctx.Done():
					return
				}
			}
		}()
	}

	// 等待所有goroutine完成（实际上不会退出，除非收到ctx.Done）
	wg.Wait()

	// 等待终止信号
	<-ctx.Done()

	log.Println("Terminating...")
	// 检查退出原因

}

func toSnake(in string) string {
	out := ""
	for i, c := range in {
		if i > 0 && c >= 'A' && c <= 'Z' {
			out += "_"
		}
		out += string(c)
	}
	return strings.ToLower(out)
}

// func readMemoryMetrics(objs *NfsTraceObjects) {
// 	fmt.Println("----------------------------------")
// 	var key uint32 = 0

// 	// ==== 从 eBPF map 获取 page alloc/reclaim 次数 ====
// 	var allocVals []uint64
// 	var reclaimVals []uint64

// 	if err := objs.MemAllocEvents.Lookup(key, &allocVals); err != nil {
// 		log.Printf("[MEM] Failed to read mem_alloc_events: %v", err)
// 	} else {
// 		var total uint64
// 		for _, v := range allocVals {
// 			total += v
// 		}
// 		fmt.Printf("[MEM] Page Allocations: %d\n", total)
// 	}

// 	if err := objs.MemReclaimEvents.Lookup(key, &reclaimVals); err != nil {
// 		log.Printf("[MEM] Failed to read mem_reclaim_events: %v", err)
// 	} else {
// 		var total uint64
// 		for _, v := range reclaimVals {
// 			total += v
// 		}
// 		fmt.Printf("[MEM] Page Reclaims: %d\n", total)
// 	}

// 	// ==== 获取当前系统内存利用率 ====
// 	var sysinfo syscall.Sysinfo_t
// 	if err := syscall.Sysinfo(&sysinfo); err == nil {
// 		total := sysinfo.Totalram * uint64(sysinfo.Unit)
// 		free := sysinfo.Freeram * uint64(sysinfo.Unit)
// 		used := total - free

// 		usedPercent := float64(used) / float64(total) * 100
// 		fmt.Printf("[MEM] Memory Used: %.2f%% \n", usedPercent)

// 		// === 正态分布 μ±3σ 异常检测 ===
// 		if len(memUsageWindow) >= memWindowSize {
// 			memUsageWindow = memUsageWindow[1:] // 移除最旧值
// 		}
// 		memUsageWindow = append(memUsageWindow, usedPercent)

// 		if len(memUsageWindow) >= 10 {
// 			mean, std := calcMeanStd(memUsageWindow)
// 			lower := mean - 3*std
// 			upper := mean + 3*std

// 			if usedPercent < lower || usedPercent > upper {
// 				log.Printf("[MEM] 利用率异常：当前 %.2f%% 超出范围 [%.2f%%, %.2f%%]", usedPercent, lower, upper)
// 			}
// 		}
// 	} else {
// 		log.Printf("[MEM] Failed to get system memory info: %v", err)
// 	}
// 	fmt.Println("----------------------------------")
// }

// 新增：清理XDP统计信息的函数
func cleanupXdpStats(coll *ebpf.Collection) {
	// 清理过期的NFS操作统计（超过1小时的数据）
	nfsOpStatsMap := coll.Maps["nfs_op_stats_map"]
	if nfsOpStatsMap == nil {
		return
	}
	
	iter := nfsOpStatsMap.Iterate()
	
	var key uint32
	var nfsOpStats struct {
		Xid       uint32
		OpType    uint32
		OpCount   uint32
		Timestamp uint64
		SrcIp     uint32
		DstIp     uint32
		SrcPort   uint16
		DstPort   uint16
		Protocol  uint8
		Status    uint32
		DataSize  uint64
		Tag       [32]byte
	}
	
	now := time.Now().UnixNano()
	expireTime := now - int64(time.Hour) // 1小时过期
	
	for iter.Next(&key, &nfsOpStats) {
		if nfsOpStats.Timestamp < uint64(expireTime) {
			nfsOpStatsMap.Delete(&key)
		}
	}
}

// 新增：加载XDP程序的函数
func LoadXdpProgram() (*ebpf.CollectionSpec, error) {
	// 使用bpf2go生成的Go绑定加载XDP程序
	spec, err := LoadXdp()
	if err != nil {
		return nil, fmt.Errorf("failed to load XDP collection spec: %v", err)
	}
	
	// 验证XDP程序是否存在
	if spec.Programs["xdp_ingress"] == nil {
		return nil, fmt.Errorf("XDP program 'xdp_ingress' not found in spec")
	}
	
	return spec, nil
}
