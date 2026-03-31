#!/usr/bin/env python3
"""
ADB 交互工具手动测试脚本

用于手动测试需要实际操作设备的工具。
"""

import asyncio
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def test_input_with_space():
    """测试输入带空格的文本"""
    print("\n" + "=" * 60)
    print("测试: 输入带空格的文本")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    from app.tools.builtin.adb.input_tools import input_text
    
    manager = get_adb_manager()
    await manager.initialize()
    
    devices = manager.list_devices(online_only=True)
    if not devices:
        print("❌ 没有在线设备")
        return False
    
    serial = devices[0].serial
    print(f"设备: {serial}")
    print("\n请打开一个可以输入文本的应用（如记事本、搜索框等）")
    print("准备好后按 Enter 键继续...")
    input()
    
    test_text = "Hello ADB Test"
    print(f"\n即将输入: \"{test_text}\"")
    print("注意检查设备上是否正确显示空格！\n")
    
    result = await input_text(test_text, serial=serial)
    
    if result["code"] == 200:
        print("✅ 输入命令执行成功")
        print("\n请检查设备上是否显示:")
        print(f"  期望: \"{test_text}\"（带空格）")
        print("  实际: （请目视检查设备屏幕）")
        
        response = input("\n显示正确（带空格）？(y/n): ").strip().lower()
        if response == 'y':
            print("✅ 空格处理修复成功！")
            return True
        else:
            print("❌ 空格仍然丢失")
            return False
    else:
        print(f"❌ 输入失败: {result['message']}")
        return False


async def test_tap():
    """测试点击"""
    print("\n" + "=" * 60)
    print("测试: 点击屏幕中心")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    from app.tools.builtin.adb.interaction_tools import tap
    
    manager = get_adb_manager()
    devices = manager.list_devices(online_only=True)
    
    if not devices:
        print("❌ 没有在线设备")
        return False
    
    serial = devices[0].serial
    print(f"设备: {serial}")
    print("\n即将点击屏幕中心位置")
    print("准备好后按 Enter 键继续...")
    input()
    
    # 使用归一化坐标 (500, 500) = 屏幕中心
    result = await tap(x=500, y=500, serial=serial, normalized=True)
    
    if result["code"] == 200:
        print("✅ 点击成功")
        print(f"   坐标: ({result['data']['x']}, {result['data']['y']})")
        return True
    else:
        print(f"❌ 点击失败: {result['message']}")
        return False


async def test_keyevent():
    """测试按键事件"""
    print("\n" + "=" * 60)
    print("测试: 按键事件（Home键）")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    from app.tools.builtin.adb.input_tools import keyevent
    
    manager = get_adb_manager()
    devices = manager.list_devices(online_only=True)
    
    if not devices:
        print("❌ 没有在线设备")
        return False
    
    serial = devices[0].serial
    print(f"设备: {serial}")
    print("\n即将发送 Home 键，设备将返回主屏幕")
    print("准备好后按 Enter 键继续...")
    input()
    
    result = await keyevent(key="KEYCODE_HOME", serial=serial)
    
    if result["code"] == 200:
        print("✅ 按键发送成功")
        print("   设备应该已返回主屏幕")
        return True
    else:
        print(f"❌ 按键发送失败: {result['message']}")
        return False


async def main():
    """主测试流程"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 13 + "ADB 交互工具手动测试" + " " * 20 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    print("⚠️  注意: 这些测试将实际操作您的设备")
    print()
    
    tests = [
        ("输入带空格文本", test_input_with_space),
        ("点击屏幕", test_tap),
        ("按键事件", test_keyevent),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        response = input(f"执行测试: {test_name}? (y/n，直接回车跳过): ").strip().lower()
        
        if response == 'y':
            try:
                result = await test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"\n❌ 测试异常: {test_name}")
                print(f"   错误: {e}")
                import traceback
                traceback.print_exc()
                results.append((test_name, False))
        else:
            print(f"⏭️  跳过测试: {test_name}")
            results.append((test_name, None))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for test_name, result in results:
        if result is None:
            status = "⏭️  跳过"
        elif result:
            status = "✅ 通过"
        else:
            status = "❌ 失败"
        print(f"  {status}  {test_name}")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

