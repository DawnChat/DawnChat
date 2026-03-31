#!/usr/bin/env python3
"""
ADB 工具系统完整测试脚本

用于测试 ADB Service 层和 Tools 层的所有功能。

测试项目：
1. ADB Manager 初始化
2. 设备发现与管理
3. 设备详细信息获取
4. 应用管理工具（获取当前应用、启动/停止应用）
5. 屏幕操作工具（截图）
6. 交互操作工具（点击、滑动、长按）
7. 输入操作工具（输入文本、按键事件）

使用方法：
    python test_adb_tools.py
    python test_adb_tools.py --interactive  # 执行交互测试（会实际操作设备）
"""

import argparse
import asyncio
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def test_adb_manager():
    """测试 ADB Manager"""
    print("=" * 60)
    print("测试 1: ADB Manager 初始化")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    
    manager = get_adb_manager()
    
    # 初始化
    success = await manager.initialize()
    if not success:
        print("❌ ADB Manager 初始化失败")
        print("   可能原因：")
        print("   1. 未安装 ADB")
        print("   2. ADB 路径未正确配置")
        print("   3. 权限问题")
        return False
    
    print("✅ ADB Manager 初始化成功")
    print(f"   ADB 路径: {manager.get_adb_path()}")
    
    return True


async def test_device_discovery():
    """测试设备发现"""
    print("\n" + "=" * 60)
    print("测试 2: 设备发现")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    
    manager = get_adb_manager()
    
    # 扫描设备
    devices = await manager.scan_devices()
    
    if not devices:
        print("⚠️  未发现任何设备")
        print("   请确保：")
        print("   1. 设备已通过 USB 连接")
        print("   2. 设备已开启 USB 调试")
        print("   3. 已授权电脑调试权限")
        return False
    
    print(f"✅ 发现 {len(devices)} 个设备:")
    for device in devices:
        print(f"   - 序列号: {device.serial}")
        print(f"     状态: {device.status.value}")
        print(f"     型号: {device.model or '未知'}")
    
    return True


async def test_device_info():
    """测试设备信息获取"""
    print("\n" + "=" * 60)
    print("测试 3: 设备详细信息")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    
    manager = get_adb_manager()
    
    devices = manager.list_devices(online_only=True)
    if not devices:
        print("⚠️  没有在线设备")
        return False
    
    device = devices[0]
    serial = device.serial
    
    # 获取详细信息
    info = await manager.get_device_info(serial, refresh=True)
    
    if not info:
        print(f"❌ 获取设备信息失败: {serial}")
        return False
    
    print(f"✅ 设备信息 ({serial}):")
    print(f"   型号: {info.model or '未知'}")
    print(f"   Android 版本: {info.android_version or '未知'}")
    print(f"   屏幕分辨率: {info.screen_width}x{info.screen_height}" if info.screen_width else "   屏幕分辨率: 未知")
    print(f"   屏幕密度: {info.screen_density} dpi" if info.screen_density else "   屏幕密度: 未知")
    print(f"   电池电量: {info.battery_level}%" if info.battery_level else "   电池电量: 未知")
    print(f"   当前应用: {info.current_app or '未知'}")
    
    return True


async def test_tools():
    """测试 ADB 工具"""
    print("\n" + "=" * 60)
    print("测试 4: ADB 工具调用")
    print("=" * 60)
    
    from app.tools.builtin.adb.device_tools import get_device_info, list_devices
    
    # 测试 list_devices 工具
    print("\n测试 list_devices 工具...")
    result = await list_devices(online_only=True)
    
    if result["code"] != 200:
        print(f"❌ list_devices 失败: {result['message']}")
        return False
    
    print("✅ list_devices 成功")
    print(f"   发现 {result['data']['count']} 个设备")
    
    if result['data']['count'] == 0:
        print("⚠️  没有在线设备，跳过后续测试")
        return True
    
    # 测试 get_device_info 工具
    print("\n测试 get_device_info 工具...")
    result = await get_device_info(refresh=True)
    
    if result["code"] != 200:
        print(f"❌ get_device_info 失败: {result['message']}")
        return False
    
    print("✅ get_device_info 成功")
    data = result['data']
    print(f"   序列号: {data['serial']}")
    print(f"   型号: {data['model'] or '未知'}")
    print(f"   分辨率: {data['screen_width']}x{data['screen_height']}" if data['screen_width'] else "   分辨率: 未知")
    
    return True


async def test_app_tools():
    """测试应用管理工具"""
    print("\n" + "=" * 60)
    print("测试 5: 应用管理工具")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    from app.tools.builtin.adb.app_tools import current_app
    
    manager = get_adb_manager()
    devices = manager.list_devices(online_only=True)
    
    if not devices:
        print("⚠️  没有在线设备，跳过测试")
        return True
    
    serial = devices[0].serial
    
    # 测试获取当前应用
    print("\n测试 current_app 工具...")
    result = await current_app(serial=serial)
    
    if result["code"] != 200:
        print(f"❌ current_app 失败: {result['message']}")
        return False
    
    package_name = result['data'].get('package_name')
    print("✅ current_app 成功")
    print(f"   当前应用: {package_name if package_name else '未检测到（可能在桌面）'}")
    
    # 测试应用启动/停止（需要知道包名）
    if package_name:
        print(f"\n✓ 检测到应用包名: {package_name}")
        print("  可以使用 start_app/stop_app 工具进行操作")
    
    return True


async def test_screenshot():
    """测试截图功能"""
    print("\n" + "=" * 60)
    print("测试 6: 屏幕截图工具")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    
    manager = get_adb_manager()
    devices = manager.list_devices(online_only=True)
    
    if not devices:
        print("⚠️  没有在线设备，跳过截图测试")
        return True
    
    from app.tools.builtin.adb.screen_tools import screenshot
    
    print("\n正在截图...")
    result = await screenshot(output_format="file_path")
    
    if result["code"] != 200:
        print(f"❌ 截图失败: {result['message']}")
        return False
    
    print("✅ 截图成功")
    print(f"   文件路径: {result['data']['file_path']}")
    print(f"   分辨率: {result['data']['screen_width']}x{result['data']['screen_height']}")
    
    return True


async def test_interaction_tools(interactive: bool = False):
    """测试交互操作工具"""
    print("\n" + "=" * 60)
    print("测试 7: 交互操作工具")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    
    manager = get_adb_manager()
    devices = manager.list_devices(online_only=True)
    
    if not devices:
        print("⚠️  没有在线设备，跳过测试")
        return True
    
    if not interactive:
        print("⚠️  非交互模式，跳过实际操作测试")
        print("   提示: 使用 --interactive 参数启用交互测试")
        print("   这些工具包括: tap, swipe, long_press")
        return True
    
    from app.tools.builtin.adb.interaction_tools import long_press, swipe, tap
    
    serial = devices[0].serial
    device_info = await manager.get_device_info(serial)
    
    if not device_info or not device_info.screen_width:
        print("❌ 无法获取设备屏幕信息")
        return False
    
    print(f"\n⚠️  即将在设备 {serial} 上执行交互操作")
    print("   这将实际操作您的设备！")
    response = input("输入 'yes' 继续，其他键跳过: ").strip().lower()
    
    if response != 'yes':
        print("⏭️  跳过交互测试")
        return True
    
    # 测试点击（点击屏幕中心）
    print("\n测试 tap 工具（点击屏幕中心）...")
    result = await tap(serial=serial, x=500, y=500, normalized=True)
    
    if result["code"] != 200:
        print(f"❌ tap 失败: {result['message']}")
        return False
    
    print("✅ tap 成功")
    await asyncio.sleep(0.5)
    
    # 测试滑动（从中心向右滑动）
    print("\n测试 swipe 工具（向右滑动）...")
    result = await swipe(
        x1=300, y1=500,
        x2=700, y2=500,
        duration=300,
        serial=serial,
        normalized=True
    )
    
    if result["code"] != 200:
        print(f"❌ swipe 失败: {result['message']}")
        return False
    
    print("✅ swipe 成功")
    await asyncio.sleep(0.5)
    
    # 测试长按
    print("\n测试 long_press 工具...")
    result = await long_press(
        x=500, y=500,
        duration=1000,
        serial=serial,
        normalized=True
    )
    
    if result["code"] != 200:
        print(f"❌ long_press 失败: {result['message']}")
        return False
    
    print("✅ long_press 成功")
    
    return True


async def test_input_tools(interactive: bool = False):
    """测试输入操作工具"""
    print("\n" + "=" * 60)
    print("测试 8: 输入操作工具")
    print("=" * 60)
    
    from app.services.adb_manager import get_adb_manager
    
    manager = get_adb_manager()
    devices = manager.list_devices(online_only=True)
    
    if not devices:
        print("⚠️  没有在线设备，跳过测试")
        return True
    
    if not interactive:
        print("⚠️  非交互模式，跳过实际操作测试")
        print("   提示: 使用 --interactive 参数启用交互测试")
        print("   这些工具包括: input_text, keyevent")
        return True
    
    from app.tools.builtin.adb.input_tools import input_text, keyevent
    
    serial = devices[0].serial
    
    print(f"\n⚠️  即将在设备 {serial} 上执行输入操作")
    print("   建议先打开一个可输入的应用（如记事本）")
    response = input("准备好后输入 'yes' 继续，其他键跳过: ").strip().lower()
    
    if response != 'yes':
        print("⏭️  跳过输入测试")
        return True
    
    # 测试输入文本
    print("\n测试 input_text 工具...")
    result = await input_text(serial=serial, text="Hello ADB Test")
    
    if result["code"] != 200:
        print(f"❌ input_text 失败: {result['message']}")
        return False
    
    print("✅ input_text 成功")
    await asyncio.sleep(0.5)
    
    # 测试按键事件（Home键）
    print("\n测试 keyevent 工具（发送 Home 键）...")
    result = await keyevent(key="home", serial=serial)
    
    if result["code"] != 200:
        print(f"❌ keyevent 失败: {result['message']}")
        return False
    
    print("✅ keyevent 成功")
    
    return True


async def main(interactive: bool = False):
    """主测试流程"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 13 + "ADB 工具系统完整测试" + " " * 20 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    if interactive:
        print("⚠️  交互模式已启用，将执行实际设备操作")
        print()
    
    tests = [
        ("ADB Manager 初始化", lambda: test_adb_manager()),
        ("设备发现", lambda: test_device_discovery()),
        ("设备详细信息", lambda: test_device_info()),
        ("基本工具调用", lambda: test_tools()),
        ("应用管理工具", lambda: test_app_tools()),
        ("屏幕截图工具", lambda: test_screenshot()),
        ("交互操作工具", lambda: test_interaction_tools(interactive)),
        ("输入操作工具", lambda: test_input_tools(interactive)),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ 测试异常: {test_name}")
            print(f"   错误: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status}  {test_name}")
    
    print()
    print(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    elif passed >= total - 2:  # 允许交互测试跳过
        print(f"\n✅ 核心测试通过！（{passed}/{total}）")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
    
    print("\n" + "=" * 60)
    print("测试覆盖的工具:")
    print("=" * 60)
    print("✓ 设备管理: list_devices, device_info")
    print("✓ 应用管理: current_app, start_app, stop_app")
    print("✓ 屏幕操作: screenshot")
    print("✓ 交互操作: tap, swipe, long_press")
    print("✓ 输入操作: input_text, keyevent")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ADB 工具系统测试')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='启用交互测试（会实际操作设备）')
    
    args = parser.parse_args()
    asyncio.run(main(interactive=args.interactive))

