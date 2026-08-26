#!/bin/bash
# ============================================
# Build script for PyScreen Viewer APK
# 在Linux x86_64机器上运行此脚本构建ARM32 APK
# ============================================

set -e

echo "======================================"
echo " PyScreen Viewer - APK Build Script"
echo "======================================"

# 检查Python和pip
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到python3"
    exit 1
fi

# 安装buildozer
echo "安装buildozer..."
pip3 install -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com buildozer cython

# 安装系统依赖 (Ubuntu/Debian)
if command -v apt-get &> /dev/null; then
    echo "安装系统依赖..."
    sudo apt-get update
    sudo apt-get install -y \
        build-essential \
        git \
        python3-pip \
        autoconf \
        libtool \
        pkg-config \
        zlib1g-dev \
        libncurses5-dev \
        libncursesw5-dev \
        libtinfo5 \
        cmake \
        libffi-dev \
        libssl-dev \
        automake \
        zip \
        unzip \
        openjdk-17-jdk
fi

# 进入android目录
cd "$(dirname "$0")"

# 确保icon存在
if [ ! -f "icon.png" ]; then
    echo "创建默认icon..."
    python3 -c "
from PIL import Image, ImageDraw
img = Image.new('RGBA', (512, 512), (30, 144, 255, 255))
draw = ImageDraw.Draw(img)
draw.rectangle([100, 100, 412, 412], fill=(255, 255, 255, 255))
draw.rectangle([150, 150, 362, 362], fill=(30, 144, 255, 255))
draw.text((200, 230), 'PS', fill=(255, 255, 255, 255))
img.save('icon.png')
"
fi

echo ""
echo "开始构建ARM32 APK..."
echo "这可能需要较长时间（首次构建需要下载Android SDK/NDK）"
echo ""

# 构建debug APK (ARM32)
buildozer android debug -v

echo ""
echo "======================================"
echo " 构建完成!"
echo " APK位置: bin/*.apk"
echo "======================================"
echo ""
echo "安装到设备: adb install bin/pyscreen-*.apk"
