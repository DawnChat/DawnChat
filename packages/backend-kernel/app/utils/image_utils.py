"""
图像处理辅助函数
"""

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Tuple, Union

from PIL import Image

from app.utils.logger import get_logger

logger = get_logger("utils.image")


def compress_image_max_side(
    image_path: Union[str, Path],
    max_side: int = 1080,
    quality: int = 80
) -> Tuple[bytes, Dict[str, Any]]:
    """
    将图片最长边等比压缩到 max_side，不足则不缩放。
    
    Args:
        image_path: 图片路径
        max_side: 最长边目标长度
        quality: JPEG 质量 (1-100)
        
    Returns:
        (compressed_bytes, meta)
        meta 包含原/新尺寸、大小及是否缩放
    """
    path = Path(image_path)
    quality = max(1, min(quality, 100))

    with Image.open(path) as img:
        original_format = img.format or "PNG"
        original_width, original_height = img.size
        original_bytes = path.read_bytes()
        longest_side = max(original_width, original_height)

        # 不需要缩放
        if longest_side <= max_side:
            return original_bytes, {
                "was_resized": False,
                "max_side": max_side,
                "quality": quality,
                "original_format": original_format,
                "output_format": original_format,
                "original_size": [original_width, original_height],
                "resized_size": [original_width, original_height],
                "original_size_bytes": len(original_bytes),
                "compressed_size_bytes": len(original_bytes),
            }

        # 计算新尺寸
        scale = max_side / float(longest_side)
        new_width = max(1, int(original_width * scale))
        new_height = max(1, int(original_height * scale))
        logger.info(f"压缩前图片尺寸: {original_width}x{original_height}, 压缩后尺寸: {new_width}x{new_height}")

        # 确保可保存为 JPEG
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        resized.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True
        )
        compressed_bytes = buffer.getvalue()

        meta = {
            "was_resized": True,
            "max_side": max_side,
            "quality": quality,
            "original_format": original_format,
            "output_format": "JPEG",
            "original_size": [original_width, original_height],
            "resized_size": [new_width, new_height],
            "original_size_bytes": len(original_bytes),
            "compressed_size_bytes": len(compressed_bytes),
        }

        return compressed_bytes, meta







