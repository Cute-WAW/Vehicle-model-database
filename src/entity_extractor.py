"""
实体识别器模块
根据 .spec/spec_entity_extractor.md 规格实现
"""
import re
import yaml
import csv
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path


@dataclass
class ExtractedEntities:
    """提取的实体结构"""
    brand: Optional[str] = None          # 品牌
    series: Optional[str] = None         # 车系
    year: Optional[int] = None           # 年款
    displacement: Optional[str] = None   # 排量 (燃油车)
    range_km: Optional[int] = None       # 续航里程 (电动车)
    transmission: Optional[str] = None   # 档位
    drive: Optional[str] = None          # 驱动方式
    edition: Optional[str] = None        # 款式
    trim: Optional[str] = None           # 版式
    vehicle_type: str = "未知"           # 动力类型
    raw_text: str = ""                   # 原始输入
    confidence: float = 0.0              # 置信度
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "brand": self.brand,
            "series": self.series,
            "year": self.year,
            "displacement": self.displacement,
            "range_km": self.range_km,
            "transmission": self.transmission,
            "drive": self.drive,
            "edition": self.edition,
            "trim": self.trim,
            "vehicle_type": self.vehicle_type,
            "raw_text": self.raw_text,
            "confidence": self.confidence
        }


@dataclass
class SeriesEntry:
    """车系条目"""
    brand: str          # 品牌名
    series: str         # 标准车系名 (输出使用)
    alias: str          # 别名 (匹配使用)
    single_match: bool  # 单匹模式：True=仅需匹配车系, False=需同时匹配品牌和车系


class EntityExtractor:
    """实体识别器"""
    
    def __init__(self, config_path: str = "config/entity_rules.yaml"):
        """
        初始化识别器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # 加载车系库 (包含品牌、车系、别名信息)
        self.series_entries = self._load_car_series()
        # 提取品牌列表 (用于品牌识别)
        self.brands = self._get_unique_brands()
        
        # 编译正则表达式
        self.patterns = self._compile_patterns()
        
        # 词典（档位、驱动）
        self.transmission_words = [
            "自动", "手动", "手自一体", "双离合", "单离合",
            "CVT", "AT", "MT", "DCT", "AMT"
        ]
        self.drive_words = ["四驱", "前驱", "后驱", "两驱", "AWD", "4WD"]
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_car_series(self) -> List[SeriesEntry]:
        """
        加载车系库 (car_series.csv)
        列格式: 品牌,车系,别名,频次,单匹
        
        Returns:
            List[SeriesEntry]: 车系条目列表，按别名长度倒序排列
        """
        csv_path = self.config_path.parent / "dictionaries" / "car_series.csv"
        entries = []
        
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    brand = row.get('品牌', '').strip()
                    series = row.get('车系', '').strip()
                    alias = row.get('别名', '').strip()
                    single_match_val = row.get('单匹', '0').strip()
                    
                    if brand and series and alias:
                        single_match = single_match_val == '1'
                        entries.append(SeriesEntry(
                            brand=brand,
                            series=series,
                            alias=alias,
                            single_match=single_match
                        ))
        
        # 按别名长度倒序排列（优先匹配更长的别名）
        entries.sort(key=lambda x: len(x.alias), reverse=True)
        return entries
    
    def _get_unique_brands(self) -> List[str]:
        """获取去重的品牌列表，按长度倒序排列"""
        brands = set(entry.brand for entry in self.series_entries)
        return sorted(list(brands), key=len, reverse=True)
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """编译正则表达式"""
        return {
            "year": re.compile(r'(\d{4})款?'),
            # 排量格式：必须是 X.X 或 X.XT/L 形式，如 2.0T、1.5L、1.4TSI
            # 要求：要么有小数点，要么后面跟单位(T/L等)
            "displacement": re.compile(r'(\d+\.\d+)\s*(T|TSI|THP|TFSI|L|t)?(?![Kk])|(\d+)\s*(T|TSI|THP|TFSI|L|t)(?![Kk])'),
            # 续航：严格模式
            # 1. 数字 + 单位 (KM/km/公里) -> group 1
            # 2. 前缀 (续航/NEDC/CLTC/WLTC) + [冒号] + 数字 -> group 2
            "range_km": re.compile(r'(\d{3,4})\s*(?:[Kk][Mm]|公里)|(?:续航|NEDC|CLTC|WLTC)\s*[:：]?\s*(\d{3,4})'),
            "edition": re.compile(r'([\u4e00-\u9fa5]+款)'),
            "trim": re.compile(r'([\u4e00-\u9fa5\w]+(?:版|型)(?:Plus)?)'),
        }
    
    def preprocess(self, text: str) -> str:
        """
        预处理：去除噪音
        
        - 去除 "**车源"、"**车行" 等前缀
        - 统一分隔符
        - 去除多余空格
        """
        # 去除车源/车行前缀
        text = re.sub(r'.*车源\n?', '', text)
        text = re.sub(r'.*车行\n?', '', text)
        
        # 统一分隔符
        text = re.sub(r'[/\\|、]', ' ', text)
        
        # 去除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _extract_chinese_series_name(self, series: str) -> str:
        """
        从 'English Name [中文名]' 格式中提取中文名
        如果不匹配该格式则返回原值
        
        Args:
            series: 车系名称，可能是 'Captiva [科帕奇]' 或 '科帕奇' 格式
            
        Returns:
            提取的中文名或原值
        """
        match = re.search(r'\[([^\]]+)\]', series)
        if match:
            return match.group(1)
        return series
    
    def _match_brand_series(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        品牌和车系联合匹配逻辑
        
        规则：
        - 单匹=1：只要匹配到车系别名就输出品牌和车系
        - 单匹=0：必须同时在文本中匹配到品牌和车系别名才输出
        
        Args:
            text: 预处理后的文本
            
        Returns:
            Tuple[brand, series]: 匹配结果
        """
        text_upper = text.upper()
        
        # 首先识别文本中出现的品牌及其位置
        brand_positions = {}  # brand -> position
        for brand in self.brands:
            pos = text.find(brand)
            if pos >= 0:
                brand_positions[brand] = pos
            else:
                # 尝试大写匹配
                pos_upper = text_upper.find(brand.upper())
                if pos_upper >= 0:
                    brand_positions[brand] = pos_upper
        
        best_match = None
        best_alias_pos = float('inf')
        
        # 遍历所有车系条目，寻找最佳匹配
        for entry in self.series_entries:
            # 查找别名在文本中的位置
            alias_pos = text.find(entry.alias)
            if alias_pos < 0:
                # 尝试大写匹配
                alias_pos = text_upper.find(entry.alias.upper())
            
            if alias_pos < 0:
                continue
            
            # 找到了别名匹配
            if entry.single_match:
                # 单匹=1：只需匹配车系别名
                if alias_pos < best_alias_pos:
                    best_match = (entry.brand, entry.series)
                    best_alias_pos = alias_pos
            else:
                # 单匹=0：需要同时匹配品牌
                if entry.brand in brand_positions:
                    brand_pos = brand_positions[entry.brand]
                    # 选择匹配位置最靠前的
                    effective_pos = min(brand_pos, alias_pos)
                    if effective_pos < best_alias_pos:
                        best_match = (entry.brand, entry.series)
                        best_alias_pos = effective_pos
        
        if best_match:
            brand, series = best_match
            # 处理 'English Name [中文名]' 格式，提取中文名
            series = self._extract_chinese_series_name(series)
            return (brand, series)
        
        # 如果没有匹配到车系，但匹配到了品牌，只返回品牌
        if brand_positions:
            # 返回位置最靠前的品牌
            earliest_brand = min(brand_positions.items(), key=lambda x: x[1])
            return (earliest_brand[0], None)
        
        return (None, None)
    
    def extract(self, text: str) -> ExtractedEntities:
        """
        从文本中提取实体
        
        Args:
            text: 车辆名称字符串
            
        Returns:
            ExtractedEntities: 提取的实体结构
        """
        raw_text = text
        text = self.preprocess(text)
        
        entities = ExtractedEntities(raw_text=raw_text)
        matched_count = 0
        total_entities = 7  # 品牌、车系、年款、排量/续航、档位、驱动、版式
        
        # 1. 品牌和车系联合匹配
        brand, series = self._match_brand_series(text)
        if brand:
            entities.brand = brand
            matched_count += 1
        if series:
            entities.series = series
            matched_count += 1
        
        # 3. 年款匹配（正则）
        year_match = self.patterns["year"].search(text)
        if year_match:
            entities.year = int(year_match.group(1))
            matched_count += 1
        
        # 4. 排量匹配（正则）
        displacement_match = self.patterns["displacement"].search(text)
        if displacement_match:
            # 正则有两种模式：
            # 模式1: 带小数点的数字 (group 1, 2)，如 2.0T
            # 模式2: 整数+单位 (group 3, 4)，如 2T
            if displacement_match.group(1):
                num = displacement_match.group(1)
                unit = displacement_match.group(2) or ""
            else:
                num = displacement_match.group(3)
                unit = displacement_match.group(4) or ""
            entities.displacement = f"{num}{unit}".upper()
            matched_count += 1
        
        # 5. 续航里程匹配（正则）
        range_match = self.patterns["range_km"].search(text)
        if range_match:
            # group(1) 对应带单位的情况，group(2) 对应带前缀的情况
            range_val = range_match.group(1) or range_match.group(2)
            if range_val:
                entities.range_km = int(range_val)
                matched_count += 1
        
        # 6. 档位匹配（词典）
        for trans in self.transmission_words:
            if trans in text:
                entities.transmission = trans
                matched_count += 1
                break
        
        # 7. 驱动方式匹配（词典）
        for drive in self.drive_words:
            if drive in text:
                entities.drive = drive
                matched_count += 1
                break
        
        # 8. 款式匹配（正则）
        edition_match = self.patterns["edition"].search(text)
        if edition_match:
            entities.edition = edition_match.group(1)
        
        # 9. 版式匹配（正则）
        trim_match = self.patterns["trim"].search(text)
        if trim_match:
            entities.trim = trim_match.group(1)
            matched_count += 1
        
        # 10. 推断动力类型
        entities.vehicle_type = self._infer_vehicle_type(entities, text)
        
        # 计算置信度
        entities.confidence = matched_count / total_entities
        
        return entities
    
    def _infer_vehicle_type(self, entities: ExtractedEntities, text: str) -> str:
        """推断动力类型"""
        text_lower = text.lower()
        
        if "增程" in text:
            return "增程"
        elif "纯电" in text_lower or "ev" in text_lower:
            return "纯电"
        elif any(kw in text_lower for kw in ["混动", "phev", "dmi", "dm-i"]):
            return "混动"
        elif entities.range_km and not entities.displacement:
            return "纯电"
        elif entities.displacement:
            return "燃油"
        else:
            return "未知"


# 测试代码
if __name__ == "__main__":
    extractor = EntityExtractor()
    
    test_cases = [
        "宝马/X1/2016款 2.0T 自动 20Li豪华型前驱",
        "中升车源\n大众 帕萨特 2023款 1.4TSI 双离合 280TSI 星空精英版",
        "特斯拉 Model 3 2023款 420KM 长续航版",
        "WEY VV5 2018款 2.0T 自动",      # 带品牌的 VV5，应该输出
        "VV5 2018款 2.0T 自动",          # 不带品牌的 VV5，单匹=0，不应该输出车系
        "五菱 宏光MINI 2023款 120KM",     # 五菱宏光MINI 测试
    ]
    
    for text in test_cases:
        result = extractor.extract(text)
        print(f"\n输入: {text}")
        print(f"结果: 品牌={result.brand}, 车系={result.series}, 年款={result.year}")
