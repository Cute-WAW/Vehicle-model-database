
import zipfile
import re
import sys
import os

def read_docx(file_path):
    """
    Read text from a .docx file by treating it as a zip archive and parsing document.xml.
    This avoids needing python-docx.
    """
    try:
        with zipfile.ZipFile(file_path) as zf:
            xml_content = zf.read('word/document.xml').decode('utf-8')
            
            # Simple regex to extract text within <w:t> tags
            # This handles the basic text content
            text_parts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml_content)
            
            # Join with spaces, but maybe try to respect paragraphs if possible
            # Paragraphs are usually in <w:p>
            
            # Better approach: Extract paragraphs
            full_text = []
            # Split by paragraph
            paragraphs = re.findall(r'<w:p.*?>(.*?)</w:p>', xml_content)
            for p in paragraphs:
                # Extract text in this paragraph
                texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', p)
                if texts:
                    full_text.append("".join(texts))
            
            return "\n".join(full_text)
            
    except Exception as e:
        return f"Error reading docx: {str(e)}"

if __name__ == "__main__":
    file_path = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\doc\patent\专利有辆一种基于混合模型的二手车价格预测方法.docx"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        
    print(f"Reading: {file_path}")
    content = read_docx(file_path)
    print("--- CONTENT START ---")
    print(content)
    print("--- CONTENT END ---")
