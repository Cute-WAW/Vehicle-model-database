"""
项目打包脚本

打包当前项目为 zip 文件，排除虚拟环境、数据目录等大型目录。
输出文件: car_price_mapping_YYYYMMDD_HHMMSS.zip
"""

import os
import time
from pathlib import Path
import zipfile

# 项目根目录
SRC = Path(__file__).resolve().parent.parent
# 输出目录（项目根目录的上级）
DEST_DIR = SRC.parent

# 排除的目录/文件
EXCLUDES = {
    # 虚拟环境
    SRC / "venv",
    SRC / ".venv",
    # 运行时目录
    SRC / "logs",
    SRC / "run",
    SRC / "log",
    # 数据目录（大型数据文件）
    SRC / "data",
    SRC / "experiment",
    # 开发目录
    SRC / ".git",
    SRC / ".vscode",
    SRC / ".idea",
    SRC / "__pycache__",
    # Other large outputs - REMOVED exclusion for output to allow specific files
    # SRC / "output" ,
}


def should_exclude(p: Path) -> bool:
    """检查路径是否应该被排除"""
    # 强制包含指定的数据文件
    if p.name == "residual_value_data_for_build_model.csv":
        return False

    # 检查是否在排除列表中
    for ex in EXCLUDES:
        try:
            if p.is_relative_to(ex):
                return True
        except Exception:
            if str(p).startswith(str(ex)):
                return True
    
    # 排除 __pycache__ 目录（任意层级）
    if "__pycache__" in p.parts:
        return True
    
    # 排除 .pyc 文件
    if p.suffix == ".pyc":
        return True
    
    # 排除大型 CSV 文件（超过 10MB）
    if p.suffix == ".csv":
        try:
            if p.stat().st_size > 10 * 1024 * 1024:  # 10MB
                return True
        except Exception:
            pass
    
    return False


def zip_project() -> Path:
    """打包项目"""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    zip_path = DEST_DIR / f"car_price_evaluation_{ts}.zip"
    
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SRC):
            root_path = Path(root)
            # 过滤掉需要排除的子目录
            dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]
            for name in files:
                file_path = root_path / name
                if should_exclude(file_path):
                    continue
                arcname = file_path.relative_to(SRC)
                zf.write(file_path, arcname)
                file_count += 1
    
    print(f"已打包 {file_count} 个文件")
    return zip_path


if __name__ == "__main__":
    print("开始打包项目...")
    print(f"源目录: {SRC}")
    print(f"输出目录: {DEST_DIR}")
    print(f"排除目录: data, experiment, logs, run, __pycache__, .git 等")
    p = zip_project()
    print(f"打包完成: {p}")
    print(f"文件大小: {p.stat().st_size / 1024 / 1024:.2f} MB")