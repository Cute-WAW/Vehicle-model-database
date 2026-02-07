import os

def load_repair_results(file_path):
    repair_map = {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_csv = None
    current_match = None
    current_score = None
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith('【输入】'):
            # Extract CSV part (last part after |)
            parts = line.split('|')
            if len(parts) > 1:
                current_csv = parts[-1].strip()
            else:
                current_csv = None
        
        elif line.startswith('【匹配】'):
            current_match = lines[i] # Keep original line with newline
            if "无匹配结果" in line:
                current_csv = None # Ignore this block
        
        elif line.startswith('【得分】'):
            current_score = lines[i] # Keep original line with newline
            
            # End of block, store if valid
            if current_csv and current_match and "无匹配结果" not in current_match:
                repair_map[current_csv] = {
                    'match': current_match,
                    'score': current_score
                }
            
            # Reset
            current_csv = None
            current_match = None
            current_score = None
            
        i += 1
        
    return repair_map

def merge_results(full_path, repair_map):
    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    new_lines = []
    current_csv_in_full = None
    skip_next_match_score = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if stripped.startswith('【输入】'):
            new_lines.append(line)
            # Extract CSV part
            parts = stripped.split('|')
            if len(parts) > 1:
                current_csv_in_full = parts[-1].strip()
                if current_csv_in_full in repair_map:
                    skip_next_match_score = True
                else:
                    skip_next_match_score = False
            else:
                skip_next_match_score = False
                
        elif stripped.startswith('【匹配】'):
            if skip_next_match_score and current_csv_in_full:
                # Replace with repair result
                new_lines.append(repair_map[current_csv_in_full]['match'])
            else:
                new_lines.append(line)
                
        elif stripped.startswith('【得分】'):
            if skip_next_match_score and current_csv_in_full:
                # Replace with repair score
                new_lines.append(repair_map[current_csv_in_full]['score'])
                # Reset
                skip_next_match_score = False
                current_csv_in_full = None
            else:
                new_lines.append(line)
        
        else:
            new_lines.append(line)
            
        i += 1
        
    return new_lines

def main():
    repair_file = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\output\cheyipai_more_match_result_repair.txt"
    full_file = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\output\cheyipai_more_match_result_full.txt"
    
    print(f"Loading repair results from {repair_file}...")
    repair_map = load_repair_results(repair_file)
    print(f"Found {len(repair_map)} successful repairs.")
    
    print(f"Merging into {full_file}...")
    new_content = merge_results(full_file, repair_map)
    
    # Backup original
    backup_file = full_file + ".bak"
    if not os.path.exists(backup_file):
        import shutil
        shutil.copy(full_file, backup_file)
        print(f"Backed up original file to {backup_file}")
    
    with open(full_file, 'w', encoding='utf-8') as f:
        f.writelines(new_content)
        
    print("Merge complete.")

if __name__ == "__main__":
    main()
