#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
C2B2C价格预测测试程序

用法：
    python c2b2c_price_model_test_predictor.py                    # 使用默认值测试
    python c2b2c_price_model_test_predictor.py 2.24               # 指定b2BPrices.b.mid值
    python c2b2c_price_model_test_predictor.py --interactive      # 交互模式

作者：Antigravity
日期：2025-12-31
"""

import os
import sys
import json
import argparse

# 添加模型目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(os.path.dirname(script_dir))  # 车型库映射目录
model_dir = os.path.join(base_dir, 'price_model', 'c2b2c_model')
sys.path.insert(0, model_dir)

from predictor import C2B2CPricePredictor


def test_prediction(b2b_b_mid: float, predictor: C2B2CPricePredictor) -> dict:
    """
    测试价格预测
    
    Args:
        b2b_b_mid: 车商B级车况中间价格
        predictor: 预测器实例
    
    Returns:
        dict: 预测结果
    """
    result = predictor.predict(b2b_b_mid)
    return result


def validate_result(result: dict) -> bool:
    """
    验证预测结果是否满足业务约束
    
    约束:
    1. c2BPrices < b2BPrices < b2CPrices
    2. a > b > c (对于同一交易类型)
    3. low < mid < up (对于同一条件)
    """
    errors = []
    
    # 检查每个条件下的 low < mid < up
    for price_type in ['b2BPrices', 'b2CPrices', 'c2BPrices']:
        for condition in ['a', 'b', 'c']:
            low = float(result[price_type][condition]['low'])
            mid = float(result[price_type][condition]['mid'])
            up = float(result[price_type][condition]['up'])
            
            if not (low < mid < up):
                errors.append(f"{price_type}.{condition}: low({low}) < mid({mid}) < up({up}) 不满足")
    
    # 检查 a > b > c
    for price_type in ['b2BPrices', 'b2CPrices', 'c2BPrices']:
        a_mid = float(result[price_type]['a']['mid'])
        b_mid = float(result[price_type]['b']['mid'])
        c_mid = float(result[price_type]['c']['mid'])
        
        if not (a_mid > b_mid > c_mid):
            errors.append(f"{price_type}: a({a_mid}) > b({b_mid}) > c({c_mid}) 不满足")
    
    # 检查 c2BPrices < b2BPrices < b2CPrices
    for condition in ['a', 'b', 'c']:
        c2b = float(result['c2BPrices'][condition]['mid'])
        b2b = float(result['b2BPrices'][condition]['mid'])
        b2c = float(result['b2CPrices'][condition]['mid'])
        
        if not (c2b < b2b < b2c):
            errors.append(f"条件{condition}: c2B({c2b}) < b2B({b2b}) < b2C({b2c}) 不满足")
    
    if errors:
        print("\n⚠️ 业务约束检查警告:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("\n✅ 业务约束检查通过")
        return True


def run_interactive(predictor: C2B2CPricePredictor):
    """交互模式"""
    print("\n交互模式 - 输入 b2BPrices.b.mid 值进行预测 (输入 q 退出)")
    print("-" * 50)
    
    while True:
        try:
            user_input = input("\n请输入价格 (万元): ").strip()
            
            if user_input.lower() in ['q', 'quit', 'exit']:
                print("退出程序")
                break
            
            price = float(user_input)
            
            if price <= 0:
                print("价格必须大于0")
                continue
            
            result = test_prediction(price, predictor)
            print(f"\n预测结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            validate_result(result)
            
        except ValueError:
            print("请输入有效的数字")
        except KeyboardInterrupt:
            print("\n退出程序")
            break


def main():
    parser = argparse.ArgumentParser(description='C2B2C价格预测测试程序')
    parser.add_argument('price', nargs='?', type=float, default=2.24,
                        help='b2BPrices.b.mid 价格值 (万元)')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='交互模式')
    parser.add_argument('--model-dir', '-m', type=str, default=None,
                        help='模型目录路径')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("C2B2C 价格预测测试")
    print("=" * 60)
    
    # 初始化预测器
    if args.model_dir:
        predictor = C2B2CPricePredictor(args.model_dir)
    else:
        predictor = C2B2CPricePredictor(model_dir)
    
    # 加载模型
    print(f"\n模型目录: {predictor.model_dir}")
    if not predictor.load():
        print("\n❌ 模型加载失败！请先运行 c2b2c_price_model_save_model.py 保存模型")
        return 1
    
    print("✅ 模型加载成功")
    
    if args.interactive:
        run_interactive(predictor)
    else:
        # 单次预测
        print(f"\n输入: b2BPrices.b.mid = {args.price}")
        result = test_prediction(args.price, predictor)
        
        print(f"\n预测结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 验证
        validate_result(result)
    
    return 0


if __name__ == "__main__":
    exit(main())
