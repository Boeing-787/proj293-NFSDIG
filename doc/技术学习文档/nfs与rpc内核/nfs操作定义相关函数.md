# nfs客户端操作定义

## nfs模块文件系统函数
```

const struct nfs_rpc_ops nfs_v3_clientops = {
	.version	= 3,			/* protocol version */
	.dentry_ops	= &nfs_dentry_operations,
	.dir_inode_ops	= &nfs3_dir_inode_operations,
	.file_inode_ops	= &nfs3_file_inode_operations,
	.file_ops	= &nfs_file_operations,
	.nlmclnt_ops	= &nlmclnt_fl_close_lock_ops,
	.getroot	= nfs3_proc_get_root,
	.submount	= nfs_submount,
	.try_get_tree	= nfs_try_get_tree,
	.getattr	= nfs3_proc_getattr,
	.setattr	= nfs3_proc_setattr,
	.lookup		= nfs3_proc_lookup,
	.lookupp	= nfs3_proc_lookupp,
	.access		= nfs3_proc_access,
	.readlink	= nfs3_proc_readlink,
	.create		= nfs3_proc_create,
	.remove		= nfs3_proc_remove,
	.unlink_setup	= nfs3_proc_unlink_setup,
	.unlink_rpc_prepare = nfs3_proc_unlink_rpc_prepare,
	.unlink_done	= nfs3_proc_unlink_done,
	.rename_setup	= nfs3_proc_rename_setup,
	.rename_rpc_prepare = nfs3_proc_rename_rpc_prepare,
	.rename_done	= nfs3_proc_rename_done,
	.link		= nfs3_proc_link,
	.symlink	= nfs3_proc_symlink,
	.mkdir		= nfs3_proc_mkdir,
	.rmdir		= nfs3_proc_rmdir,
	.readdir	= nfs3_proc_readdir,
	.mknod		= nfs3_proc_mknod,
	.statfs		= nfs3_proc_statfs,
	.fsinfo		= nfs3_proc_fsinfo,
	.pathconf	= nfs3_proc_pathconf,
	.decode_dirent	= nfs3_decode_dirent,
	.pgio_rpc_prepare = nfs3_proc_pgio_rpc_prepare,
	.read_setup	= nfs3_proc_read_setup,
	.read_done	= nfs3_read_done,
	.write_setup	= nfs3_proc_write_setup,
	.write_done	= nfs3_write_done,
	.commit_setup	= nfs3_proc_commit_setup,
	.commit_rpc_prepare = nfs3_proc_commit_rpc_prepare,
	.commit_done	= nfs3_commit_done,
	.lock		= nfs3_proc_lock,
	.clear_acl_cache = forget_all_cached_acls,
	.close_context	= nfs_close_context,
	.have_delegation = nfs3_have_delegation,
	.alloc_client	= nfs_alloc_client,
	.init_client	= nfs_init_client,
	.free_client	= nfs_free_client,
	.create_server	= nfs3_create_server,
	.clone_server	= nfs3_clone_server,
};
```
```
const struct nfs_rpc_ops nfs_v4_clientops = {
	.version	= 4,			/* protocol version */
	.dentry_ops	= &nfs4_dentry_operations,
	.dir_inode_ops	= &nfs4_dir_inode_operations,
	.file_inode_ops	= &nfs4_file_inode_operations,
	.file_ops	= &nfs4_file_operations,
	.getroot	= nfs4_proc_get_root,
	.submount	= nfs4_submount,
	.try_get_tree	= nfs4_try_get_tree,
	.getattr	= nfs4_proc_getattr,
	.setattr	= nfs4_proc_setattr,
	.lookup		= nfs4_proc_lookup,
	.lookupp	= nfs4_proc_lookupp,
	.access		= nfs4_proc_access,
	.readlink	= nfs4_proc_readlink,
	.create		= nfs4_proc_create,
	.remove		= nfs4_proc_remove,
	.unlink_setup	= nfs4_proc_unlink_setup,
	.unlink_rpc_prepare = nfs4_proc_unlink_rpc_prepare,
	.unlink_done	= nfs4_proc_unlink_done,
	.rename_setup	= nfs4_proc_rename_setup,
	.rename_rpc_prepare = nfs4_proc_rename_rpc_prepare,
	.rename_done	= nfs4_proc_rename_done,
	.link		= nfs4_proc_link,
	.symlink	= nfs4_proc_symlink,
	.mkdir		= nfs4_proc_mkdir,
	.rmdir		= nfs4_proc_rmdir,
	.readdir	= nfs4_proc_readdir,
	.mknod		= nfs4_proc_mknod,
	.statfs		= nfs4_proc_statfs,
	.fsinfo		= nfs4_proc_fsinfo,
	.pathconf	= nfs4_proc_pathconf,
	.set_capabilities = nfs4_server_capabilities,
	.decode_dirent	= nfs4_decode_dirent,
	.pgio_rpc_prepare = nfs4_proc_pgio_rpc_prepare,
	.read_setup	= nfs4_proc_read_setup,
	.read_done	= nfs4_read_done,
	.write_setup	= nfs4_proc_write_setup,
	.write_done	= nfs4_write_done,
	.commit_setup	= nfs4_proc_commit_setup,
	.commit_rpc_prepare = nfs4_proc_commit_rpc_prepare,
	.commit_done	= nfs4_commit_done,
	.lock		= nfs4_proc_lock,
	.clear_acl_cache = nfs4_zap_acl_attr,
	.close_context  = nfs4_close_context,
	.open_context	= nfs4_atomic_open,
	.have_delegation = nfs4_have_delegation,
	.alloc_client	= nfs4_alloc_client,
	.init_client	= nfs4_init_client,
	.free_client	= nfs4_free_client,
	.create_server	= nfs4_create_server,
	.clone_server	= nfs_clone_server,
	.discover_trunking = nfs4_discover_trunking,
	.enable_swap	= nfs4_enable_swap,
	.disable_swap	= nfs4_disable_swap,
};


const struct file_operations nfs4_file_operations = {
	.read_iter	= nfs_file_read,
	.write_iter	= nfs_file_write,
	.mmap		= nfs_file_mmap,
	.open		= nfs4_file_open,
	.flush		= nfs4_file_flush,
	.release	= nfs_file_release,
	.fsync		= nfs_file_fsync,
	.lock		= nfs_lock,
	.flock		= nfs_flock,
	.splice_read	= nfs_file_splice_read,
	.splice_write	= iter_file_splice_write,
	.check_flags	= nfs_check_flags,
	.setlease	= nfs4_setlease,
#ifdef CONFIG_NFS_V4_2
	.copy_file_range = nfs4_copy_file_range,
	.llseek		= nfs4_file_llseek,
	.fallocate	= nfs42_fallocate,
	.remap_file_range = nfs42_remap_file_range,
#else
	.llseek		= nfs_file_llseek,
#endif
};



static const struct inode_operations nfs4_file_inode_operations = {
	.permission	= nfs_permission,
	.getattr	= nfs_getattr,
	.setattr	= nfs_setattr,
	.listxattr	= nfs4_listxattr,
};

static const struct inode_operations nfs4_dir_inode_operations = {
	.create		= nfs_create,
	.lookup		= nfs_lookup,
	.atomic_open	= nfs_atomic_open,
	.link		= nfs_link,
	.unlink		= nfs_unlink,
	.symlink	= nfs_symlink,
	.mkdir		= nfs_mkdir,
	.rmdir		= nfs_rmdir,
	.mknod		= nfs_mknod,
	.rename		= nfs_rename,
	.permission	= nfs_permission,
	.getattr	= nfs_getattr,
	.setattr	= nfs_setattr,
	.listxattr	= nfs4_listxattr,
};

const struct dentry_operations nfs4_dentry_operations = {
	.d_revalidate	= nfs4_lookup_revalidate,
	.d_weak_revalidate	= nfs_weak_revalidate,
	.d_delete	= nfs_dentry_delete,
	.d_iput		= nfs_dentry_iput,
	.d_automount	= nfs_d_automount,
	.d_release	= nfs_d_release,
};
```

## nfs向vfs注册的地址空间处理函数
在 Linux 内核中，struct address_space_operations 是 VFS（虚拟文件系统）与底层文件系统之间的一个关键接口。它定义了文件系统如何操作其对应的页缓存（page cache）。
每个打开的文件都有一个 address_space 对象，它负责管理该文件的页缓存（page cache）。
```
   const struct address_space_operations nfs_file_aops = {
      .read_folio = nfs_read_folio,\\当需要读取某个文件偏移位置的页时，如果该页不在缓存中，则调用此函数进行填充。
      .readahead = nfs_readahead,
      .dirty_folio = filemap_dirty_folio,
      .writepages = nfs_writepages,\\负责将所有脏页异步写回到服务器
      .write_begin = nfs_write_begin,
      .write_end = nfs_write_end,\\写入结束后更新页状态（如设置 dirty、解锁等）。
      .invalidate_folio = nfs_invalidate_folio,\\当文件被截断（truncate）或关闭时，清除指定页缓存中的内容。
      .release_folio = nfs_release_folio,\\释放页缓存中的页，通常发生在页不再使用时。
      .migrate_folio = nfs_migrate_folio,\\页面迁移时调用，比如内存热插拔或 NUMA 迁移
      .launder_folio = nfs_launder_folio,\\在页被回收之前，如果页是脏的，会在此处触发写回操作。
      .is_dirty_writeback = nfs_check_dirty_writeback,\\判断当前页是否处于写回状态
      .error_remove_folio = generic_error_remove_folio,
      .swap_activate = nfs_swap_activate,
      .swap_deactivate = nfs_swap_deactivate,
      .swap_rw = nfs_swap_rw,
   };
```