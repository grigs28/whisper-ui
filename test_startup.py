#!/usr/bin/env python3
"""
测试脚本 - 验证Whisper UI应用能否正常启动
"""

import sys
import os
import subprocess
import time

def test_application_startup():
    """测试应用启动"""
    print("正在测试Whisper UI应用启动...")
    
    # 尝试启动应用
    try:
        # 使用subprocess启动应用，但设置超时时间
        process = subprocess.Popen([
            sys.executable, 'main.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # 等待几秒钟让应用启动
        time.sleep(3)
        
        # 检查进程是否仍在运行
        if process.poll() is None:
            print("✓ 应用启动成功")
            # 终止进程
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return True
        else:
            stdout, stderr = process.communicate()
            print(f"✗ 应用启动失败: {stderr}")
            return False
            
    except Exception as e:
        print(f"✗ 启动测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_application_startup()
    if success:
        print("测试通过！应用可以正常启动。")
        sys.exit(0)
    else:
        print("测试失败！应用启动存在问题。")
        sys.exit(1)
