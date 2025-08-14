#!/usr/bin/env python3
"""
系统测试脚本
用于验证改进后的Whisper转录系统的功能
"""

import os
import sys
import unittest
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from main import SUPPORTED_LANGUAGES, WHISPER_MODELS


class TestWhisperSystem(unittest.TestCase):
    """Whisper系统测试类"""
    
    def test_supported_languages_count(self):
        """测试支持的语言数量是否为10"""
        self.assertEqual(len(SUPPORTED_LANGUAGES), 10)
        
    def test_supported_languages_content(self):
        """测试支持的语言内容"""
        expected_languages = [
            ('zh', '中文'),
            ('en', '英语'),
            ('ja', '日语'),
            ('ko', '韩语'),
            ('fr', '法语'),
            ('de', '德语'),
            ('es', '西班牙语'),
            ('ru', '俄语'),
            ('ar', '阿拉伯语'),
            ('pt', '葡萄牙语')
        ]
        
        self.assertEqual(SUPPORTED_LANGUAGES, expected_languages)
        
    def test_whisper_models(self):
        """测试Whisper模型列表"""
        expected_models = ['tiny', 'base', 'small', 'medium', 'large']
        self.assertEqual(WHISPER_MODELS, expected_models)
        
    def test_config_exists(self):
        """测试配置文件是否存在"""
        self.assertTrue(os.path.exists('config.py'))
        
    def test_main_exists(self):
        """测试主程序文件是否存在"""
        self.assertTrue(os.path.exists('main.py'))
        
    def test_templates_exist(self):
        """测试模板文件是否存在"""
        self.assertTrue(os.path.exists('templates/index.html'))
        
    def test_static_files_exist(self):
        """测试静态文件是否存在"""
        css_path = 'static/css/index.css'
        js_path = 'static/js/components/fileManager.js'
        
        self.assertTrue(os.path.exists(css_path))
        self.assertTrue(os.path.exists(js_path))


def run_tests():
    """运行所有测试"""
    print("开始运行系统测试...")
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWhisperSystem)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n✅ 所有测试通过！")
        return True
    else:
        print(f"\n❌ 测试失败: {len(result.failures)} 个失败, {len(result.errors)} 个错误")
        return False


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
