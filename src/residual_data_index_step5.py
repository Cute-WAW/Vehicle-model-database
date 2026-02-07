"""
成交数据索引模块

功能：
1. 为 residual_value_data.csv 中的车辆全称建立索引
2. 实现相近车辆检索
3. 支持排除完全相同记录

使用方法：
    from residual_data_index import ResidualDataIndex
    
    index = ResidualDataIndex()
    index.build_from_csv('../output/residual_value_data.csv')
    
    # 检索相近车辆
    similar = index.search_similar('起亚 K3 2013款 1.6 手自一体 GLS', top_k=5)
"""

import pickle
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import logging
import re

from entity_extractor import EntityExtractor, ExtractedEntities

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ResidualRecord:
    """成交数据记录"""
    index: int  # DataFrame 行索引
    vehicle_full_name: str
    brand_series: str
    new_price: float
    used_price: float  # 二手车成交价
    adjusted_price: float  # 车况校正价
    years: float
    grade: str
    vehicle_type: str  # 车辆大类
    vehicle_size: str  # 车辆小类
    vehicle_attr: str  # 车辆属性
    city: str
    mileage: float
    transaction_date: str = "" # 交易时间
    source: str = "unknown"  # 数据来源
    entities: Optional[Dict] = None


@dataclass
class SimilarVehicle:
    """相近车辆"""
    record: ResidualRecord
    score: float
    matched_features: List[str]


class ResidualDataIndex:
    """成交数据索引"""
    
    def __init__(self, entity_extractor: Optional[EntityExtractor] = None):
        """
        初始化索引
        
        Args:
            entity_extractor: 实体识别器，如果不传则自动创建
        """
        if entity_extractor is None:
            config_path = Path(__file__).parent / '..' / 'config' / 'entity_rules.yaml'
            if config_path.exists():
                self.entity_extractor = EntityExtractor(str(config_path))
            else:
                self.entity_extractor = None
        else:
            self.entity_extractor = entity_extractor
        
        # 索引结构
        self.records: List[ResidualRecord] = []
        self.brand_series_index: Dict[str, List[int]] = {}  # 品牌车系 -> 记录索引列表
        self.brand_index: Dict[str, List[int]] = {}  # 品牌 -> 记录索引列表 (新增，用于降级搜索)
        self.vehicle_type_index: Dict[str, List[int]] = {}  # 车辆类别 -> 记录索引列表
        
        # 原始 DataFrame 引用
        self._df: Optional[pd.DataFrame] = None
    
    def build_from_csv(self, csv_path: str, index_path: str = None, force_rebuild: bool = False) -> None:
        """
        从CSD文件构建索引（支持缓存）
        
        Args:
            csv_path: CSV 文件路径
            index_path: 索引缓存文件路径，如果不传则不缓存
            force_rebuild: 是否强制重建索引
        """
        csv_path = Path(csv_path)
        
        # 尝试加载缓存的索引
        if index_path and not force_rebuild:
            if self._try_load_cached_index(str(csv_path), index_path):
                return
        
        # 构建新索引
        logger.info(f"加载成交数据: {csv_path}")
        self._df = pd.read_csv(csv_path)
        logger.info(f"共 {len(self._df)} 条记录")
        
        self._csv_mtime = csv_path.stat().st_mtime
        self._build_index()
        
        # 保存索引缓存
        if index_path:
            self.save(index_path)
    
    def _try_load_cached_index(self, csv_path: str, index_path: str) -> bool:
        """
        尝试加载缓存的索引
        
        Args:
            csv_path: CSV 文件路径
            index_path: 索引缓存文件路径
            
        Returns:
            是否成功加载缓存
        """
        index_file = Path(index_path)
        csv_file = Path(csv_path)
        
        if not index_file.exists():
            logger.info("索引缓存文件不存在，需要重建")
            return False
        
        try:
            with open(index_file, 'rb') as f:
                data = pickle.load(f)
            
            # 检查 CSV 文件修改时间
            cached_mtime = data.get('csv_mtime', 0)
            current_mtime = csv_file.stat().st_mtime
            
            if cached_mtime != current_mtime:
                logger.info(f"CSV文件已修改，需要重建索引 (缓存: {cached_mtime}, 当前: {current_mtime})")
                return False
            
            # 加载索引数据
            self.records = data['records']
            self.brand_series_index = data['brand_series_index']
            self.vehicle_type_index = data['vehicle_type_index']
            self.brand_index = data.get('brand_index', {}) # 兼容旧缓存
            
            if not self.brand_index:
                logger.info("索引缓存缺少 brand_index，需要重建")
                return False

            self._csv_mtime = cached_mtime
            
            logger.info(f"从缓存加载索引: {index_path}")
            logger.info(f"  记录数: {len(self.records)}")
            logger.info(f"  品牌车系数: {len(self.brand_series_index)}")
            logger.info(f"  车辆类别数: {len(self.vehicle_type_index)}")
            return True
            
        except Exception as e:
            logger.warning(f"加载索引缓存失败: {e}，需要重建")
            return False
    
    def build_from_dataframe(self, df: pd.DataFrame) -> None:
        """
        从 DataFrame 构建索引
        
        Args:
            df: 成交数据 DataFrame
        """
        self._df = df.copy()
        self._build_index()
    
    def _build_index(self) -> None:
        """构建索引"""
        logger.info("开始构建索引...")
        
        self.records = []
        self.brand_series_index = {}
        self.brand_index = {}
        self.vehicle_type_index = {}
        
        for idx, row in self._df.iterrows():
            # 创建记录
            record = ResidualRecord(
                index=idx,
                vehicle_full_name=str(row.get('车辆全称', '')),
                brand_series=str(row.get('品牌车系', '')),
                new_price=float(row.get('新车的价格', 0)),
                used_price=float(row.get('二手车的成交价', 0)),
                adjusted_price=float(row.get('车况校正价', 0)),
                years=float(row.get('使用年限', 0)),
                grade=str(row.get('车辆评级', '')),
                vehicle_type=str(row.get('车辆大类', '')),
                vehicle_size=str(row.get('车辆小类', '')),
                vehicle_attr=str(row.get('车辆属性', '')),
                city=str(row.get('城市', '')),
                mileage=float(row.get('行驶里程', 0)) if pd.notna(row.get('行驶里程')) else 0,
                transaction_date=str(row.get('交易时间', row.get('trade_date', ''))) if pd.notna(row.get('交易时间', row.get('trade_date', ''))) else '',
                source=str(row.get('数据来源', 'unknown'))
            )
            
            # 提取实体特征
            if self.entity_extractor and record.vehicle_full_name:
                entities = self.entity_extractor.extract(record.vehicle_full_name)
                record.entities = entities.to_dict()
            
            self.records.append(record)
            record_idx = len(self.records) - 1
            
            # 品牌车系索引
            if record.brand_series:
                if record.brand_series not in self.brand_series_index:
                    self.brand_series_index[record.brand_series] = []
                self.brand_series_index[record.brand_series].append(record_idx)
                
                # 品牌索引 (从 brand_series 提取品牌)
                # 假设格式为 "Brand-Series"
                parts = record.brand_series.split('-')
                if parts:
                    brand = parts[0]
                    if brand not in self.brand_index:
                        self.brand_index[brand] = []
                    self.brand_index[brand].append(record_idx)
            
            # 车辆类别索引 (大类-小类-属性)
            car_type = f"{record.vehicle_type}-{record.vehicle_size}-{record.vehicle_attr}"
            if car_type not in self.vehicle_type_index:
                self.vehicle_type_index[car_type] = []
            self.vehicle_type_index[car_type].append(record_idx)
        
        logger.info(f"索引构建完成:")
        logger.info(f"  记录数: {len(self.records)}")
        logger.info(f"  品牌车系数: {len(self.brand_series_index)}")
        logger.info(f"  车辆类别数: {len(self.vehicle_type_index)}")
    
    def get_car_type_for_brand_series(self, brand_series: str) -> Optional[str]:
        """
        获取品牌车系对应的车辆类别
        
        Args:
            brand_series: 品牌-车系
            
        Returns:
            车辆大类-车辆小类-车辆属性，如果找不到返回 None
        """
        if brand_series not in self.brand_series_index:
            return None
        
        record_indices = self.brand_series_index[brand_series]
        if not record_indices:
            return None
        
        # 返回第一个记录的类别
        record = self.records[record_indices[0]]
        return f"{record.vehicle_type}-{record.vehicle_size}-{record.vehicle_attr}"
    
    def find_identical_records(
        self,
        vehicle_full_name: str,
        brand_series: str,
        years: float,
        grade: str,
        city: str,
        mileage: float,
        tolerance_years: float = 0.1,
        tolerance_mileage: float = 0.5
    ) -> List[ResidualRecord]:
        """
        查找完全相同的车辆记录
        
        Args:
            vehicle_full_name: 车辆全称
            brand_series: 品牌车系
            years: 使用年限
            grade: 车辆评级
            city: 城市
            mileage: 行驶里程
            tolerance_years: 年限容差
            tolerance_mileage: 里程容差
            
        Returns:
            完全相同的记录列表
        """
        identical = []
        
        # 先按品牌车系筛选
        if brand_series not in self.brand_series_index:
            return identical
        
        for record_idx in self.brand_series_index[brand_series]:
            record = self.records[record_idx]
            
            # 检查各项是否匹配
            if record.vehicle_full_name != vehicle_full_name:
                continue
            if record.grade != grade:
                continue
            if record.city != city:
                continue
            if abs(record.years - years) > tolerance_years:
                continue
            if abs(record.mileage - mileage) > tolerance_mileage:
                continue
            
            identical.append(record)
        
        return identical
    
    def search_similar(
        self,
        vehicle_full_name: str,
        brand_series: str,
        years: float,
        grade: str = "",
        city: str = "",
        mileage: float = 0.0,
        exclude_identical: bool = True,
        top_k: int = 30
    ) -> List[SimilarVehicle]:
        """
        检索相近车辆
        
        Args:
            vehicle_full_name: 车辆全称
            brand_series: 品牌车系
            years: 使用年限
            grade: 车辆评级
            city: 城市
            mileage: 行驶里程
            exclude_identical: 是否排除完全相同的记录
            top_k: 返回数量
            
        Returns:
            相近车辆列表，按分数排序
        """
        candidates = []
        
        # 提取查询实体
        query_entities = None
        if self.entity_extractor:
            query_entities = self.entity_extractor.extract(vehicle_full_name)
        
        # 确定检索范围
        search_indices = []
        if brand_series in self.brand_series_index:
            search_indices = self.brand_series_index[brand_series]
        else:
            # 降级：尝试同品牌检索
            parts = brand_series.split('-')
            if parts:
                brand = parts[0]
                if brand in self.brand_index:
                    search_indices = self.brand_index[brand]
                    logger.warning(f"未找到车系 {brand_series}，降级为品牌 {brand} 检索 (候选数: {len(search_indices)})")

        if search_indices:
            for record_idx in search_indices:
                record = self.records[record_idx]
                
                # 排除完全相同
                if exclude_identical and record.vehicle_full_name == vehicle_full_name:
                    continue
                
                score, matched = self._calculate_similarity(
                    query_entities, record, years, grade, city, mileage
                )
                
                if score > 0:
                    candidates.append(SimilarVehicle(
                        record=record,
                        score=score,
                        matched_features=matched
                    ))
        
        # 按分数排序
        candidates.sort(key=lambda x: x.score, reverse=True)
        
        return candidates[:top_k]
    
    def _calculate_similarity(
        self,
        query_entities: Optional[ExtractedEntities],
        record: ResidualRecord,
        query_years: float,
        query_grade: str = "",
        query_city: str = "",
        query_mileage: float = 0.0
    ) -> Tuple[float, List[str]]:
        """
        计算相似度分数
        
        Args:
            query_entities: 查询实体
            record: 候选记录
            query_years: 查询年限
            query_grade: 查询评级
            query_city: 查询城市
            query_mileage: 查询里程
            
        Returns:
            (分数, 匹配的特征列表)
        """
        score = 0.0
        matched = []
        
        # 基础分：品牌车系匹配
        score += 50
        matched.append('brand_series')
        
        # 年限相近度 (最高30分)
        year_diff = abs(record.years - query_years)
        if year_diff < 0.5:
            score += 30
            matched.append('year_exact')
        elif year_diff < 1:
            score += 25
            matched.append('year_close')
        elif year_diff < 2:
            score += 15
            matched.append('year_similar')
        elif year_diff < 3:
            score += 5
        
        # 评级匹配 (+10分)
        if query_grade and record.grade == query_grade:
            score += 10
            matched.append('grade')
        
        # 城市匹配 (+5分)
        if query_city and record.city == query_city:
            score += 5
            matched.append('city')
        
        # 里程接近 (+10分)
        if query_mileage > 0 and record.mileage > 0:
            mileage_diff = abs(record.mileage - query_mileage)
            if mileage_diff < 2:  # 差小于2万公里
                score += 10
                matched.append('mileage_exact')
            elif mileage_diff < 5:  # 差小于5万公里
                score += 5
                matched.append('mileage_close')
        
        # 如果有实体信息，进行更细粒度的匹配
        if query_entities and record.entities:
            record_entities = record.entities
            
            # 年款匹配 (20分)
            if query_entities.year and record_entities.get('year'):
                if query_entities.year == record_entities.get('year'):
                    score += 20
                    matched.append('model_year')
            
            # 排量匹配 (15分)
            if query_entities.displacement and record_entities.get('displacement'):
                if query_entities.displacement == record_entities.get('displacement'):
                    score += 15
                    matched.append('displacement')
            
            # 档位匹配 (10分)
            if query_entities.transmission and record_entities.get('transmission'):
                if self._is_transmission_match(
                    query_entities.transmission, 
                    record_entities.get('transmission')
                ):
                    score += 10
                    matched.append('transmission')
            
            # 版式匹配 (10分)
            if query_entities.trim and record_entities.get('trim'):
                if query_entities.trim in record_entities.get('trim', '') or \
                   record_entities.get('trim', '') in query_entities.trim:
                    score += 10
                    matched.append('trim')
        
        return score, matched
    
    def _is_transmission_match(self, query: str, candidate: str) -> bool:
        """档位是否匹配"""
        if query == candidate:
            return True
        # 自动 = 手自一体
        auto_variants = {'自动', '手自一体', 'AT', 'CVT', 'DCT', '双离合'}
        if query in auto_variants and candidate in auto_variants:
            return True
        return False
    
    def get_records_by_brand_series(self, brand_series: str) -> List[ResidualRecord]:
        """获取指定品牌车系的所有记录"""
        if brand_series not in self.brand_series_index:
            return []
        return [self.records[i] for i in self.brand_series_index[brand_series]]
    
    def get_records_by_car_type(self, car_type: str) -> List[ResidualRecord]:
        """获取指定车辆类别的所有记录"""
        if car_type not in self.vehicle_type_index:
            return []
        return [self.records[i] for i in self.vehicle_type_index[car_type]]
    
    def save(self, path: str) -> None:
        """保存索引到文件"""
        data = {
            'records': self.records,
            'brand_series_index': self.brand_series_index,
            'brand_index': self.brand_index,
            'vehicle_type_index': self.vehicle_type_index,
            'csv_mtime': getattr(self, '_csv_mtime', 0)
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"索引已保存到: {path}")
    
    def load(self, path: str) -> None:
        """从文件加载索引"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.records = data['records']
        self.brand_series_index = data['brand_series_index']
        self.brand_index = data.get('brand_index', {})
        self.vehicle_type_index = data['vehicle_type_index']
        self._csv_mtime = data.get('csv_mtime', 0)
        logger.info(f"索引已加载，共 {len(self.records)} 条记录")


if __name__ == '__main__':
    # 测试
    import os
    os.chdir(Path(__file__).parent.parent)
    
    # 路径配置
    csv_path = 'output/cheyipai_more_residual_value.csv'
    index_path = 'index/residual_data_index.pkl'
    
    if not os.path.exists(csv_path):
        print(f"数据文件不存在: {csv_path}")
        exit(1)
        
    # 初始化并构建索引
    index = ResidualDataIndex()
    # 强制重建索引以确保使用最新数据
    index.build_from_csv(csv_path, index_path=index_path, force_rebuild=True)
    
    print(f"\n索引构建完成: {index_path}")
    print(f"包含记录数: {len(index.records)}")
    
    # 获取第一条有效记录进行测试
    if index.records:
        test_record = index.records[0]
        test_name = test_record.vehicle_full_name
        test_series = test_record.brand_series
        test_years = test_record.years
        
        print(f"\n测试检索功能:")
        print(f"查询: {test_name} ({test_series}, {test_years}年)")
        
        similar = index.search_similar(test_name, test_series, years=test_years, top_k=5)
        print(f"找到 {len(similar)} 个相近车辆:")
        for s in similar:
            print(f"  分数={s.score:.0f}, 车辆={s.record.vehicle_full_name}")
            print(f"    成交价={s.record.used_price}万, 年限={s.record.years:.1f}年, 匹配={s.matched_features}")
    else:
        print("警告: 索引中没有记录，无法测试检索功能")
