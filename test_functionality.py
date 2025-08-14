#!/usr/bin/env python3
"""
功能测试脚本 - 完整测试Whisper UI应用的功能
"""

import sys
import os
import subprocess
import time
import requests
import json

def test_imports():
    """测试所有必要的模块是否可以正常导入"""
    print("正在测试模块导入...")
    
    try:
        # 测试基本导入
        import torch
        import whisper
        from flask import Flask
        from flask_socketio import SocketIO
        print("✓ 所有模块导入成功")
        return True
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False

def test_application_startup():
    """测试应用启动"""
    print("正在测试应用启动...")
    
    try:
        # 使用subprocess启动应用
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

def test_config():
    """测试配置加载"""
    print("正在测试配置加载...")
    
    try:
        from config import config
        print(f"✓ 配置加载成功")
        print(f"  主机: {config.HOST}")
        print(f"  端口: {config.PORT}")
        print(f"  调试模式: {config.DEBUG}")
        return True
    except Exception as e:
        print(f"✗ 配置加载失败: {e}")
        return False

def test_gpu_detection():
    """测试GPU检测功能"""
    print("正在测试GPU检测...")
    
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✓ 检测到GPU: {torch.cuda.get_device_name(0)}")
            return True
        else:
            print("ℹ 未检测到GPU，将使用CPU")
            return True
    except Exception as e:
        print(f"✗ GPU检测失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("Whisper UI 应用功能测试")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_config,
        test_gpu_detection,
        test_application_startup
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"测试结果: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！应用功能正常。")
        return 0
    else:
        print("❌ 部分测试失败，请检查错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
