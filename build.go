//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target $TARGET_GOARCH -cc clang -no-strip NfsTrace ./bpf/nfs_trace.c -- -I ./bpf/headers -Wno-address-of-packed-member
//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target $TARGET_GOARCH -cc clang -no-strip Xdp ./bpf/xdp.c -- -I ./bpf/headers -Wno-address-of-packed-member
package main
