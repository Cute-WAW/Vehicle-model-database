
import docx
import sys
from pathlib import Path

def read_docx(file_path):
    print(f"Reading {file_path}")
    try:
        doc = docx.Document(file_path)
        content = []
        for para in doc.paragraphs:
            if para.text.strip():
                content.append(para.text)
        return "\n".join(content)
    except Exception as e:
        return f"Error reading docx: {e}"

if __name__ == "__main__":
    file_path = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\doc\patent\二手车残值估价专利设计.docx"
    print(read_docx(file_path))
