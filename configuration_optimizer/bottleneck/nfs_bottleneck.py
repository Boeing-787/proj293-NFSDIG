# import subprocess
# import json
# sudo fio --name=test --directory=/home/lll/nfs --rw=read --bs=64M --size=256M --numjobs=1 --direct=1 --time_based --runtime=120 --output-format=jso

import subprocess
import json

def test_nfs_perf_nfsio(directory="/home/lll/nfs", timeout=300, numjobs=32, bs="1M", size="32M"):
    # fio_cmd = [
    #     "sudo", "fio", "--name=nfs_stress_test", f"--directory={directory}",
    #     "--rw=readwrite", f"--bs={bs}", f"--size={size}", f"--numjobs={numjobs}",
    #     "--rwmixread=50", "--direct=1", "--output-format=json"
    # ]

    fio_cmd = [
        "sudo", "fio", "--name=nfs_stress_test", f"--directory={directory}",
        "--rw=read", f"--bs={bs}", f"--size={size}", f"--numjobs={numjobs}",
        "--direct=1", "--output-format=json"
    ]

    try:
        result = subprocess.run(fio_cmd, capture_output=True, text=True, timeout=timeout)

        if result.stdout.strip():
            output = json.loads(result.stdout)
            print("FIO JSON 解析成功")

            num = len(output['jobs'])
            total_read_bw = 0
            total_write_bw = 0
            total_read_lat_ns = 0
            total_write_lat_ns = 0

            for job in output['jobs']:
                read = job.get('read', {})
                write = job.get('write', {})
                read_bw = read.get('bw', 0)
                write_bw = write.get('bw', 0)
                read_lat = read.get('lat_ns', {}).get('mean', 0)
                write_lat = write.get('lat_ns', {}).get('mean', 0)

                total_read_bw += read_bw
                total_write_bw += write_bw
                total_read_lat_ns += read_lat
                total_write_lat_ns += write_lat

            avg_read_bw = total_read_bw / num
            avg_write_bw = total_write_bw / num
            avg_read_lat_ms = total_read_lat_ns / num / 1e6
            avg_write_lat_ms = total_write_lat_ns / num / 1e6

            return avg_read_bw, avg_read_lat_ms, avg_write_bw, avg_write_lat_ms

        else:
            print("FIO 输出为空")
            return 0, float('inf'), 0, float('inf')

    except subprocess.TimeoutExpired:
        print("FIO 执行超时")
        return 0, float('inf'), 0, float('inf')

    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        return 0, float('inf'), 0, float('inf')

    except Exception as e:
        print(f"FIO 执行失败: {e}")
        return 0, float('inf'), 0, float('inf')


def run_nfs_limit_test():
    numjobs_list = [1 ,2, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64]
    bs = "1M"
    size = "16M"
    directory = "/mnt/nfs_test"

    prev_read_bw = 0
    prev_write_bw = 0
    prev_read_lat = float("inf")
    prev_write_lat = float("inf")
    threshold = 0.05  # 5%变化判断瓶颈

    for idx, jobs in enumerate(numjobs_list):

        read_bw, read_lat, write_bw, write_lat = test_nfs_perf_nfsio(
            directory=directory,
            numjobs=jobs,
            bs=bs,
            size=size
        )

        print(f"[numjobs={jobs}]")
        print(f"  Read  : {read_bw:.2f} KiB/s | Latency: {read_lat:.2f} ms")
        print(f"  Write : {write_bw:.2f} KiB/s | Latency: {write_lat:.2f} ms")

        if idx > 0:
            read_bw_growth = (read_bw - prev_read_bw) / prev_read_bw if prev_read_bw > 0 else 1
            write_bw_growth = (write_bw - prev_write_bw) / prev_write_bw if prev_write_bw > 0 else 1
            read_lat_growth = (read_lat - prev_read_lat) / prev_read_lat if prev_read_lat > 0 else 0
            write_lat_growth = (write_lat - prev_write_lat) / prev_write_lat if prev_write_lat > 0 else 0

            if all(abs(metric) < threshold for metric in [read_bw_growth, write_bw_growth, read_lat_growth, write_lat_growth]):
                print("检测到性能瓶颈，停止测试。")
                break

        prev_read_bw = read_bw
        prev_write_bw = write_bw
        prev_read_lat = read_lat
        prev_write_lat = write_lat

if __name__ == "__main__":
    run_nfs_limit_test()



# def test_nfs_perf_nfsio(directory="/home/lll/nfs", timeout=300, numjobs=4, bs="1M", size="32M"):
#     # fio_cmd = [
#     #     "sudo", "fio", "--name=nfs_stress_test", f"--directory={directory}",
#     #     "--rw=readwrite", f"--bs={bs}", f"--size={size}", f"--numjobs={numjobs}",
#     #     "--rwmixread=50", "--direct=1", "--output-format=json"
#     # ]
#     fio_cmd = [
#         "sudo", "fio", "--name=nfs_stress_test", f"--directory={directory}",
#         "--rw=read", f"--bs={bs}", f"--size={size}", f"--numjobs={numjobs}",
#         "--direct=1", "--output-format=json"
#     ]

#     try:
#         result = subprocess.run(fio_cmd, capture_output=True, text=True, timeout=timeout)

#         if result.stdout.strip():
#             output = json.loads(result.stdout)
#             print("FIO JSON 解析成功")

#             num = len(output['jobs'])
#             total_read_bw = 0
#             total_write_bw = 0
#             total_read_lat_ns = 0
#             total_write_lat_ns = 0

#             for job in output['jobs']:
#                 read = job.get('read', {})
#                 write = job.get('write', {})
#                 read_bw = read.get('bw', 0)
#                 write_bw = write.get('bw', 0)
#                 read_lat = read.get('lat_ns', {}).get('mean', 0)
#                 write_lat = write.get('lat_ns', {}).get('mean', 0)

#                 total_read_bw += read_bw
#                 total_write_bw += write_bw
#                 total_read_lat_ns += read_lat
#                 total_write_lat_ns += write_lat

#             avg_read_bw = total_read_bw / num
#             avg_write_bw = total_write_bw / num
#             avg_read_lat_ms = total_read_lat_ns / num / 1e6
#             avg_write_lat_ms = total_write_lat_ns / num / 1e6

#             return avg_read_bw, avg_read_lat_ms, avg_write_bw, avg_write_lat_ms

#         else:
#             print("FIO 输出为空")
#             return 0, float('inf'), 0, float('inf')

#     except subprocess.TimeoutExpired:
#         print("FIO 执行超时")
#         return 0, float('inf'), 0, float('inf')

#     except json.JSONDecodeError as e:
#         print(f"JSON解析失败: {e}")
#         return 0, float('inf'), 0, float('inf')

#     except Exception as e:
#         print(f"FIO 执行失败: {e}")
#         return 0, float('inf'), 0, float('inf')


# def run_nfs_bs_test():
#     bs_list = ["4K", "8K", "16K", "32K", "64K", "128K", "256K", "512K", "1M", "2M", "4M","8M", "12M", "16M","20M", "24M","28M","32M"]
#     numjobs = 1
#     directory = "/mnt/nfs_test"

#     for bs in bs_list:
#         # 计算 size = bs × 32
#         if bs.endswith("K"):
#             size_val = int(bs[:-1]) * 16
#             size = f"{size_val}K"
#         elif bs.endswith("M"):
#             size_val = int(bs[:-1]) * 16
#             size = f"{size_val}M"
#         else:
#             print(f"不支持的 block size 格式: {bs}")
#             continue

#         print(f"\n[bs={bs}, size={size}, numjobs={numjobs}]")
#         read_bw, read_lat, write_bw, write_lat = test_nfs_perf_nfsio(
#             directory=directory,
#             numjobs=numjobs,
#             bs=bs,
#             size=size
#         )

#         print(f"  Read  : {read_bw:.2f} KiB/s | Latency: {read_lat:.2f} ms")
#         print(f"  Write : {write_bw:.2f} KiB/s | Latency: {write_lat:.2f} ms")


# if __name__ == "__main__":
#     run_nfs_bs_test()