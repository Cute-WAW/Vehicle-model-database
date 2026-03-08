import os
import time
import zipfile
from pathlib import Path

# 项目根目录
SRC = Path(__file__).resolve().parent.parent
# 输出目录（项目根目录的上级）
DEST_DIR = SRC.parent

# 排除的目录/文件模式
EXCLUDES_DIRS = {
    'venv', '.venv', '.git', '.vscode', '.idea', '__pycache__', '.pytest_cache'
}

EXCLUDES_FILES = {
    '*.pyc', '*.pyo', '.DS_Store'
}

def zip_project():
    """打包项目，包含所有数据并保留 .env"""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    zip_name = f"vehicle_model_mapping_full_{ts}.zip"
    zip_path = DEST_DIR / zip_name
    
    print(f"正在打包项目到: {zip_path}")
    print(f"源目录: {SRC}")
    
    file_count = 0
    total_size = 0
    
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SRC):
            # 过滤排除的目录
            dirs[:] = [d for d in dirs if d not in EXCLUDES_DIRS]
            
            for name in files:
                # 过滤排除的文件模式
                if any(name.endswith(ext.replace('*', '')) for ext in EXCLUDES_FILES if '*' in ext):
                    continue
                if name in EXCLUDES_FILES:
                    continue
                
                file_path = Path(root) / name
                arcname = file_path.relative_to(SRC)
                
                # 写入 zip
                zf.write(file_path, arcname)
                file_count += 1
                total_size += file_path.stat().st_size
                
                if file_count % 100 == 0:
                    print(f"已处理 {file_count} 个文件...")
    
    print(f"\n打包完成！")
    print(f"文件总数: {file_count}")
    print(f"压缩包位置: {zip_path}")
    print(f"压缩包大小: {zip_path.stat().st_size / 1024 / 1024:.2f} MB")
    return zip_path

if __name__ == "__main__":
    zip_project()
