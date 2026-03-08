
import sys
import os
from pathlib import Path

# Add src to path
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
src_dir = project_root / 'src'
sys.path.insert(0, str(src_dir))

from residual_predictor_step5 import ResidualPredictor

def generate_report():
    print("Initializing predictor...")
    predictor = ResidualPredictor()
    
    test_cases = [
        {
            "name": "标准案例 (Standard Case)",
            "input": {
                "vehicle_full_name": "奥迪 A4L 2017款 2.0T 自动 40TFSI时尚型",
                "brand_series": "奥迪-A4L",
                "years": 6.5,
                "grade": "中",
                "city": "北京",
                "mileage": 8.0
            }
        },
        {
            "name": "新能源案例 (NEV Case)",
            "input": {
                "vehicle_full_name": "特斯拉 Model 3 2020款 标准续航升级版",
                "brand_series": "特斯拉-Model 3",
                "years": 3.5,
                "grade": "优",
                "city": "上海",
                "mileage": 4.5
            }
        },
        {
            "name": "大龄车辆 (Old Car)",
            "input": {
                "vehicle_full_name": "大众 帕萨特 2013款 1.8T 自动 尊栄版",
                "brand_series": "大众-帕萨特",
                "years": 11.0,
                "grade": "中",
                "city": "成都",
                "mileage": 15.0
            }
        }
    ]
    
    report_content = []
    
    for case in test_cases:
        print(f"Running case: {case['name']}")
        i = case['input']
        result = predictor.predict(
            vehicle_full_name=i['vehicle_full_name'],
            brand_series=i['brand_series'],
            years=i['years'],
            grade=i['grade'],
            city=i['city'],
            mileage=i['mileage']
        )
        
        md = f"### {case['name']}\n\n"
        md += f"- **输入**: {i['vehicle_full_name']} | {i['years']}年 | {i['mileage']}万公里 | {i['city']} | {i['grade']}\n"
        
        if result.success:
            md += f"- **预测结果**: {result.predicted_price} 万元\n"
            md += f"- **新车价格**: {result.new_price} 万元 (残值率: {result.residual_rate:.1%})\n"
            
            if result.debug:
                d = result.debug
                md += f"- **算法路径**: \n"
                md += f"    1. **新车价推断**: {result.new_price}\n"
                md += f"    2. **模型预测**: {d.model_prediction}万 (模型: `{d.model_name}`, Type: `{d.model_type}`, R2: {d.model_r2:.2f})\n"
                md += f"    3. **相似车检索**: 找到 {len(d.to_dict()['similar_vehicles'])} 辆, 均价 {d.similar_avg_price}万\n"
                md += f"    4. **最终微调**: 采用 `{d.adjustment_method}` 方法, 调整幅度 {d.adjustment_delta}万\n"
        else:
            md += f"- **预测失败**: {result.error_message}\n"
            
        md += "\n"
        report_content.append(md)
        
    return "\n".join(report_content)

if __name__ == "__main__":
    try:
        content = generate_report()
        output_file = project_root / 'model_test_results.md'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Report generated at {output_file}")
    except Exception as e:
        print(f"Error: {e}")
