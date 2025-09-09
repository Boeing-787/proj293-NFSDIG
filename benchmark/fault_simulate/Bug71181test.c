#include <stdio.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>


int main()
{
        int fd = creat ("/mnt/nfs_test/file", 0600);
        struct stat st1, st2;
        struct timespec t[2] = { { 1000000000, 0 }, { 0, UTIME_OMIT } };

        fstat(fd, &st1);
        sleep(1);
        printf("st1.st_ctime: %ld\n", st1.st_ctime);
        futimens(fd, t); 
        printf("futimens success\n");
        fstat(fd, &st2);

        if (st1.st_ctime == st2.st_ctime)
                printf("failed to update ctime!\n");
        else 
                printf("update ctime success\n");
        return 0;
}