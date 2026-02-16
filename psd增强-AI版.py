"""
PSD转网页素材提取工具 - 增强版
功能：将PSD中所有图层自动导出为图片素材，生成详细的说明文档，便于AI理解并生成一致网页
"""
"""PSD转网页素材提取工具（AI友好版）使用说明

**一句话定位**：将PSD设计稿转换为AI能理解的格式，让AI自动生成完整网页。

### 🚀 快速开始
```bash
# 安装
pip install psd-tools pillow

# 使用（生成AI友好文档）
python psd_to_web_ai.py 设计图.psd ./输出目录
```

### 📁 输出文件说明
- **ai_summary.txt** - **核心文件**：复制内容给AI，说“根据这个生成网页”
- images/ - 所有图片素材
- metadata.json - 完整数据结构
- web_layout_guide.html - 布局实现示例

### 🤖 AI使用模板
将ai_summary.txt内容复制给AI，并说：
“请根据这个PSD说明生成完整的HTML网页，严格按照坐标定位，使用images/目录的图片，保持设计原样。”

### ⚙️ 常用参数
```bash
--invisible     # 导出隐藏图层
--font 字体路径 # 解决文字乱码（如C:/Windows/Fonts/simhei.ttf）
```

### ❗常见问题
- **文字乱码**：用--font指定中文字体
- **图层缺失**：加--invisible参数
- **AI位置不准**：提示词强调“严格按坐标"""
import os
import sys
import json
import argparse
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

try:
    from psd_tools import PSDImage
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请安装依赖: pip install psd-tools pillow")
    sys.exit(1)


class LayerProcessor:
    """图层处理器"""

    def __init__(self, font_path=None):
        self.font_cache = {}
        self.default_font = self._find_system_font(font_path)

    def _find_system_font(self, custom_font_path):
        """查找字体文件"""
        if custom_font_path and Path(custom_font_path).exists():
            return custom_font_path

        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
        ]

        for path in font_paths:
            if Path(path).exists():
                return path
        return None

    def get_font(self, size):
        """获取字体对象"""
        if not self.default_font:
            return None

        cache_key = f"{self.default_font}_{size}"
        if cache_key not in self.font_cache:
            try:
                self.font_cache[cache_key] = ImageFont.truetype(self.default_font, size)
            except Exception as e:
                print(f"⚠️ 字体加载失败: {e}")
                return None

        return self.font_cache[cache_key]

    def rasterize_text_layer(self, layer):
        """栅格化文字图层"""
        try:
            # 首先尝试使用psd-tools的内置方法
            if hasattr(layer, 'topil'):
                pil_image = layer.topil()
                if pil_image:
                    return pil_image

            # 备用方法：手动创建文字图像
            text = getattr(layer, 'text', '')
            if not text:
                return None

            bbox = layer.bbox
            width = max(bbox[2] - bbox[0], 1)
            height = max(bbox[3] - bbox[1], 1)

            font_size = getattr(layer, 'size', 12)
            color = (0, 0, 0, 255)

            image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)

            font = self.get_font(font_size)
            if font:
                draw.text((0, 0), text, fill=color, font=font)
            else:
                draw.text((0, 0), text, fill=color)

            return image

        except Exception as e:
            print(f"⚠️ 文字栅格化失败: {e}")
            return None

    def export_layer_image(self, layer):
        """导出图层图像"""
        try:
            if hasattr(layer, 'topil'):
                image = layer.topil()
                if image:
                    return image
            return None
        except Exception as e:
            print(f"⚠️ 图层导出失败: {e}")
            return None


class PSDWebExtractor:
    """PSD网页素材提取器 - 增强版"""

    def __init__(self, psd_path, output_dir,
                 export_invisible=False,
                 expand_smart_objects=False,
                 font_path=None):

        self.psd_path = Path(psd_path)
        self.output_dir = Path(output_dir)
        self.export_invisible = export_invisible
        self.expand_smart_objects = expand_smart_objects

        if not self.psd_path.exists():
            raise FileNotFoundError(f"PSD文件不存在: {psd_path}")

        # 创建输出目录结构
        self.images_dir = self.output_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # 初始化处理器
        self.processor = LayerProcessor(font_path)

        # 加载PSD文件
        print(f"📂 加载PSD文件: {self.psd_path.name}")
        self.psd = PSDImage.open(self.psd_path)

        # 收集所有图层
        self.all_layers = list(self.psd.descendants())

        # 收集PSD详细信息
        self.psd_info = self._collect_psd_info()

        print(f"✅ PSD加载成功")
        print(f"   文档尺寸: {self.psd.width} x {self.psd.height} 像素")
        print(f"   颜色模式: {self.psd_info['color_mode']}")
        print(f"   位深度: {self.psd_info['depth']}位")
        print(f"   图层总数: {len(self.all_layers)}")
        print(f"   可见图层: {self.psd_info['visible_layers']}")
        print(f"   文字图层: {self.psd_info['text_layers']}")
        print(f"   智能对象: {self.psd_info['smart_objects']}")

    def _collect_psd_info(self):
        """收集PSD文件的详细信息"""
        info = {
            'name': self.psd_path.name,
            'width': self.psd.width,
            'height': self.psd.height,
            'color_mode': str(getattr(self.psd, 'color_mode', '未知')),
            'depth': getattr(self.psd, 'depth', '未知'),
            'total_layers': len(self.all_layers),
            'visible_layers': 0,
            'text_layers': 0,
            'smart_objects': 0,
            'adjustment_layers': 0,
            'pixel_layers': 0,
            'shape_layers': 0,
            'layer_groups': 0
        }

        # 统计不同类型图层
        for layer in self.all_layers:
            if hasattr(layer, 'is_visible') and layer.is_visible():
                info['visible_layers'] += 1

            # 检查图层类型
            if hasattr(layer, 'kind'):
                if layer.kind == 'type':
                    info['text_layers'] += 1
                elif layer.kind == 'shape':
                    info['shape_layers'] += 1
                elif 'adjustment' in str(layer.kind).lower():
                    info['adjustment_layers'] += 1

            if hasattr(layer, 'smart_object') and layer.smart_object:
                info['smart_objects'] += 1

            if hasattr(layer, 'is_group') and layer.is_group:
                info['layer_groups'] += 1

            if hasattr(layer, 'has_pixels') and layer.has_pixels():
                info['pixel_layers'] += 1

        return info

    def extract_all_layers(self):
        """提取所有图层"""
        print(f"\n🔧 开始提取图层...")

        results = []
        layer_stats = {
            'total': 0,
            'exported': 0,
            'text_exported': 0,
            'pixel_exported': 0,
            'smart_exported': 0,
            'other_exported': 0,
            'skipped': 0
        }

        for i, layer in enumerate(self.all_layers):
            layer_stats['total'] += 1
            layer_name = getattr(layer, 'name', f"layer_{i}")

            # 检查可见性
            is_visible = layer.is_visible() if hasattr(layer, 'is_visible') else True
            if not self.export_invisible and not is_visible:
                layer_stats['skipped'] += 1
                continue

            try:
                layer_type = self._get_layer_type(layer)
                image = None
                result = None

                if layer_type == 'text':
                    image = self.processor.rasterize_text_layer(layer)
                    if image:
                        result = self._create_layer_result(layer, len(results), image, 'text')
                        layer_stats['text_exported'] += 1

                elif layer_type == 'smart_object':
                    if not self.expand_smart_objects:
                        image = self.processor.export_layer_image(layer)
                        if image:
                            result = self._create_layer_result(layer, len(results), image, 'smart_object')
                            layer_stats['smart_exported'] += 1

                elif layer_type == 'pixel':
                    image = self.processor.export_layer_image(layer)
                    if image:
                        result = self._create_layer_result(layer, len(results), image, 'pixel')
                        layer_stats['pixel_exported'] += 1

                else:
                    # 尝试导出其他类型图层
                    image = self.processor.export_layer_image(layer)
                    if image:
                        result = self._create_layer_result(layer, len(results), image, 'other')
                        layer_stats['other_exported'] += 1

                if result:
                    results.append(result)
                    layer_stats['exported'] += 1
                    symbol = "✓" if is_visible else "👁️"
                    print(f"  [{i}] {symbol} {layer_type}: {layer_name}")
                else:
                    layer_stats['skipped'] += 1
                    symbol = "-" if is_visible else "👁️-"
                    print(f"  [{i}] {symbol} 跳过: {layer_name}")

            except Exception as e:
                layer_stats['skipped'] += 1
                print(f"  [{i}] ✗ 错误: {layer_name} - {e}")

        print(f"\n📊 提取完成!")
        print(f"   成功导出: {layer_stats['exported']} 个图层")
        print(f"   文字图层: {layer_stats['text_exported']}")
        print(f"   像素图层: {layer_stats['pixel_exported']}")
        print(f"   智能对象: {layer_stats['smart_exported']}")
        print(f"   其他图层: {layer_stats['other_exported']}")
        print(f"   跳过: {layer_stats['skipped']} 个图层")

        return results, layer_stats

    def _get_layer_type(self, layer):
        """获取图层类型"""
        if hasattr(layer, 'kind') and layer.kind == 'type':
            return 'text'
        if hasattr(layer, 'smart_object') and layer.smart_object:
            return 'smart_object'
        if hasattr(layer, 'kind') and 'adjustment' in str(layer.kind).lower():
            return 'adjustment'
        if hasattr(layer, 'has_pixels') and layer.has_pixels():
            return 'pixel'
        return 'other'

    def _create_layer_result(self, layer, index, image, layer_type):
        """创建图层结果"""
        bbox = layer.bbox
        x, y = bbox[0], bbox[1]
        width = max(bbox[2] - bbox[0], 1)
        height = max(bbox[3] - bbox[1], 1)

        layer_name = getattr(layer, 'name', f"layer_{index}")
        clean_name = self._sanitize_filename(layer_name)

        filename = f"{index:03d}_{clean_name}.png"
        filepath = self.images_dir / filename
        relative_path = f"images/{filename}"

        try:
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            image.save(filepath, 'PNG', optimize=True)
        except Exception as e:
            print(f"⚠️ 图片保存失败: {filename} - {e}")

        # 获取图层详细属性
        opacity = getattr(layer, 'opacity', 100)
        blend_mode = str(getattr(layer, 'blend_mode', 'normal'))
        is_visible = layer.is_visible() if hasattr(layer, 'is_visible') else True

        # 对于文字图层，收集更多信息
        text_info = {}
        if layer_type == 'text':
            text = getattr(layer, 'text', '')
            text_info = {
                'text_content': text,
                'font_size': getattr(layer, 'size', '未知'),
                'color': str(getattr(layer, 'color', '未知')),
                'alignment': getattr(layer, 'alignment', '未知')
            }

        return {
            'index': index,
            'name': layer_name,
            'type': layer_type,
            'text_info': text_info if layer_type == 'text' else {},
            'filename': filename,
            'relative_path': relative_path,
            'absolute_path': str(filepath.absolute()),
            'position': {'x': x, 'y': y, 'width': width, 'height': height},
            'visibility': {'visible': is_visible, 'exported': True},
            'opacity': opacity,
            'blend_mode': blend_mode,
            'layer_bbox': {
                'left': bbox[0], 'top': bbox[1],
                'right': bbox[2], 'bottom': bbox[3]
            }
        }

    def _sanitize_filename(self, name):
        """清理文件名"""
        import re
        clean = re.sub(r'[<>:"/\\|?*]', '_', name)
        clean = clean.strip().strip('.')
        return clean[:50] if len(clean) > 50 else clean

    def generate_metadata(self, results, layer_stats):
        """生成元数据文件 - 增强版，添加AI友好说明"""
        if not results:
            print("⚠️ 没有导出任何图层，跳过元数据生成")
            return

        print(f"\n📝 生成元数据文件...")

        # 1. 生成详细的JSON元数据
        json_data = {
            'psd_documentation': {
                'file_info': {
                    'name': self.psd_info['name'],
                    'dimensions': {
                        'width': self.psd_info['width'],
                        'height': self.psd_info['height'],
                        'aspect_ratio': self.psd_info['width'] / self.psd_info['height']
                    },
                    'color_mode': self.psd_info['color_mode'],
                    'bit_depth': self.psd_info['depth']
                },
                'layer_statistics': {
                    'total_layers': self.psd_info['total_layers'],
                    'visible_layers': self.psd_info['visible_layers'],
                    'text_layers': self.psd_info['text_layers'],
                    'smart_objects': self.psd_info['smart_objects'],
                    'adjustment_layers': self.psd_info['adjustment_layers'],
                    'pixel_layers': self.psd_info['pixel_layers'],
                    'shape_layers': self.psd_info['shape_layers'],
                    'layer_groups': self.psd_info['layer_groups']
                },
                'export_statistics': {
                    'exported_layers': len(results),
                    'text_layers_exported': layer_stats['text_exported'],
                    'pixel_layers_exported': layer_stats['pixel_exported'],
                    'smart_objects_exported': layer_stats['smart_exported'],
                    'other_layers_exported': layer_stats['other_exported'],
                    'skipped_layers': layer_stats['skipped']
                },
                'export_config': {
                    'export_invisible': self.export_invisible,
                    'expand_smart_objects': self.expand_smart_objects,
                    'export_time': datetime.now().isoformat()
                },
                'output_structure': {
                    'root_directory': str(self.output_dir.absolute()),
                    'images_directory': 'images/',
                    'relative_paths_used': True,
                    'file_naming_convention': '###_layer_name.png'
                }
            },
            'layers': results
        }

        json_path = self.output_dir / 'metadata.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"   ✅ JSON元数据: {json_path}")

        # 2. 生成AI友好的详细文本说明
        self._generate_ai_friendly_summary(results, layer_stats)

        # 3. 生成CSV文件
        self._generate_csv_metadata(results)

        # 4. 生成HTML预览
        self._generate_html_preview(results)

        # 5. 生成网页布局指南
        self._generate_web_layout_guide(results)

        print("✅ 所有元数据文件生成完成")

    def _generate_ai_friendly_summary(self, results, layer_stats):
        """生成AI友好的详细文本说明"""
        summary_path = self.output_dir / 'ai_summary.txt'

        with open(summary_path, 'w', encoding='utf-8') as f:
            #AI提示词

            # 在 _generate_ai_friendly_summary 方法的开头添加

            f.write("# 🎯 AI网页生成任务说明\n\n")
            f.write("## 任务目标\n")
            f.write("请根据以下PSD设计稿的详细说明，生成一个**与原始设计图完全一致**的HTML网页。\n\n")
            f.write("## 核心要求\n\n")
            f.write("### 1. 精确还原\n")
            f.write("- **尺寸精确**: 严格按照说明中的`设计尺寸`设置容器宽度和高度\n")
            f.write("- **位置精确**: 每个图层必须按照说明中的`位置坐标`进行绝对定位\n")
            f.write("- **大小精确**: 每个图层的`宽度`和`高度`必须与说明完全一致\n")
            f.write("- **层级精确**: 严格按照`层级(Z-index)`顺序排列，数值越大越靠上\n\n")
            f.write("### 2. 图片资源\n")
            f.write("- **图片路径**: 所有图片都存放在`images/`目录下\n")
            f.write("- **引用方式**: 使用相对路径，例如 `<img src=\"images/001_logo.png\">`\n")
            f.write("- **图片格式**: 所有图片都是PNG格式，已保留透明通道\n\n")
            f.write("### 3. 布局方式\n")
            f.write("- **容器设置**:\n")
            f.write("```css\n")
            f.write(".container {\n")
            f.write("    position: relative;\n")
            f.write("    width: [设计宽度]px;\n")
            f.write("    height: [设计高度]px;\n")
            f.write("    margin: 0 auto;\n")
            f.write("}\n")
            f.write("```\n")
            f.write("- **图层定位**: 所有图层使用 `position: absolute`\n")
            f.write("- **背景处理**: 序号最小的图层通常是背景，应置于最底层\n\n")
            f.write("### 4. 响应式处理\n")
            f.write("- 在移动端保持设计稿比例\n")
            f.write("- 使用 `max-width: 100%` 和 `height: auto` 确保图片响应式\n")
            f.write("- 大屏居中显示，两侧留白\n\n")
            f.write("### 5. 特殊元素处理\n\n")
            f.write("#### 文字图层\n")
            f.write("- 文字已转换为图片，直接使用 `<img>` 标签\n")
            f.write("- 保留原始文字内容在 `alt` 属性中\n\n")
            f.write("#### 隐藏图层\n")
            f.write("- 如果图层标记为`隐藏`且有👁️符号，表示在PSD中隐藏但已导出\n")
            f.write("- 默认保持隐藏（`display: none`），除非特别说明需要显示\n\n")
            f.write("### 6. 代码规范\n\n")
            f.write("#### HTML结构\n")
            f.write("```html\n")
            f.write("<!DOCTYPE html>\n")
            f.write("<html lang=\"zh-CN\">\n")
            f.write("<head>\n")
            f.write("    <meta charset=\"UTF-8\">\n")
            f.write("    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n")
            f.write("    <title>[设计稿名称]</title>\n")
            f.write("    <link rel=\"stylesheet\" href=\"style.css\">\n")
            f.write("</head>\n")
            f.write("<body>\n")
            f.write("    <div class=\"design-container\">\n")
            f.write("        <!-- 按z-index顺序排列图层 -->\n")
            f.write("    </div>\n")
            f.write("</body>\n")
            f.write("</html>\n")
            f.write("```\n\n")
            f.write("#### CSS规范\n")
            f.write("```css\n")
            f.write("* {\n")
            f.write("    margin: 0;\n")
            f.write("    padding: 0;\n")
            f.write("    box-sizing: border-box;\n")
            f.write("}\n\n")
            f.write("body {\n")
            f.write("    min-height: 100vh;\n")
            f.write("    display: flex;\n")
            f.write("    justify-content: center;\n")
            f.write("    align-items: center;\n")
            f.write("    background: #f5f5f5;\n")
            f.write("}\n\n")
            f.write(".design-container {\n")
            f.write("    position: relative;\n")
            f.write("    width: [设计宽度]px;\n")
            f.write("    height: [设计高度]px;\n")
            f.write("    box-shadow: 0 10px 30px rgba(0,0,0,0.1);\n")
            f.write("}\n\n")
            f.write("/* 每个图层的样式 */\n")
            f.write(".layer-序号 {\n")
            f.write("    position: absolute;\n")
            f.write("    left: Xpx;\n")
            f.write("    top: Ypx;\n")
            f.write("    width: Wpx;\n")
            f.write("    height: Hpx;\n")
            f.write("    z-index: 序号;\n")
            f.write("    opacity: 不透明度/100;\n")
            f.write("}\n")
            f.write("```\n\n")
            f.write("## 输出要求\n\n")
            f.write("请提供以下三个文件：\n\n")
            f.write("请提供以下一个文件：\n\n")
            f.write("1. **index.html** - 包含完整的HTML结构、CSS样式和内联JavaScript（将所有代码集成到一个文件中）\n\n")
            f.write("## 检查清单（生成后请确认）\n\n")
            f.write("- [ ] 容器尺寸是否与设计稿一致？\n")
            f.write("- [ ] 所有图片路径是否正确（`images/`目录）？\n")
            f.write("- [ ] 每个图层的X/Y坐标是否准确？\n")
            f.write("- [ ] 每个图层的宽高是否准确？\n")
            f.write("- [ ] 图层顺序是否正确（z-index）？\n")
            f.write("- [ ] 透明度是否正确设置？\n")
            f.write("- [ ] 隐藏图层是否默认隐藏？\n")
            f.write("- [ ] 在移动端预览是否正常？\n\n")
            f.write("## 额外说明\n")
            f.write("- 不要添加任何额外的设计元素\n")
            f.write("- 保持设计稿的原汁原味\n")
            f.write("- 如果发现矛盾信息，优先遵循图层详细信息中的坐标\n\n")
            f.write("---\n")
            f.write("**开始分析以下PSD设计稿数据：**\n\n")

            # 第一部分：PSD文件详细说明
            f.write("# PSD文件详细说明\n")
            f.write("=" * 80 + "\n\n")

            f.write("## 1. 文件基本信息\n")
            f.write(f"- **文件名**: {self.psd_info['name']}\n")
            f.write(f"- **设计尺寸**: {self.psd_info['width']} × {self.psd_info['height']} 像素\n")
            f.write(f"- **宽高比**: {self.psd_info['width'] / self.psd_info['height']:.2f}\n")
            f.write(f"- **颜色模式**: {self.psd_info['color_mode']}\n")
            f.write(f"- **位深度**: {self.psd_info['depth']}位\n\n")

            # 第二部分：图层统计
            f.write("## 2. 图层统计分析\n")
            f.write(f"- **总图层数**: {self.psd_info['total_layers']}\n")
            f.write(f"- **可见图层**: {self.psd_info['visible_layers']}\n")
            f.write(f"- **文字图层**: {self.psd_info['text_layers']}\n")
            f.write(f"- **智能对象**: {self.psd_info['smart_objects']}\n")
            f.write(f"- **调整图层**: {self.psd_info['adjustment_layers']}\n")
            f.write(f"- **形状图层**: {self.psd_info['shape_layers']}\n")
            f.write(f"- **图层组**: {self.psd_info['layer_groups']}\n\n")

            # 第三部分：导出统计
            f.write("## 3. 导出结果\n")
            f.write(f"- **成功导出**: {len(results)} 个图层\n")
            f.write(f"- **文字图层导出**: {layer_stats['text_exported']}\n")
            f.write(f"- **像素图层导出**: {layer_stats['pixel_exported']}\n")
            f.write(f"- **智能对象导出**: {layer_stats['smart_exported']}\n")
            f.write(f"- **其他图层导出**: {layer_stats['other_exported']}\n")
            f.write(f"- **跳过图层**: {layer_stats['skipped']}\n\n")

            # 第四部分：目录结构说明
            f.write("## 4. 输出目录结构\n")
            f.write("```\n")
            f.write(f"{self.output_dir.name}/\n")
            f.write("├── images/                    # 所有图片素材\n")
            f.write("│   ├── 000_layer_name.png    # 命名规则: 序号_图层名.png\n")
            f.write("│   ├── 001_another_layer.png\n")
            f.write("│   └── ...\n")
            f.write("├── metadata.json             # 完整结构化数据\n")
            f.write("├── ai_summary.txt            # 本文档 - AI友好说明\n")
            f.write("├── metadata.csv              # 表格格式数据\n")
            f.write("├── web_layout_guide.html     # 网页布局参考\n")
            f.write("└── preview.html              # 素材预览页面\n")
            f.write("```\n\n")

            # 第五部分：网页布局说明
            f.write("## 5. 网页布局说明\n")
            f.write("### 布局类型分析\n")
            f.write("根据图层位置分析，此设计稿使用以下布局方式：\n")
            f.write("- **绝对定位**: 所有图层都有精确的X/Y坐标\n")
            f.write("- **层次结构**: 图层按导出顺序排列，序号越小层级越低\n")
            f.write("- **响应式基准**: 基于 {self.psd_info['width']}px 宽度设计\n\n")

            f.write("### 布局建议\n")
            f.write("```html\n")
            f.write("<!-- 建议的HTML结构 -->\n")
            f.write(
                "<div class=\"design-container\" style=\"position: relative; width: {self.psd_info['width']}px; height: {self.psd_info['height']}px;\">\n")

            # 添加图层示例
            if results:
                f.write("    <!-- 背景图层 -->\n")
                f.write(f"    <img src=\"{results[0]['relative_path']}\" \n")
                f.write(
                    f"         style=\"position: absolute; left: {results[0]['position']['x']}px; top: {results[0]['position']['y']}px; z-index: 1;\">\n")
                f.write("\n")
                f.write("    <!-- 文字内容 -->\n")
                f.write(
                    "    <div class=\"text-content\" style=\"position: absolute; left: Xpx; top: Ypx; z-index: 10;\">\n")
                f.write("        <!-- 文字已转换为图片 -->\n")
                f.write("    </div>\n")
            f.write("</div>\n")
            f.write("```\n\n")

            # 第六部分：图层详细信息
            f.write("## 6. 图层详细信息\n")
            f.write("=" * 80 + "\n\n")

            for result in results:
                pos = result['position']
                visible_symbol = "👁️ " if not result['visibility']['visible'] else ""

                f.write(f"### 图层 #{result['index']}: {visible_symbol}{result['name']}\n")
                f.write(f"- **类型**: {result['type']}\n")

                # 如果是文字图层，显示文字内容
                if result['type'] == 'text' and result.get('text_info', {}).get('text_content'):
                    f.write(f"- **文字内容**: \"{result['text_info']['text_content']}\"\n")
                    if result['text_info'].get('font_size'):
                        f.write(f"- **字体大小**: {result['text_info']['font_size']}\n")
                    if result['text_info'].get('color'):
                        f.write(f"- **文字颜色**: {result['text_info']['color']}\n")

                # ✅ 修改这里：使用相对路径而不是绝对路径
                f.write(f"- **图片文件**: `{result['relative_path']}`\n")
                f.write(f"- **位置坐标**: ({pos['x']}px, {pos['y']}px)\n")
                f.write(f"- **尺寸大小**: {pos['width']}px × {pos['height']}px\n")
                f.write(f"- **不透明度**: {result['opacity']}%\n")
                f.write(f"- **可见性**: {'可见' if result['visibility']['visible'] else '隐藏'}\n")
                f.write(f"- **混合模式**: {result['blend_mode']}\n")
                f.write(f"- **层级(Z-index)**: {result['index']} (数值越大层级越高)\n")

                # CSS代码示例
                f.write(f"\n**CSS定位代码**:\n")
                f.write("```css\n")
                f.write(f".layer-{result['index']} {{\n")
                f.write(f"    position: absolute;\n")
                f.write(f"    left: {pos['x']}px;\n")
                f.write(f"    top: {pos['y']}px;\n")
                f.write(f"    width: {pos['width']}px;\n")
                f.write(f"    height: {pos['height']}px;\n")
                f.write(f"    z-index: {result['index']};\n")
                f.write(f"    opacity: {result['opacity'] / 100:.2f};\n")
                f.write("}\n")
                f.write("```\n\n")

                # HTML使用示例
                f.write("**HTML使用示例**:\n")
                f.write("```html\n")
                if result['type'] == 'text':
                    f.write(f"<!-- 文字已转换为图片 -->\n")
                # ✅ 修改这里：使用相对路径而不是绝对路径
                f.write(f"<img src=\"{result['relative_path']}\" \n")
                f.write(f"     alt=\"{result['name']}\" \n")
                f.write(f"     class=\"layer-{result['index']}\">\n")
                f.write("```\n\n")
                f.write("---\n\n")

        print(f"   ✅ AI友好说明: {summary_path}")

    def _generate_csv_metadata(self, results):
        """生成CSV元数据"""
        try:
            import csv

            csv_path = self.output_dir / 'metadata.csv'

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                writer.writerow(['序号', '图层名称', '类型', '文字内容', '图片文件',
                                 '相对路径', 'X位置', 'Y位置', '宽度', '高度',
                                 '不透明度', '可见性', '混合模式', '层级'])

                for result in results:
                    pos = result['position']
                    text_content = result.get('text_info', {}).get('text_content', '')

                    writer.writerow([
                        result['index'],
                        result['name'],
                        result['type'],
                        text_content,
                        result['filename'],
                        result['relative_path'],
                        pos['x'],
                        pos['y'],
                        pos['width'],
                        pos['height'],
                        result['opacity'],
                        '可见' if result['visibility']['visible'] else '隐藏',
                        result['blend_mode'],
                        result['index']
                    ])

            print(f"   ✅ CSV元数据: {csv_path}")

        except ImportError:
            print("   ⚠️ CSV模块不可用，跳过CSV生成")

    def _generate_html_preview(self, results):
        """生成HTML预览"""
        try:
            html_path = self.output_dir / 'preview.html'

            html_content = '''
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>PSD素材预览</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                    .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
                    .header { text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; margin-bottom: 20px; }
                    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }
                    .stat-card { background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; border-left: 4px solid #667eea; }
                    .stat-value { font-size: 1.5em; font-weight: bold; color: #333; }
                    .layers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; }
                    .layer-card { border: 1px solid #ddd; border-radius: 5px; padding: 15px; background: white; transition: transform 0.2s; }
                    .layer-card:hover { transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                    .layer-image { width: 100%; height: 150px; object-fit: contain; background: #f0f0f0; border-radius: 3px; margin-bottom: 10px; }
                    .layer-info { margin-top: 10px; }
                    .layer-name { font-weight: bold; margin-bottom: 5px; }
                    .layer-position { font-size: 12px; color: #666; }
                    .type-badge { display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 11px; margin-right: 5px; }
                    .type-text { background: #d4edda; color: #155724; }
                    .type-pixel { background: #d1ecf1; color: #0c5460; }
                    .type-smart { background: #fff3cd; color: #856404; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎨 PSD素材预览</h1>
                        <p>''' + f'{self.psd_info["name"]} - {self.psd_info["width"]}×{self.psd_info["height"]}px' + '''</p>
                    </div>

                    <div class="stats">
                        <div class="stat-card">
                            <div class="stat-value">''' + f'{len(results)}' + '''</div>
                            <div>导出图层</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">''' + f'{self.psd_info["width"]}×{self.psd_info["height"]}' + '''</div>
                            <div>设计尺寸</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">''' + f'{self.psd_info["total_layers"]}' + '''</div>
                            <div>总图层数</div>
                        </div>
                    </div>

                    <h2>📁 导出素材预览</h2>
                    <div class="layers-grid">
            '''

            for result in results:
                type_class = f"type-{result['type']}"
                type_label = {
                    'text': '文字',
                    'pixel': '图片',
                    'smart_object': '智能对象',
                    'other': '其他'
                }.get(result['type'], result['type'])

                html_content += f'''
                        <div class="layer-card">
                            <img src="{result['relative_path']}" alt="{result['name']}" class="layer-image"
                                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🖼️</text></svg>'">
                            <div class="layer-info">
                                <div class="layer-name">{result['name']}</div>
                                <span class="type-badge type-{result['type']}">{type_label}</span>
                                <div class="layer-position">
                                    位置: ({result['position']['x']}, {result['position']['y']})<br>
                                    尺寸: {result['position']['width']}×{result['position']['height']}px
                                </div>
                            </div>
                        </div>
                '''

            html_content += '''
                    </div>
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                        生成时间: ''' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''<br>
                        图片目录: <code>images/</code><br>
                        详细说明: <a href="ai_summary.txt">ai_summary.txt</a>
                    </div>
                </div>
            </body>
            </html>
            '''

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"   ✅ HTML预览: {html_path}")

        except Exception as e:
            print(f"   ⚠️ HTML生成失败: {e}")

    def _generate_web_layout_guide(self, results):
        """生成网页布局指南"""
        try:
            guide_path = self.output_dir / 'web_layout_guide.html'

            guide_content = f'''
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>网页布局指南 - {self.psd_info['name']}</title>
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background: #f8f9fa; padding: 20px; }}
                    .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
                    .header {{ text-align: center; margin-bottom: 40px; padding-bottom: 20px; border-bottom: 2px solid #eee; }}
                    .header h1 {{ color: #2c3e50; font-size: 2.5em; margin-bottom: 10px; }}
                    .header .subtitle {{ color: #7f8c8d; font-size: 1.2em; }}
                    .design-preview {{ position: relative; width: {self.psd_info['width']}px; height: {self.psd_info['height']}px; margin: 0 auto 40px; border: 2px dashed #ddd; background: #f9f9f9; overflow: hidden; }}
                    .layer-box {{ position: absolute; border: 1px solid rgba(102, 126, 234, 0.5); background: rgba(102, 126, 234, 0.1); pointer-events: none; }}
                    .layer-label {{ position: absolute; top: -25px; left: 0; background: #667eea; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; white-space: nowrap; }}
                    .code-section {{ background: #2d3a4b; border-radius: 8px; padding: 20px; margin: 20px 0; overflow-x: auto; }}
                    .code-section h3 {{ color: #42b983; margin-bottom: 15px; }}
                    pre {{ color: #abb2bf; font-family: 'Consolas', monospace; font-size: 14px; line-height: 1.5; }}
                    .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 30px 0; }}
                    .info-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; }}
                    .info-card h3 {{ color: #2c3e50; margin-bottom: 10px; }}
                    .info-card p {{ color: #666; }}
                    .footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #7f8c8d; font-size: 14px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🌐 网页布局实现指南</h1>
                        <div class="subtitle">基于 {self.psd_info['name']} 设计稿</div>
                    </div>

                    <div class="info-grid">
                        <div class="info-card">
                            <h3>📏 设计规格</h3>
                            <p>• 宽度: {self.psd_info['width']}px</p>
                            <p>• 高度: {self.psd_info['height']}px</p>
                            <p>• 图层数量: {len(results)}个</p>
                            <p>• 布局类型: 绝对定位</p>
                        </div>
                        <div class="info-card">
                            <h3>📁 文件结构</h3>
                            <p>• 图片目录: <code>images/</code></p>
                            <p>• 图片总数: {len(results)}个</p>
                            <p>• 命名规则: 序号_图层名.png</p>
                            <p>• 数据文件: <code>metadata.json</code></p>
                        </div>
                        <div class="info-card">
                            <h3>⚙️ 技术实现</h3>
                            <p>• 定位方式: position: absolute</p>
                            <p>• 层级控制: z-index</p>
                            <p>• 尺寸单位: 像素(px)</p>
                            <p>• 响应式: 固定尺寸设计</p>
                        </div>
                    </div>

                    <h2>🎨 设计稿布局预览</h2>
                    <div class="design-preview">
            '''

            # 添加图层预览框
            for result in results[:10]:  # 最多显示10个图层预览
                pos = result['position']
                if pos['width'] > 10 and pos['height'] > 10:  # 只显示足够大的图层
                    guide_content += f'''
                        <div class="layer-box" style="
                            left: {pos['x']}px;
                            top: {pos['y']}px;
                            width: {pos['width']}px;
                            height: {pos['height']}px;
                            z-index: {result['index']};
                        ">
                            <div class="layer-label">#{result['index']} {result['name'][:15]}{'...' if len(result['name']) > 15 else ''}</div>
                        </div>
                    '''

            guide_content += f'''
                    </div>

                    <h2>💻 HTML实现代码</h2>
                    <div class="code-section">
                        <h3>基础HTML结构</h3>
                        <pre><code>
&lt;!-- 基于 {self.psd_info['name']} 设计稿的HTML结构 --&gt;
&lt;!DOCTYPE html&gt;
&lt;html lang="zh-CN"&gt;
&lt;head&gt;
    &lt;meta charset="UTF-8"&gt;
    &lt;meta name="viewport" content="width=device-width, initial-scale=1.0"&gt;
    &lt;title&gt;{self.psd_info['name'].replace('.psd', '')} - 网页实现&lt;/title&gt;
    &lt;style&gt;
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: Arial, sans-serif;
            background: #f5f5f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}

        .design-container {{
            position: relative;
            width: {self.psd_info['width']}px;
            height: {self.psd_info['height']}px;
            background: white;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        /* 图层样式 - 根据metadata.json自动生成 */
                        '''

            # 添加图层CSS
            for result in results[:5]:  # 示例前5个图层
                pos = result['position']
                guide_content += f'''
        /* 图层 #{result['index']}: {result['name']} */
        .layer-{result['index']} {{
            position: absolute;
            left: {pos['x']}px;
            top: {pos['y']}px;
            width: {pos['width']}px;
            height: {pos['height']}px;
            z-index: {result['index']};
            opacity: {result['opacity'] / 100:.2f};
        }}
                '''

            guide_content += '''
    &lt;/style&gt;
&lt;/head&gt;
&lt;body&gt;
    &lt;div class="design-container"&gt;
        '''

            # 添加图层HTML
            for result in results[:5]:  # 示例前5个图层
                guide_content += f'''
        &lt;!-- {result['name']} --&gt;
        &lt;img src="{result['relative_path']}" 
             alt="{result['name']}" 
             class="layer-{result['index']}"&gt;
                '''

            guide_content += '''
    &lt;/div&gt;
&lt;/body&gt;
&lt;/html&gt;
                        </code></pre>
                    </div>

                    <div class="info-card">
                        <h3>📋 实现步骤</h3>
                        <p>1. 复制<code>images/</code>目录到您的项目</p>
                        <p>2. 根据<code>metadata.json</code>中的位置信息设置CSS</p>
                        <p>3. 使用绝对定位(position: absolute)布局所有元素</p>
                        <p>4. 按z-index顺序排列元素（序号越大层级越高）</p>
                        <p>5. 如需响应式，添加媒体查询调整容器尺寸</p>
                    </div>

                    <div class="footer">
                        <p>🛠️ 生成时间: ''' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''</p>
                        <p>📄 详细说明: <a href="ai_summary.txt">ai_summary.txt</a> | 完整数据: <a href="metadata.json">metadata.json</a></p>
                    </div>
                </div>

                <script>
                    // 简单的交互效果
                    document.querySelectorAll('.layer-box').forEach(box => {{
                        box.addEventListener('mouseenter', function() {{
                            this.style.background = 'rgba(102, 126, 234, 0.3)';
                            this.style.borderColor = '#667eea';
                        }});
                        box.addEventListener('mouseleave', function() {{
                            this.style.background = 'rgba(102, 126, 234, 0.1)';
                            this.style.borderColor = 'rgba(102, 126, 234, 0.5)';
                        }});
                    }});
                </script>
            </body>
            </html>
            '''

            with open(guide_path, 'w', encoding='utf-8') as f:
                f.write(guide_content)

            print(f"   ✅ 网页布局指南: {guide_path}")

        except Exception as e:
            print(f"   ⚠️ 网页布局指南生成失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='PSD转网页素材提取工具 - AI友好版',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 基本用法 - 生成AI友好的说明文档
  python psd_to_web_ai.py design.psd ./output

  # 导出不可见图层
  python psd_to_web_ai.py design.psd ./output --invisible

  # 指定中文字体（避免文字乱码）
  python psd_to_web_ai.py design.psd ./output --font "fonts/simhei.ttf"
        '''
    )

    parser.add_argument('input', nargs='?', help='PSD文件路径')
    parser.add_argument('output', nargs='?', default=None,
                        help='输出目录 (默认: web_<文件名>)')

    # 功能选项
    parser.add_argument('--invisible', action='store_true',
                        help='导出不可见图层')
    parser.add_argument('--expand-smart', action='store_true',
                        help='展开智能对象 (实验性功能)')
    parser.add_argument('--font', default=None,
                        help='字体文件路径 (用于文字渲染)')

    args = parser.parse_args()

    # 如果没有提供输入文件，进入交互模式
    if not args.input:
        return interactive_mode()

    # 验证输入文件
    if not Path(args.input).exists():
        print(f"❌ 错误: 文件不存在 - {args.input}")
        return 1

    # 设置输出目录
    if not args.output:
        input_stem = Path(args.input).stem
        args.output = f"web_{input_stem}"

    try:
        # 创建提取器
        extractor = PSDWebExtractor(
            psd_path=args.input,
            output_dir=args.output,
            export_invisible=args.invisible,
            expand_smart_objects=args.expand_smart,
            font_path=args.font
        )

        # 提取所有图层
        results, layer_stats = extractor.extract_all_layers()

        # 生成元数据文件
        if results:
            extractor.generate_metadata(results, layer_stats)

        # 输出总结
        print(f"\n{'=' * 60}")
        print("🎉 AI友好版导出完成!")
        print(f"{'=' * 60}")
        print(f"📁 输出目录: {extractor.output_dir.absolute()}")
        print(f"🖼️  图片目录: {extractor.images_dir.relative_to(extractor.output_dir)}/")
        print(f"\n📄 生成的文件:")
        print(f"   • ai_summary.txt       - AI友好详细说明（可提供给AI生成网页）")
        print(f"   • metadata.json        - 完整结构化数据")
        print(f"   • web_layout_guide.html - 网页布局实现指南")
        print(f"   • preview.html         - 素材预览页面")
        print(f"   • metadata.csv         - 表格格式数据")
        print(f"\n💡 使用方法:")
        print(f"   1. 将 ai_summary.txt 提供给AI（如ChatGPT、Claude等）")
        print(f"   2. AI会根据详细说明生成与PSD一致的HTML/CSS代码")
        print(f"   3. 参考 web_layout_guide.html 中的实现示例")

        return 0

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        return 1


def interactive_mode():
    """交互式模式"""
    print("\n" + "=" * 60)
    print("      🤖 PSD转网页素材提取工具 - AI友好版")
    print("=" * 60)

    try:
        # 获取PSD文件路径
        print("\n📁 请输入PSD文件路径:")
        print("-" * 40)

        while True:
            psd_path = input("PSD文件路径: ").strip()
            if not psd_path:
                print("❌ 请输入有效路径")
                continue

            psd_path_obj = Path(psd_path)
            if not psd_path_obj.exists():
                print(f"❌ 文件不存在: {psd_path}")
                continue

            if psd_path_obj.suffix.lower() != '.psd':
                print(f"❌ 文件格式必须是PSD: {psd_path}")
                continue

            print(f"✅ 文件有效: {psd_path_obj.name}")
            break

        # 获取输出目录
        print(f"\n📂 输出目录设置:")
        print("-" * 40)

        psd_stem = Path(psd_path).stem
        default_dir = f"web_{psd_stem}"

        output_dir = input(f"输出目录 (按Enter使用默认: {default_dir}): ").strip()
        if not output_dir:
            output_dir = default_dir

        # 询问是否导出不可见图层
        print(f"\n⚙️  导出配置:")
        print("-" * 40)
        print("说明: 导出不可见图层会增加素材数量")
        export_invisible = input("是否导出不可见图层? (y/N): ").strip().lower() == 'y'

        # 询问字体文件
        print(f"\n🔤 字体设置:")
        print("-" * 40)
        print("重要: 文字图层需要字体文件进行栅格化")
        print("如果文字显示为方框，请指定中文字体路径")

        font_path = None
        use_custom_font = input("是否指定字体文件? (y/N): ").strip().lower() == 'y'
        if use_custom_font:
            font_path = input("字体文件路径: ").strip()
            if font_path and not Path(font_path).exists():
                print(f"⚠️  字体文件不存在，将使用系统默认字体")
                font_path = None

        # 显示配置摘要
        print(f"\n{'=' * 60}")
        print("🤖 AI友好版配置摘要")
        print("=" * 60)
        print(f"PSD文件: {psd_path}")
        print(f"输出目录: {output_dir}")
        print(f"导出不可见图层: {'是' if export_invisible else '否'}")
        print(f"字体文件: {font_path or '系统默认'}")
        print(f"生成文件: ai_summary.txt, web_layout_guide.html等")
        print("=" * 60)
        print("\n说明: 生成的ai_summary.txt可直接提供给AI生成网页代码")

        confirm = input("\n是否开始提取? (Y/n): ").strip().lower()
        if confirm == 'n':
            print("操作已取消")
            return 0

        # 创建提取器
        extractor = PSDWebExtractor(
            psd_path=psd_path,
            output_dir=output_dir,
            export_invisible=export_invisible,
            expand_smart_objects=False,
            font_path=font_path
        )

        # 提取所有图层
        results, layer_stats = extractor.extract_all_layers()

        # 生成元数据文件
        if results:
            extractor.generate_metadata(results, layer_stats)

        # 输出总结
        print(f"\n{'=' * 60}")
        print("🎉 AI友好版导出完成!")
        print(f"{'=' * 60}")
        print(f"📁 输出目录: {extractor.output_dir.absolute()}")
        print(f"\n📄 关键文件:")
        print(f"   1. ai_summary.txt - 可直接复制给AI生成网页代码")
        print(f"   2. web_layout_guide.html - 网页布局实现示例")
        print(f"   3. preview.html - 素材预览")

        # 显示下一步操作
        print(f"\n💡 下一步操作:")
        print(f"   将 ai_summary.txt 内容复制到AI对话中，并提示:")
        print(f"   \"根据这个PSD文件说明，生成一个HTML网页，还原设计稿\"")

        # 询问是否打开目录
        if sys.platform == 'win32':
            open_dir = input("\n是否打开输出目录? (y/N): ").strip().lower()
            if open_dir == 'y':
                os.startfile(str(extractor.output_dir.absolute()))

        return 0

    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # 检查依赖
    try:
        from psd_tools import PSDImage
        from PIL import Image
    except ImportError:
        print("❌ 缺少必要依赖")
        print("请运行: pip install psd-tools pillow")
        sys.exit(1)

    sys.exit(main())