#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys
from pathlib import Path



def run_fio_test(scene, mnt_path):
    """运行fio测试"""
    # 获取当前脚本所在目录
    script_dir = Path(__file__).parent
    fio_config = script_dir / f"{scene}.fio"
    
    if not fio_config.exists():
        print(f"✗ 配置文件不存在: {fio_config}")
        return False
    
    # 更新配置文件中的目录路径
    update_config_directory(fio_config, mnt_path)
    
    print(f"🚀 开始运行 {scene} 场景测试...")
    print(f"📁 测试目录: {mnt_path}")
    print(f"📄 配置文件: {fio_config}")
    
    try:
        # 运行fio测试
        result = subprocess.run(['fio', str(fio_config)], 
                              capture_output=True, text=True, 
                              cwd=script_dir)
        
        # 输出结果
        if result.stdout:
            print("\n📊 测试结果:")
            print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  警告信息:")
            print(result.stderr)
        
        if result.returncode == 0:
            print(f"✅ {scene} 场景测试完成")
            return True
        else:
            print(f"❌ {scene} 场景测试失败，返回码: {result.returncode}")
            return False
            
    except FileNotFoundError:
        print("❌ 错误: 未找到 fio 命令，请确保已安装 fio")
        return False
    except Exception as e:
        print(f"❌ 运行测试时出错: {e}")
        return False

def update_config_directory(config_file, new_directory):
    """更新配置文件中的目录路径"""
    try:
        with open(config_file, 'r') as f:
            content = f.read()
        
        # 替换目录路径
        content = content.replace('directory=/mnt/nfs_test', f'directory={new_directory}')
        
        with open(config_file, 'w') as f:
            f.write(content)         
    except Exception as e:
        print(f"⚠️  更新配置文件失败: {e}")

def main():
    # 创建解析器
    parser = argparse.ArgumentParser(description="FIO 性能测试工具")
    
    # 添加参数
    parser.add_argument('--scene', type=str, help='测试场景', 
                       choices=['tiny_file', 'libaio', 'sync', 'simple_test', 
                               'fileserver', 'webserver', 'mailserver'], 
                       default='simple_test')
    parser.add_argument('--mnt', type=str, help='挂载目录', 
                       choices=['/mnt/nfs_test', '~/nfs'], 
                       default='~/nfs')
    parser.add_argument('--debug', type=bool, help='调试模式', default=False)
    
    # 解析参数
    args = parser.parse_args()
    print(f"📋 测试场景: {args.scene}")
    print(f"📁 挂载目录: {args.mnt}")
    print("=" * 50)
    
    
    # 运行fio测试
    success = run_fio_test(args.scene, mnt_path)
    
    if success:
        print("\n🎉 所有测试完成！")
        sys.exit(0)
    else:
        print("\n💥 测试过程中出现错误")
        sys.exit(1)

if __name__ == "__main__":
    main()
