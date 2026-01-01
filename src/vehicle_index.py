"""
车型库索引模块
根据 .spec/spec_vehicle_index.md 规格实现
"""
import pickle
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
import pandas as pd
from datetime import datetime

from .entity_extractor import EntityExtractor, ExtractedEntities


@dataclass
class VehicleDetail:
    """车型详情"""
    level_id: str
    brand: str
    series: str
    models: str
    sales_name: str
    year: int
    guiding_price: Optional[float] = None
    vehicle_type: Optional[str] = None
    entities: Optional[Dict] = None


@dataclass
class VehicleCandidate:
    """候选车型"""
    level_id: str
    brand: str
    series: str
    sales_name: str
    year: int
    entities: Dict


class VehicleIndex:
    """车型库索引"""
    
    def __init__(self, entity_extractor: EntityExtractor):
        """
        初始化索引
        
        Args:
            entity_extractor: 实体识别器实例
        """
        self.entity_extractor = entity_extractor
        
        # L1: 品牌索引
        self.brand_index: Dict[str, Set[str]] = {}
        
        # L2: 车系索引
        self.series_index: Dict[Tuple[str, str], Set[str]] = {}
        
        # L3: 特征倒排索引
        self.feature_index: Dict[str, Set[str]] = {}
        
        # L4: 详情存储
        self.detail_store: Dict[str, VehicleDetail] = {}
        
        # 元数据
        self.build_time: Optional[str] = None
        self.version: str = "1.0"
    
    def build(self, vehicle_library: pd.DataFrame) -> None:
        """
        构建索引
        
        Args:
            vehicle_library: 车型库 DataFrame
            必需字段: brand, series, models, sales_name, year, level_id
        """
        print(f"开始构建索引，共 {len(vehicle_library)} 条记录...")
        
        for idx, row in vehicle_library.iterrows():
            level_id = str(row['level_id'])
            brand = str(row['brand'])
            series = str(row['series'])
            models = str(row.get('models', ''))
            sales_name = str(row['sales_name'])
            year = int(row['year']) if pd.notna(row['year']) else 0
            guiding_price = float(row['guiding_price']) if 'guiding_price' in row and pd.notna(row['guiding_price']) else None
            vehicle_type = str(row.get('vehicle_type_agg', '')) if 'vehicle_type_agg' in row else None
            
            # 提取 sales_name 中的实体
            entities = self.entity_extractor.extract(sales_name)
            
            # L1: 品牌索引
            if brand not in self.brand_index:
                self.brand_index[brand] = set()
            self.brand_index[brand].add(level_id)
            
            # L2: 车系索引
            key = (brand, series)
            if key not in self.series_index:
                self.series_index[key] = set()
            self.series_index[key].add(level_id)
            
            # L3: 特征倒排索引
            self._add_to_feature_index(level_id, entities)
            
            # L4: 详情存储
            self.detail_store[level_id] = VehicleDetail(
                level_id=level_id,
                brand=brand,
                series=series,
                models=models,
                sales_name=sales_name,
                year=year,
                guiding_price=guiding_price,
                vehicle_type=vehicle_type,
                entities=entities.to_dict()
            )
            
            if (idx + 1) % 10000 == 0:
                print(f"已处理 {idx + 1} 条记录...")
        
        self.build_time = datetime.now().isoformat()
        print(f"索引构建完成！共 {len(self.detail_store)} 条记录")
        print(f"品牌数: {len(self.brand_index)}, 车系数: {len(self.series_index)}")
    
    def _add_to_feature_index(self, level_id: str, entities: ExtractedEntities) -> None:
        """添加到特征倒排索引"""
        features = []
        
        if entities.displacement:
            features.append(f"displacement:{entities.displacement}")
        if entities.range_km:
            features.append(f"range_km:{entities.range_km}")
        if entities.transmission:
            features.append(f"transmission:{entities.transmission}")
        if entities.drive:
            features.append(f"drive:{entities.drive}")
        if entities.year:
            features.append(f"year:{entities.year}")
        
        for feature in features:
            if feature not in self.feature_index:
                self.feature_index[feature] = set()
            self.feature_index[feature].add(level_id)
    
    def search(
        self, 
        entities: ExtractedEntities,
        filters: Optional[Dict] = None
    ) -> List[VehicleCandidate]:
        """
        搜索候选车型
        
        Args:
            entities: 查询实体
            filters: 额外过滤条件
            
        Returns:
            候选车型列表
        """
        candidates = None
        
        # L1: 品牌过滤
        if entities.brand and entities.brand in self.brand_index:
            candidates = self.brand_index[entities.brand].copy()
        else:
            # 无品牌匹配，返回空
            return []
        
        # L2: 车系过滤
        if entities.series:
            key = (entities.brand, entities.series)
            if key in self.series_index:
                candidates = candidates.intersection(self.series_index[key])
        
        # 转换为候选列表
        result = []
        for level_id in candidates:
            detail = self.detail_store.get(level_id)
            if detail:
                result.append(VehicleCandidate(
                    level_id=level_id,
                    brand=detail.brand,
                    series=detail.series,
                    sales_name=detail.sales_name,
                    year=detail.year,
                    entities=detail.entities or {}
                ))
        
        return result
    
    def filter_by_brand(self, brand: str) -> Set[str]:
        """按品牌过滤"""
        return self.brand_index.get(brand, set())
    
    def filter_by_series(self, brand: str, series: str) -> Set[str]:
        """按车系过滤"""
        return self.series_index.get((brand, series), set())
    
    def get_detail(self, level_id: str) -> Optional[VehicleDetail]:
        """获取车型详情"""
        return self.detail_store.get(level_id)
    
    def save(self, path: str) -> None:
        """持久化索引到文件"""
        index_data = {
            "brand_index": self.brand_index,
            "series_index": self.series_index,
            "feature_index": self.feature_index,
            "detail_store": self.detail_store,
            "version": self.version,
            "build_time": self.build_time
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(index_data, f)
        print(f"索引已保存到: {path}")
    
    def load(self, path: str) -> None:
        """从文件加载索引"""
        with open(path, 'rb') as f:
            index_data = pickle.load(f)
        
        self.brand_index = index_data["brand_index"]
        self.series_index = index_data["series_index"]
        self.feature_index = index_data["feature_index"]
        self.detail_store = index_data["detail_store"]
        self.version = index_data.get("version", "1.0")
        self.build_time = index_data.get("build_time")
        
        print(f"索引已加载，共 {len(self.detail_store)} 条记录")
        print(f"构建时间: {self.build_time}")


# 测试代码
if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)
    
    # 初始化
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    
    # 加载车型库
    df = pd.read_csv("data/力洋车型库精简5.csv")
    print(f"车型库共 {len(df)} 条记录")
    
    # 构建索引
    index.build(df)
    
    # 保存索引
    index.save("index/vehicle_index.pkl")
    
    # 测试搜索
    test_entities = extractor.extract("宝马/X1/2016款 2.0T 自动 豪华版")
    candidates = index.search(test_entities)
    print(f"\n搜索结果: {len(candidates)} 个候选")
    for c in candidates[:5]:
        print(f"  {c.level_id}: {c.brand} {c.series} {c.sales_name}")
