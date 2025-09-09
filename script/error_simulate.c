#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>

#define TEST_FILE "/home/lll/nfs/testfile"

// 触发 -EINVAL: 使用非法偏移量读取文件
void trigger_einval(const char *filepath) {
    int fd = open(filepath, O_RDONLY);
    if (fd == -1) {
        perror("open");
        return;
    }

    char buf[1024];

    // 设置一个非法偏移量（超过文件最大允许偏移）
    off_t invalid_offset = 0xFFFFFFFFFFFFFFFF; // -1 in signed 64-bit
    if (lseek(fd, invalid_offset, SEEK_SET) == -1) {
        perror("lseek");
        close(fd);
        return;
    }

    ssize_t bytes_read = read(fd, buf, sizeof(buf));
    if (bytes_read == -1) {
        printf("Triggered error: %s (%d)\n", strerror(errno), errno);
    } else {
        printf("Unexpected success: read %ld bytes\n", bytes_read);
    }

    close(fd);
}

//触发 -EFAULT
void trigger_efault() {
    char *bad_addr = (char *)0x1;
    ssize_t ret = read(0, bad_addr, 1);
    if (ret == -1) {
        printf("Triggered EFAULT: %s (%d)\n", strerror(errno), errno);
    }
}

// 触发其他错误：
// 2. 触发 -ESTALE
// 手动卸载并重新挂载 NFS 目录后访问原文件句柄即可。

// 3. 触发 -EIO
// 断开 NFS 服务器网络后尝试访问文件。

int main(int argc, char *argv[]) {
    const char *mount_point = argc > 1 ? argv[1] : "/mnt/nfs";

    // 构建测试文件路径
    char test_file[256];
    snprintf(test_file, sizeof(test_file), "%s/testfile", mount_point);

    // 创建测试文件
    int fd = open(test_file, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd == -1) {
        perror("create testfile");
        return 1;
    }
    write(fd, "test data", 9);
    close(fd);

    // 触发 EINVAL
    printf("Triggering -EINVAL...\n");
    trigger_einval(test_file);

    return 0;
}