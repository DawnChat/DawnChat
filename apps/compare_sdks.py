#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import re
import sys

# ==========================================
# DawnChat 双端 SDK 依赖校验脚本 (Python 稳如老狗版)
# ==========================================

ANDROID_DIR = "./dawnchat-android"
IOS_DIR = "./dawnchat-ios"

# 颜色定义
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m' # No Color

def print_color(color, msg):
    print(f"{color}{msg}{NC}")

def get_deps(project_dir, ignore_pkg):
    """提取工程目录下的依赖并返回 Set 集合"""
    if not os.path.isdir(project_dir):
        print_color(RED, f"❌ 找不到工程目录: {project_dir}，请确认路径。")
        sys.exit(1)

    try:
        # 使用 subprocess 在指定目录执行 bun list，完全避免了 cd 的目录污染
        result = subprocess.run(
            ["bun", "list"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        print_color(RED, f"❌ 在 {project_dir} 提取依赖失败，请确保安装了 bun: {e}")
        sys.exit(1)

    deps = set()
    # 正则表达式：精准匹配 @scope/package@version 或者 package@version
    pattern = re.compile(r'(@[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+|[a-zA-Z0-9_.-]+)@([0-9a-zA-Z_.-]+)')

    for line in result.stdout.splitlines():
        match = pattern.search(line)
        if match:
            full_pkg = match.group(0) # 例如: @capacitor/core@8.2.0
            pkg_name = match.group(1) # 例如: @capacitor/core
            
            # 过滤掉各端专属的插件 (如 @capacitor/android)
            if pkg_name != ignore_pkg:
                deps.add(full_pkg)
                
    return deps

def main():
    print("🔍 开始提取 DawnChat 移动端底座依赖...")

    # 提取 Android 依赖，并忽略 @capacitor/android
    android_deps = get_deps(ANDROID_DIR, "@capacitor/android")
    # 提取 iOS 依赖，并忽略 @capacitor/ios
    ios_deps = get_deps(IOS_DIR, "@capacitor/ios")

    print("\n📊 对比结果：")

    # Python 集合求差集，优雅且绝对不会出错
    only_in_android = android_deps - ios_deps
    only_in_ios = ios_deps - android_deps

    if not only_in_android and not only_in_ios:
        print_color(GREEN, "✅ 恭喜！Android 和 iOS 宿主的 SDK 底座（含版本号）已完全对齐！")
    else:
        if only_in_android:
            print_color(YELLOW, "🤖 仅在 Android (缺失于 iOS) 的插件或版本:")
            for dep in sorted(only_in_android):
                print(f"  - {dep}")
        
        if only_in_ios:
            print_color(RED, "🍎 仅在 iOS (缺失于 Android) 的插件或版本:")
            for dep in sorted(only_in_ios):
                print(f"  - {dep}")
                
        print_color(YELLOW, "\n⚠️ 警告：请尽快同步双端依赖（bun add / bun remove），否则 AI 沙箱在跨端时将抛出异常！")

if __name__ == "__main__":
    main()