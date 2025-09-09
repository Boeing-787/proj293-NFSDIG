# NFS4.0新特性
1. RPC & security: 
	-  远程数据传输的基础：**XDR（External Data Representation）** 和 **RPC（Remote Procedure Call）**
	- **RPCSEC_GSS 框架**：为了满足端到端的安全需求，NFSv4 使用了 **RPCSEC_GSS** 框架（定义于 [RFC2203]）来扩展基本的 RPC 安全性
	- NFSv4 使用 **Kerberos V5**（定义于 [RFC1964]）作为一种安全机制，提供基于票据的身份验证。
	- NFSv4 还支持 **LIPKEY**（定义于 [RFC2847]）作为另一种安全机制。LIPKEY 允许使用用户密码和服务器的公钥进行身份验证，适合某些特定场景。
2.  COMPOUND procedure： 多个文件系统操作整合为一个发送
3. 文件系统模型：
	 - **NFSv4 简化了路径名到文件句柄的映射**：
	    - 不再需要单独的 MOUNT 协议，而是通过一个 ROOT 文件句柄直接访问文件系统树的根。
	- **伪文件系统的引入**：
	    - 通过伪文件系统，NFSv4 服务器可以将多个实际文件系统整合为一个逻辑文件系统树，填补路径中的空隙。
	- **改进的路径解析**：
	    - 客户端可以通过一个统一的逻辑视图访问服务器上的文件系统，而无需关心底层的实际文件系统结构。
	+ 引入了 **volatile（易失性）文件句柄** 的概念
	+  引入了三种类型的属性分类（mandatory、recommended 和 named attributes），以增强协议的灵活性、可扩展性和跨平台的兼容性。
		+ **Mandatory Attributes（必需属性）**: 文件大小、文件类型、时间戳（如创建时间、修改时间）等
		+ **Recommended Attributes（推荐属性**: ACL
		+ **Named Attributes**： 命名属性是与文件或目录关联的 **不透明字节流（opaque byte stream）**，可以通过字符串名称引用。它们是为客户端应用程序设计的，用于将特定的应用程序数据与文件或目录关联。
	- 引入了一个特殊的文件属性，称为 **`filesystem locations attribute`**。这个属性允许客户端查询文件系统的位置信息。客户端可以根据自身的策略（如延迟、负载等）选择最合适的副本进行访问。
4. OPEN & CLOSE operations
5. 文件锁：基于租约release的模型
6. NFSv4 在缓存管理方面的一个重要改进是引入了 **文件委托（delegation）** 概念：- 允许服务器将文件操作的责任委托给客户端。通过读委托和写委托，客户端可以在本地处理文件操作，减少与服务器的交互
# NFS4.2新特性
1. 服务端copy
2. 客户端IO建议
3. Sparse files 处理和space reservation：Sparse files  are files that have unallocated or uninitialized data blocks as holes in the file.
4. Application Data Block (ADB) Support
5. Labeled NFS: 服务端和客户端共享Mandatory Access Control (MAC) security models
6. pNFS layout: communicate back to the metadata server
   any errors or performance characteristics with the storage devices

#### Minor版本更新
在 NFSv4.2 中，引入了 **判别联合（Discriminated Unions）** 的概念，用于操作的参数定义。

to do continue...

# nfstest
[NFStest-CSDN博客](https://blog.csdn.net/QTM_Gitee/article/details/133858361)