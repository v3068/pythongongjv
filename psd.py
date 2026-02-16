"""
PSD转网页素材提取工具
功能：将PSD中所有图层自动导出为图片素材，记录精确位置信息，用于网页开发
"""

import os
import sys
import json
import argparse
import traceback
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

try:
    from psd_tools import PSDImage
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请安装依赖: pip install psd-tools pillow")
    sys.exit(1)


class LayerProcessor:
    """图层处理器 - 处理不同类型图层的导出"""

    def __init__(self, font_path=None):
        self.font_cache = {}
        self.default_font = self._find_system_font(font_path)

    def _find_system_font(self, custom_font_path):
        """查找字体文件"""
        # 优先使用用户指定的字体
        if custom_font_path and Path(custom_font_path).exists():
            return custom_font_path

        # 尝试查找系统字体
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",  # Windows黑体
            "C:/Windows/Fonts/msyh.ttc",    # Windows雅黑
            "/System/Library/Fonts/PingFang.ttc",  # macOS苹方
            "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",  # Linux
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

            # 获取文字属性
            bbox = layer.bbox
            width = max(bbox[2] - bbox[0], 1)
            height = max(bbox[3] - bbox[1], 1)

            # 获取字体大小，默认为12
            font_size = getattr(layer, 'size', 12)

            # 获取颜色，默认为黑色
            color = (0, 0, 0, 255)  # RGBA

            # 创建透明背景的图像
            image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)

            # 获取字体并绘制文字
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
            # 尝试获取PIL图像
            if hasattr(layer, 'topil'):
                image = layer.topil()
                if image:
                    return image

            return None

        except Exception as e:
            print(f"⚠️ 图层导出失败: {e}")
            return None


class PSDWebExtractor:
    """PSD网页素材提取器"""

    def __init__(self, psd_path, output_dir,
                 export_invisible=False,
                 expand_smart_objects=False,
                 font_path=None):
        """
        初始化提取器

        Args:
            psd_path: PSD文件路径
            output_dir: 输出目录
            export_invisible: 是否导出不可见图层
            expand_smart_objects: 是否展开智能对象
            font_path: 字体文件路径
        """
        self.psd_path = Path(psd_path)
        self.output_dir = Path(output_dir)
        self.export_invisible = export_invisible
        self.expand_smart_objects = expand_smart_objects

        # 验证文件
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

        # 获取所有图层
        self.all_layers = list(self.psd.descendants())

        print(f"✅ PSD加载成功")
        print(f"   文档尺寸: {self.psd.width} x {self.psd.height} 像素")
        print(f"   图层总数: {len(self.all_layers)}")

    def extract_all_layers(self):
        """提取所有图层"""
        print(f"\n🔧 开始提取图层...")

        results = []
        exported_count = 0
        skipped_count = 0
        layer_index = 0

        for i, layer in enumerate(self.all_layers):
            layer_name = getattr(layer, 'name', f"layer_{i}")

            # 检查可见性
            is_visible = layer.is_visible() if hasattr(layer, 'is_visible') else True
            if not self.export_invisible and not is_visible:
                skipped_count += 1
                continue

            try:
                # 判断图层类型
                layer_type = self._get_layer_type(layer)

                # 处理不同类型的图层
                if layer_type == 'text':
                    # 文字图层：栅格化为图片
                    image = self.processor.rasterize_text_layer(layer)
                    if image:
                        result = self._create_layer_result(layer, layer_index, image, 'text')
                        results.append(result)
                        layer_index += 1
                        exported_count += 1
                        print(f"  [{i}] ✓ 文字: {layer_name}")
                    else:
                        skipped_count += 1
                        print(f"  [{i}] - 跳过文字: {layer_name} (栅格化失败)")

                elif layer_type == 'smart_object':
                    # 智能对象
                    if self.expand_smart_objects:
                        # TODO: 展开智能对象
                        print(f"  [{i}] ! 智能对象: {layer_name} (暂不支持展开)")
                        skipped_count += 1
                    else:
                        # 整体导出
                        image = self.processor.export_layer_image(layer)
                        if image:
                            result = self._create_layer_result(layer, layer_index, image, 'smart_object')
                            results.append(result)
                            layer_index += 1
                            exported_count += 1
                            print(f"  [{i}] ✓ 智能对象: {layer_name}")
                        else:
                            skipped_count += 1
                            print(f"  [{i}] - 跳过智能对象: {layer_name}")

                elif layer_type == 'adjustment':
                    # 调整图层：跳过（不应用效果）
                    skipped_count += 1
                    print(f"  [{i}] - 跳过调整图层: {layer_name}")

                elif layer_type == 'pixel':
                    # 像素图层
                    image = self.processor.export_layer_image(layer)
                    if image:
                        result = self._create_layer_result(layer, layer_index, image, 'pixel')
                        results.append(result)
                        layer_index += 1
                        exported_count += 1
                        print(f"  [{i}] ✓ 像素: {layer_name}")
                    else:
                        skipped_count += 1
                        print(f"  [{i}] - 跳过像素: {layer_name}")

                else:
                    # 其他类型图层
                    image = self.processor.export_layer_image(layer)
                    if image:
                        result = self._create_layer_result(layer, layer_index, image, 'other')
                        results.append(result)
                        layer_index += 1
                        exported_count += 1
                        print(f"  [{i}] ✓ 其他: {layer_name}")
                    else:
                        skipped_count += 1
                        print(f"  [{i}] - 跳过: {layer_name}")

            except Exception as e:
                skipped_count += 1
                print(f"  [{i}] ✗ 错误: {layer_name} - {e}")

        print(f"\n📊 提取完成!")
        print(f"   成功导出: {exported_count} 个图层")
        print(f"   跳过: {skipped_count} 个图层")

        return results

    def _get_layer_type(self, layer):
        """获取图层类型"""
        # 文字图层
        if hasattr(layer, 'kind') and layer.kind == 'type':
            return 'text'

        # 智能对象
        if hasattr(layer, 'smart_object') and layer.smart_object:
            return 'smart_object'

        # 调整图层
        if hasattr(layer, 'kind') and 'adjustment' in str(layer.kind).lower():
            return 'adjustment'

        # 像素图层
        if hasattr(layer, 'has_pixels') and layer.has_pixels():
            return 'pixel'

        return 'other'

    def _create_layer_result(self, layer, index, image, layer_type):
        """创建图层结果"""
        # 获取图层信息
        bbox = layer.bbox
        x, y = bbox[0], bbox[1]
        width = max(bbox[2] - bbox[0], 1)
        height = max(bbox[3] - bbox[1], 1)

        # 图层名称
        layer_name = getattr(layer, 'name', f"layer_{index}")

        # 清理文件名
        clean_name = self._sanitize_filename(layer_name)

        # 生成文件名和路径
        filename = f"{index:03d}_{clean_name}.png"
        filepath = self.images_dir / filename
        relative_path = f"images/{filename}"

        # 保存图片
        try:
            # 确保图像是RGBA模式
            if image.mode != 'RGBA':
                if image.mode == 'RGB':
                    image = image.convert('RGBA')
                else:
                    # 转换为RGBA
                    image = image.convert('RGBA')

            # 保存为PNG
            image.save(filepath, 'PNG', optimize=True)
        except Exception as e:
            print(f"⚠️ 图片保存失败: {filename} - {e}")

        # 返回结果
        return {
            'index': index,
            'name': layer_name,
            'type': layer_type,
            'filename': filename,
            'relative_path': relative_path,
            'absolute_path': str(filepath.absolute()),
            'position': {
                'x': x,
                'y': y,
                'width': width,
                'height': height
            },
            'visibility': {
                'visible': layer.is_visible() if hasattr(layer, 'is_visible') else True,
                'exported': True  # 标记为已导出
            },
            'opacity': getattr(layer, 'opacity', 100),
            'blend_mode': str(getattr(layer, 'blend_mode', 'normal'))
        }

    def _sanitize_filename(self, name):
        """清理文件名"""
        import re
        # 移除非法字符
        clean = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 移除首尾空格和点
        clean = clean.strip().strip('.')
        # 限制长度
        return clean[:50] if len(clean) > 50 else clean

    def generate_metadata(self, results):
        """生成元数据文件"""
        if not results:
            print("⚠️ 没有导出任何图层，跳过元数据生成")
            return

        print(f"\n📝 生成元数据文件...")

        # 1. 生成JSON元数据
        json_data = {
            'metadata': {
                'source_psd': str(self.psd_path.absolute()),
                'document_size': {
                    'width': self.psd.width,
                    'height': self.psd.height
                },
                'export_time': datetime.now().isoformat(),
                'export_config': {
                    'export_invisible': self.export_invisible,
                    'expand_smart_objects': self.expand_smart_objects
                },
                'statistics': {
                    'total_layers': len(self.all_layers),
                    'exported_layers': len(results),
                    'images_dir': 'images/'
                }
            },
            'layers': results
        }

        json_path = self.output_dir / 'metadata.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"   ✅ JSON元数据: {json_path}")

        # 2. 生成文本摘要
        self._generate_text_summary(results, json_path)

        # 3. 生成CSV文件
        self._generate_csv_metadata(results)

        # 4. 生成HTML预览
        self._generate_html_preview(results)

        print("✅ 所有元数据文件生成完成")

    def _generate_text_summary(self, results, json_path):
        """生成文本摘要"""
        summary_path = self.output_dir / 'summary.txt'

        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("PSD网页素材提取报告\n")
            f.write("=" * 80 + "\n\n")

            f.write("📁 文件信息:\n")
            f.write("-" * 40 + "\n")
            f.write(f"PSD源文件: {self.psd_path.name}\n")
            f.write(f"完整路径: {self.psd_path.absolute()}\n")
            f.write(f"文档尺寸: {self.psd.width} x {self.psd.height} 像素\n")
            f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"输出目录: {self.output_dir.absolute()}\n")
            f.write(f"图片目录: {self.images_dir.relative_to(self.output_dir)}\n\n")

            f.write("⚙️ 导出配置:\n")
            f.write("-" * 40 + "\n")
            f.write(f"导出不可见图层: {'是' if self.export_invisible else '否'}\n")
            f.write(f"展开智能对象: {'是' if self.expand_smart_objects else '否'}\n\n")

            f.write("📊 统计信息:\n")
            f.write("-" * 40 + "\n")
            f.write(f"总图层数: {len(self.all_layers)}\n")
            f.write(f"成功导出: {len(results)}\n")
            f.write(f"图片目录: images/\n\n")

            f.write("📋 图层详情:\n")
            f.write("=" * 80 + "\n")

            for result in results:
                pos = result['position']
                visible_symbol = "👁️ " if not result['visibility']['visible'] else ""
                f.write(f"\n图层 #{result['index']}: {visible_symbol}{result['name']}\n")
                f.write(f"  类型: {result['type']}\n")
                f.write(f"  图片文件: {result['relative_path']}\n")
                f.write(f"  位置: X={pos['x']}, Y={pos['y']}\n")
                f.write(f"  尺寸: {pos['width']} x {pos['height']} 像素\n")
                f.write(f"  不透明度: {result['opacity']}%\n")
                f.write(f"  可见性: {'可见' if result['visibility']['visible'] else '隐藏'}\n")
                f.write(f"  混合模式: {result['blend_mode']}\n")
                f.write(f"  完整路径: {result['absolute_path']}\n")

        print(f"   ✅ 文本摘要: {summary_path}")

    def _generate_csv_metadata(self, results):
        """生成CSV元数据"""
        try:
            import csv

            csv_path = self.output_dir / 'metadata.csv'

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # 写入标题行
                writer.writerow([
                    '序号', '图层名称', '类型', '图片文件',
                    '相对路径', 'X位置', 'Y位置', '宽度', '高度',
                    '不透明度', '可见性', '混合模式'
                ])

                # 写入数据行
                for result in results:
                    pos = result['position']
                    writer.writerow([
                        result['index'],
                        result['name'],
                        result['type'],
                        result['filename'],
                        result['relative_path'],
                        pos['x'],
                        pos['y'],
                        pos['width'],
                        pos['height'],
                        result['opacity'],
                        '可见' if result['visibility']['visible'] else '隐藏',
                        result['blend_mode']
                    ])

            print(f"   ✅ CSV元数据: {csv_path}")

        except ImportError:
            print("   ⚠️ CSV模块不可用，跳过CSV生成")

    def _generate_html_preview(self, results):
        """生成HTML预览"""
        try:
            html_path = self.output_dir / 'preview.html'

            # 生成HTML内容
            html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PSD素材预览 - {self.psd_path.name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .header .subtitle {{
            font-size: 1.2em;
            opacity: 0.9;
            font-weight: 300;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            text-align: center;
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .layers-container {{
            padding: 30px;
        }}
        
        .layers-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 15px;
            border-bottom: 2px solid #eee;
        }}
        
        .layers-header h2 {{
            color: #333;
            font-size: 1.8em;
            font-weight: 300;
        }}
        
        .search-box {{
            padding: 10px 20px;
            border: 2px solid #667eea;
            border-radius: 25px;
            width: 300px;
            font-size: 1em;
            transition: all 0.3s ease;
        }}
        
        .search-box:focus {{
            outline: none;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
        }}
        
        .layers-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 25px;
            margin-top: 20px;
        }}
        
        .layer-card {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            border: 1px solid #eee;
        }}
        
        .layer-card:hover {{
            transform: translateY(-10px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        }}
        
        .layer-image {{
            width: 100%;
            height: 200px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        
        .layer-image img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            transition: transform 0.3s ease;
        }}
        
        .layer-card:hover .layer-image img {{
            transform: scale(1.05);
        }}
        
        .layer-info {{
            padding: 20px;
        }}
        
        .layer-name {{
            font-size: 1.2em;
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .layer-meta {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 0.9em;
        }}
        
        .layer-type {{
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 500;
        }}
        
        .layer-position {{
            color: #666;
            font-size: 0.9em;
            line-height: 1.4;
        }}
        
        .layer-size {{
            color: #888;
            font-size: 0.85em;
            margin-top: 5px;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            background: #f8f9fa;
            color: #666;
            border-top: 1px solid #eee;
        }}
        
        .export-time {{
            font-size: 0.9em;
            margin-top: 10px;
            color: #999;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            
            .layers-grid {{
                grid-template-columns: 1fr;
            }}
            
            .header {{
                padding: 30px 20px;
            }}
            
            .header h1 {{
                font-size: 2em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎨 PSD素材预览</h1>
            <div class="subtitle">{self.psd_path.name} - 网页素材提取</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(results)}</div>
                <div class="stat-label">导出图层</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{self.psd.width}×{self.psd.height}</div>
                <div class="stat-label">文档尺寸</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(self.all_layers)}</div>
                <div class="stat-label">总图层数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">images/</div>
                <div class="stat-label">图片目录</div>
            </div>
        </div>
        
        <div class="layers-container">
            <div class="layers-header">
                <h2>📁 导出素材 ({len(results)}个)</h2>
                <input type="text" class="search-box" placeholder="搜索图层..." onkeyup="searchLayers(this.value)">
            </div>
            
            <div class="layers-grid" id="layersGrid">
'''

            # 添加图层卡片
            for result in results:
                # 类型标签样式
                type_labels = {
                    'text': ('文字', '#4CAF50'),
                    'pixel': ('图片', '#2196F3'),
                    'smart_object': ('智能对象', '#FF9800'),
                    'other': ('其他', '#9C27B0')
                }

                type_label, type_color = type_labels.get(
                    result['type'],
                    (result['type'], '#607D8B')
                )

                # 图片路径
                img_src = f"images/{result['filename']}"

                html += f'''
                <div class="layer-card" data-name="{result['name'].lower()}" data-type="{result['type']}">
                    <div class="layer-image">
                        <img src="{img_src}" alt="{result['name']}" 
                             onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 font-size=%2220%22 fill=%22%23667eea%22>🖼️</text></svg>'">
                    </div>
                    <div class="layer-info">
                        <div class="layer-name">{result['name']}</div>
                        <div class="layer-meta">
                            <span class="layer-type" style="background: {type_color}">{type_label}</span>
                            <span style="color: #666;">#{result['index']:03d}</span>
                        </div>
                        <div class="layer-position">
                            <div>位置: ({result['position']['x']}, {result['position']['y']})</div>
                            <div class="layer-size">
                                {result['position']['width']} × {result['position']['height']}px
                            </div>
                        </div>
                    </div>
                </div>
'''

            # 结束HTML
            html += f'''
            </div>
        </div>
        
        <div class="footer">
            <div>🛠️ PSD网页素材提取工具</div>
            <div>导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            <div class="export-time">
                图片目录: <code>images/</code> | 
                数据文件: <code>metadata.json</code>, <code>metadata.csv</code>, <code>summary.txt</code>
            </div>
        </div>
    </div>
    
    <script>
        function searchLayers(searchTerm) {{
            const cards = document.querySelectorAll('.layer-card');
            const term = searchTerm.toLowerCase().trim();
            
            cards.forEach(card => {{
                const layerName = card.getAttribute('data-name').toLowerCase();
                const layerType = card.getAttribute('data-type').toLowerCase();
                
                if (term === '' || layerName.includes(term) || layerType.includes(term)) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
        
        // 点击图层卡片显示详细信息
        document.querySelectorAll('.layer-card').forEach(card => {{
            card.addEventListener('click', function() {{
                const img = this.querySelector('img');
                const name = this.querySelector('.layer-name').textContent;
                
                // 在新窗口中打开图片
                if (img.src) {{
                    window.open(img.src, '_blank');
                }}
            }});
        }});
    </script>
</body>
</html>
'''

            # 保存HTML文件
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)

            print(f"   ✅ HTML预览: {html_path}")

        except Exception as e:
            print(f"   ⚠️ HTML生成失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='PSD转网页素材提取工具 - 自动导出所有图层为网页素材',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 基本用法
  python psd_to_web.py design.psd ./output
  
  # 导出不可见图层
  python psd_to_web.py design.psd ./output --invisible
  
  # 指定字体文件
  python psd_to_web.py design.psd ./output --font "C:/Windows/Fonts/simhei.ttf"
  
  # 交互式模式
  python psd_to_web.py
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
        results = extractor.extract_all_layers()

        # 生成元数据文件
        if results:
            extractor.generate_metadata(results)

        # 输出总结
        print(f"\n{'='*60}")
        print("🎉 导出完成!")
        print(f"{'='*60}")
        print(f"📁 输出目录: {extractor.output_dir.absolute()}")
        print(f"🖼️  图片目录: {extractor.images_dir.relative_to(extractor.output_dir)}/")
        print(f"📄 元数据文件:")
        print(f"   • metadata.json - 完整JSON数据")
        print(f"   • metadata.csv - 表格格式数据")
        print(f"   • summary.txt - 文本摘要")
        print(f"   • preview.html - HTML预览")
        print(f"\n💡 提示: 打开 preview.html 查看素材预览")

        return 0

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        return 1


def interactive_mode():
    """交互式模式"""
    print("\n" + "="*60)
    print("      🎨 PSD转网页素材提取工具")
    print("="*60)

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

        export_invisible = input("是否导出不可见图层? (y/N): ").strip().lower() == 'y'

        # 询问字体文件
        print(f"\n🔤 字体设置:")
        print("-" * 40)
        print("注: 文字图层需要字体文件进行栅格化")

        font_path = None
        use_custom_font = input("是否指定字体文件? (y/N): ").strip().lower() == 'y'
        if use_custom_font:
            font_path = input("字体文件路径: ").strip()
            if font_path and not Path(font_path).exists():
                print(f"⚠️  字体文件不存在，将使用系统默认字体")
                font_path = None

        # 显示配置摘要
        print(f"\n{'='*60}")
        print("📋 配置摘要")
        print("="*60)
        print(f"PSD文件: {psd_path}")
        print(f"输出目录: {output_dir}")
        print(f"导出不可见图层: {'是' if export_invisible else '否'}")
        print(f"字体文件: {font_path or '系统默认'}")
        print("="*60)

        confirm = input("\n是否开始提取? (Y/n): ").strip().lower()
        if confirm == 'n':
            print("操作已取消")
            return 0

        # 创建提取器
        extractor = PSDWebExtractor(
            psd_path=psd_path,
            output_dir=output_dir,
            export_invisible=export_invisible,
            expand_smart_objects=False,  # 交互模式默认不展开智能对象
            font_path=font_path
        )

        # 提取所有图层
        results = extractor.extract_all_layers()

        # 生成元数据文件
        if results:
            extractor.generate_metadata(results)

        # 输出总结
        print(f"\n{'='*60}")
        print("🎉 导出完成!")
        print(f"{'='*60}")
        print(f"📁 输出目录: {extractor.output_dir.absolute()}")
        print(f"🖼️  图片目录: {extractor.images_dir.relative_to(extractor.output_dir)}/")
        print(f"\n💡 提示:")
        print(f"   1. 打开 preview.html 查看素材预览")
        print(f"   2. 图片素材在 images/ 目录中")
        print(f"   3. 位置信息在 metadata.json 中")

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




'''使用文档
PSD转网页素材提取工具 - 详细功能说明
一、工具核心目标
将PSD设计稿自动转换为网页开发所需的完整素材包，包括：

所有图层的图片文件

精确的位置和尺寸信息

网页开发友好的输出结构

二、主要功能模块详解
1. 智能图层识别与处理
python
LayerProcessor 类 - 专门处理不同类型图层的转换
文字图层处理：

自动识别PSD中的文字图层（layer.kind == 'type'）

智能栅格化：将文字转换为PNG图片

字体支持：使用系统字体或用户指定字体

保持样式：保留原始字体大小、颜色等属性

智能对象处理：

识别智能对象（layer.smart_object）

可选择整体导出或展开内部图层

保持智能对象的变换效果

像素图层处理：

直接使用layer.topil()方法导出

保持原始色彩和透明度

调整图层处理：

识别亮度/对比度、色相等调整图层

跳过应用效果（避免颜色失真问题）

2. 精确位置信息记录
python
# 记录每个图层的完整信息
{
    "name": "图层名称",          # 在PSD中的图层名称
    "position": {              # 精确位置和尺寸
        "x": 100,              # 左侧位置（像素）
        "y": 50,               # 顶部位置（像素）
        "width": 200,          # 宽度（像素）
        "height": 100          # 高度（像素）
    },
    "relative_path": "images/001_layer.png",  # 相对路径
    "type": "text/pixel/smart_object",        # 图层类型
    "visibility": {                           # 可见性信息
        "visible": True/False,
        "exported": True
    },
    "opacity": 100,            # 不透明度（0-100）
    "blend_mode": "normal"     # 混合模式
}
3. 自动化导出流程
python
PSDWebExtractor.extract_all_layers() 方法
处理流程：

text
加载PSD → 遍历所有图层 → 判断图层类型 → 导出为图片 → 记录位置信息
智能跳过：自动跳过空图层、无效图层

错误处理：单个图层导出失败不影响整体流程

进度显示：实时显示处理进度和结果

4. 多格式元数据输出
生成4种不同格式的元数据文件：

a) metadata.json - 完整结构化数据
json
{
    "metadata": {
        "source_psd": "文件路径",
        "document_size": {"width": 1920, "height": 1080},
        "export_time": "2024-01-15T10:30:00",
        "statistics": {
            "total_layers": 66,
            "exported_layers": 45,
            "images_dir": "images/"
        }
    },
    "layers": [/* 所有图层信息 */]
}
用途：前端开发直接读取，自动布局

b) metadata.csv - 表格数据
text
序号,图层名称,类型,图片文件,相对路径,X位置,Y位置,宽度,高度,不透明度,可见性,混合模式
0,背景,pixel,000_background.png,images/000_background.png,0,0,1920,1080,100,可见,normal
1,主标题,text,001_主标题.png,images/001_主标题.png,100,50,800,120,100,可见,normal
用途：导入Excel、Google Sheets进行数据分析

c) summary.txt - 文本报告
text
==================================================
PSD网页素材提取报告
==================================================

📁 文件信息:
----------------------------------------
PSD源文件: design.psd
文档尺寸: 1920 x 1080 像素
导出时间: 2024-01-15 10:30:00

📊 统计信息:
----------------------------------------
总图层数: 66
成功导出: 45
图片目录: images/

📋 图层详情:
==================================================
图层 #0: 背景
  类型: pixel
  图片文件: images/000_background.png
  位置: X=0, Y=0
  尺寸: 1920 x 1080 像素
  不透明度: 100%
  可见性: 可见
  混合模式: normal
用途：人工查阅、项目文档

d) preview.html - 可视化预览
响应式网页界面，美观易用

缩略图展示所有导出的图片

支持搜索过滤图层

点击缩略图查看原图

显示完整的图层信息

支持移动设备查看

5. 目录结构管理
text
输出目录/
├── images/                    # 所有图片素材（核心目录）
│   ├── 000_background.png    # 按序号命名，便于排序
│   ├── 001_logo.png
│   ├── 002_title_text.png    # 文字栅格化的图片
│   ├── 003_button.png
│   └── ...
├── metadata.json             # 完整数据（JSON格式）
├── metadata.csv              # 表格数据（CSV格式）
├── summary.txt               # 文本报告
└── preview.html              # 网页预览
设计特点：

images/目录集中存放所有图片

相对路径引用，便于项目迁移

按数字序号排序，保持原始层级顺序

6. 用户交互系统
支持两种使用模式：

a) 命令行模式（适合批量处理、自动化）
bash
# 基本用法
python psd_to_web.py design.psd ./output

# 导出不可见图层
python psd_to_web.py design.psd ./output --invisible

# 指定中文字体
python psd_to_web.py design.psd ./output --font "fonts/simhei.ttf"
b) 交互式模式（适合新手用户）
text
==================================================
      🎨 PSD转网页素材提取工具
==================================================

📁 请输入PSD文件路径:
----------------------------------------
PSD文件路径: [用户输入]

📂 输出目录设置:
----------------------------------------
输出目录 (按Enter使用默认: web_design): [用户输入]

⚙️ 导出配置:
----------------------------------------
是否导出不可见图层? (y/N): [用户输入]
...
7. 错误处理与日志系统
python
try:
    # 尝试处理图层
    image = processor.export_layer_image(layer)
    if image:
        # 成功处理
        print(f"  [{i}] ✓ 像素: {layer_name}")
    else:
        # 跳过无效图层
        print(f"  [{i}] - 跳过: {layer_name}")
except Exception as e:
    # 错误捕获和记录
    print(f"  [{i}] ✗ 错误: {layer_name} - {e}")
特点：

逐图层错误隔离：一个图层失败不影响其他

详细错误日志：显示具体错误信息

进度实时反馈：让用户了解处理状态

三、技术特性详解
1. 颜色保真处理
直接使用psd-tools的topil()方法，确保颜色准确性

不应用调整图层，避免颜色偏差

保持原始透明度（RGBA模式）

2. 文字渲染优化
python
# 文字栅格化流程
1. 获取文字内容、字体、大小、颜色
2. 创建透明背景画布
3. 使用指定字体绘制文字
4. 保存为PNG（保留透明度）
3. 文件名智能处理
python
def _sanitize_filename(self, name):
    # 移除非法字符：<>:"/\|?*
    # 限制长度：最长50字符
    # 保留中文和特殊符号（除上述非法字符外）
4. 路径管理
相对路径：images/001_layer.png（便于项目迁移）

绝对路径：/full/path/to/images/001_layer.png（便于程序访问）

跨平台兼容：使用pathlib处理路径

四、实际应用场景
场景1：网页开发素材准备
text
设计师提供PSD → 工具自动导出所有素材 → 前端使用图片+位置信息构建网页
场景2：设计稿审查
text
生成HTML预览 → 产品经理/客户在线查看所有素材 → 确认设计细节
场景3：版本管理
text
每次设计修改 → 重新导出素材包 → Git记录所有变化 → 追踪设计迭代
场景4：跨团队协作
text
设计师：只需提供PSD
前端：获得完整的素材包
产品：查看HTML预览确认效果
五、输出文件的实际用途
对于前端开发：
html
<!-- 使用导出的图片 -->
<img src="images/001_logo.png" 
     style="position: absolute; 
            left: 100px; 
            top: 50px; 
            width: 200px; 
            height: 100px;">

<!-- 直接从metadata.json读取位置信息 -->
<script>
    fetch('metadata.json')
        .then(response => response.json())
        .then(data => {
            data.layers.forEach(layer => {
                // 自动布局
                createElement(layer);
            });
        });
</script>
对于设计审查：
打开preview.html查看所有素材

点击缩略图查看大图

核对位置和尺寸信息

确认无误后交付开发

对于项目管理：
summary.txt作为交付文档

metadata.csv导入项目管理工具

完整的素材包作为交付物

六、工具优势总结
1. 自动化程度高
一键导出所有素材

自动处理文字栅格化

自动生成多种格式元数据

2. 信息完整精确
像素级位置精度

完整的图层属性信息

多种格式数据输出

3. 开发友好
清晰的目录结构

相对路径引用

可直接用于网页布局

4. 使用灵活
支持命令行和交互式两种模式

可配置导出选项

支持自定义字体

5. 安全可靠
不修改原始PSD文件

逐图层错误隔离

详细的错误日志

这个工具专门为解决"从PSD设计稿到网页实现"的工作流程而设计，极大提高了设计到开发的转换效率和准确性。
'''