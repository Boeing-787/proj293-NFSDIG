# small_files_create.f
# Filebench script to simulate the creation of a large number of small files

# 定义文件集
# 这里我们定义了一个名为 "smallfiles" 的文件集
# 文件将被创建在 /tmp/filebench_test 目录下
# 每个文件的大小为 4KB (典型的小文件)
# 总共创建 10000 个文件
# 预分配所有文件以减少运行时开销
define fileset name=smallfiles,path=/tmp/filebench_test,size=4k,entries=10000,prealloc=100

# 定义进程
# 创建一个名为 "creator" 的进程，运行一个实例
define process name=creator,instances=1
{
  # 在进程中定义一个线程
  # 分配 10MB 内存给线程
  thread name=creator_thread,memsize=10m
  {
    # 流操作：创建文件
    # 使用 "create" 操作来创建文件
    # 文件来自之前定义的 "smallfiles" 文件集
    flowop create name=create-file,filesetname=smallfiles
  }
}

# 输出提示信息
echo "Starting filebench run to create a large number of small files..."

# 运行测试 60 秒
# 在这段时间内，Filebench 将尽可能多地创建文件
run 60