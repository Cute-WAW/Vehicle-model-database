import docx
from pathlib import Path

def extract_structure(file_path):
    """Extract headings and structure from docx"""
    doc = docx.Document(file_path)
    
    structure = []
    for para in doc.paragraphs:
        if para.style.name.startswith('Heading') or para.text.strip():
            level = 0
            if 'Heading 1' in para.style.name:
                level = 1
            elif 'Heading 2' in para.style.name:
                level = 2
            elif 'Heading 3' in para.style.name:
                level = 3
            
            text = para.text.strip()
            if text:
                structure.append({
                    'level': level,
                    'text': text[:200],  # Limit length
                    'style': para.style.name
                })
    
    return structure

if __name__ == "__main__":
    file_path = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\doc\patent\专利有辆一种基于混合模型的二手车价格预测方法.docx"
    
    try:
        structure = extract_structure(file_path)
        
        print("=== Document Structure ===\n")
        for i, item in enumerate(structure[:100]):  # First 100 items
            indent = "  " * item['level']
            print(f"{indent}[{item['style']}] {item['text']}")
            
    except Exception as e:
        print(f"Error: {e}")
