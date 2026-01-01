"""
匹配引擎模块
根据 .spec/spec_matching_engine.md 规格实现
"""
import yaml
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

from .entity_extractor import EntityExtractor, ExtractedEntities
from .vehicle_index import VehicleIndex, VehicleCandidate


@dataclass
class MatchCandidate:
    """匹配候选"""
    level_id: str
    score: float
    confidence: float
    matched_entities: List[str]
    vehicle_info: Dict[str, Any]


@dataclass
class DebugInfo:
    """调试信息"""
    candidates_after_brand: int = 0
    candidates_after_series: int = 0
    candidates_after_year: int = 0
    final_candidates: int = 0
    processing_time_ms: float = 0.0


@dataclass
class MatchResult:
    """匹配结果"""
    query: str
    extracted_entities: Dict[str, Any]
    matches: List[MatchCandidate]
    debug: DebugInfo
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "query": self.query,
            "extracted_entities": self.extracted_entities,
            "matches": [
                {
                    "level_id": m.level_id,
                    "score": m.score,
                    "confidence": m.confidence,
                    "matched_entities": m.matched_entities,
                    "vehicle_info": m.vehicle_info
                }
                for m in self.matches
            ],
            "debug": {
                "candidates_after_brand": self.debug.candidates_after_brand,
                "candidates_after_series": self.debug.candidates_after_series,
                "candidates_after_year": self.debug.candidates_after_year,
                "final_candidates": self.debug.final_candidates,
                "processing_time_ms": self.debug.processing_time_ms
            }
        }


class MatchingEngine:
    """匹配引擎"""
    
    def __init__(
        self,
        entity_extractor: EntityExtractor,
        vehicle_index: VehicleIndex,
        config_path: str = "config/matching_config.yaml"
    ):
        """
        初始化匹配引擎
        
        Args:
            entity_extractor: 实体识别器
            vehicle_index: 车型库索引
            config_path: 配置文件路径
        """
        self.entity_extractor = entity_extractor
        self.vehicle_index = vehicle_index
        self.config = self._load_config(config_path)
        
        # 权重
        self.weights = self.config.get("weights", {
            "brand": 100,
            "series": 80,
            "year": 50,
            "displacement": 40,
            "range_km": 40,
            "transmission": 30,
            "drive": 20,
            "trim": 15
        })
        
        # 阈值
        thresholds = self.config.get("thresholds", {})
        self.min_score = thresholds.get("min_score", 150)
        self.high_confidence = thresholds.get("high_confidence", 250)
        
        # 模糊规则
        self.fuzzy_rules = self.config.get("fuzzy_rules", {})
        
        # 排量等价映射
        self.displacement_equivalents = self.config.get("displacement_equivalents", {})
        self._build_displacement_map()
        
        # 档位等价映射
        self.transmission_equivalents = self.config.get("transmission_equivalents", {})
        self._build_transmission_map()
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        path = Path(config_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}
    
    def _build_displacement_map(self) -> None:
        """构建排量等价映射的反向索引"""
        self.displacement_map: Dict[str, str] = {}
        for canonical, equivalents in self.displacement_equivalents.items():
            self.displacement_map[canonical.upper()] = canonical.upper()
            for eq in equivalents:
                self.displacement_map[eq.upper()] = canonical.upper()
    
    def _build_transmission_map(self) -> None:
        """构建档位等价映射的反向索引"""
        self.transmission_map: Dict[str, str] = {}
        for canonical, equivalents in self.transmission_equivalents.items():
            self.transmission_map[canonical] = canonical
            for eq in equivalents:
                self.transmission_map[eq] = canonical
    
    def match(
        self, 
        query_text: str, 
        top_k: int = 5,
        min_score: Optional[float] = None
    ) -> MatchResult:
        """
        匹配车辆名称
        
        Args:
            query_text: 车辆名称
            top_k: 返回结果数量
            min_score: 最低分数阈值
            
        Returns:
            MatchResult: 匹配结果
        """
        start_time = time.time()
        min_score = min_score or self.min_score
        debug = DebugInfo()
        
        # 1. 实体识别
        entities = self.entity_extractor.extract(query_text)
        
        # 2. 品牌过滤
        if entities.brand:
            brand_candidates = self.vehicle_index.filter_by_brand(entities.brand)
            debug.candidates_after_brand = len(brand_candidates)
        else:
            # 无品牌，返回空结果
            return MatchResult(
                query=query_text,
                extracted_entities=entities.to_dict(),
                matches=[],
                debug=debug
            )
        
        # 3. 车系过滤
        if entities.series:
            series_candidates = self.vehicle_index.filter_by_series(entities.brand, entities.series)
            debug.candidates_after_series = len(series_candidates)
            candidates = series_candidates
        else:
            candidates = brand_candidates
            debug.candidates_after_series = len(brand_candidates)
        
        # 4. 获取候选详情并计算分数
        scored_candidates: List[Tuple[float, List[str], VehicleCandidate]] = []
        
        for level_id in candidates:
            detail = self.vehicle_index.get_detail(level_id)
            if not detail:
                continue
            
            candidate = VehicleCandidate(
                level_id=level_id,
                brand=detail.brand,
                series=detail.series,
                sales_name=detail.sales_name,
                year=detail.year,
                entities=detail.entities or {}
            )
            
            score, matched_entities = self._calculate_score(entities, candidate)
            
            if score >= min_score:
                scored_candidates.append((score, matched_entities, candidate))
        
        # 5. 排序取 TopK
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:top_k]
        
        debug.final_candidates = len(top_candidates)
        debug.processing_time_ms = (time.time() - start_time) * 1000
        
        # 6. 构建结果
        matches = []
        for score, matched_entities, candidate in top_candidates:
            confidence = self._calculate_confidence(score, matched_entities)
            matches.append(MatchCandidate(
                level_id=candidate.level_id,
                score=score,
                confidence=confidence,
                matched_entities=matched_entities,
                vehicle_info={
                    "brand": candidate.brand,
                    "series": candidate.series,
                    "sales_name": candidate.sales_name,
                    "year": candidate.year
                }
            ))
        
        return MatchResult(
            query=query_text,
            extracted_entities=entities.to_dict(),
            matches=matches,
            debug=debug
        )
    
    def _calculate_score(
        self,
        query_entities: ExtractedEntities,
        candidate: VehicleCandidate
    ) -> Tuple[float, List[str]]:
        """
        计算匹配分数
        
        Returns:
            (分数, 匹配的实体列表)
        """
        score = 0.0
        matched = []
        candidate_entities = candidate.entities
        
        # 品牌 (已经在过滤阶段匹配)
        score += self.weights["brand"]
        matched.append("brand")
        
        # 车系 (已经在过滤阶段匹配)
        if query_entities.series and candidate.series == query_entities.series:
            score += self.weights["series"]
            matched.append("series")
        
        # 年款
        if query_entities.year and candidate.year:
            year_score = self._score_year(query_entities.year, candidate.year)
            if year_score > 0:
                score += year_score
                matched.append("year")
        
        # 排量
        if query_entities.displacement:
            candidate_disp = candidate_entities.get("displacement", "")
            if self._is_displacement_match(query_entities.displacement, candidate_disp):
                score += self.weights["displacement"]
                matched.append("displacement")
        
        # 续航里程
        if query_entities.range_km and candidate_entities.get("range_km"):
            if self._is_range_match(query_entities.range_km, candidate_entities["range_km"]):
                score += self.weights["range_km"]
                matched.append("range_km")
        
        # 档位（考虑等价映射：自动=手自一体）
        if query_entities.transmission and candidate_entities.get("transmission"):
            if self._is_transmission_match(query_entities.transmission, candidate_entities["transmission"]):
                score += self.weights["transmission"]
                matched.append("transmission")
        
        # 驱动
        if query_entities.drive and candidate_entities.get("drive"):
            if query_entities.drive == candidate_entities["drive"]:
                score += self.weights["drive"]
                matched.append("drive")
        
        # 版式 (模糊匹配)
        if query_entities.trim and candidate_entities.get("trim"):
            if self._is_trim_match(query_entities.trim, candidate_entities["trim"]):
                score += self.weights["trim"]
                matched.append("trim")
        
        return score, matched
    
    def _score_year(self, query_year: int, candidate_year: int) -> float:
        """年款打分"""
        diff = abs(query_year - candidate_year)
        year_config = self.fuzzy_rules.get("year", {})
        
        if diff == 0:
            return year_config.get("exact_score", 50)
        elif diff == 1:
            return year_config.get("off_by_1_score", 30)
        elif diff == 2:
            return year_config.get("off_by_2_score", 10)
        else:
            return 0.0
    
    def _is_displacement_match(self, query: str, candidate: str) -> bool:
        """排量是否匹配（考虑等价映射）"""
        if not query or not candidate:
            return False
        
        q_normalized = self.displacement_map.get(query.upper(), query.upper())
        c_normalized = self.displacement_map.get(candidate.upper(), candidate.upper())
        
        return q_normalized == c_normalized
    
    def _is_range_match(self, query: int, candidate: int) -> bool:
        """续航里程是否匹配"""
        tolerance = self.fuzzy_rules.get("range_km", {}).get("tolerance", 20)
        return abs(query - candidate) <= tolerance
    
    def _is_transmission_match(self, query: str, candidate: str) -> bool:
        """档位是否匹配（考虑等价映射：自动=手自一体）"""
        if not query or not candidate:
            return False
        
        # 精确匹配
        if query == candidate:
            return True
        
        # 等价映射匹配
        q_normalized = self.transmission_map.get(query, query)
        c_normalized = self.transmission_map.get(candidate, candidate)
        
        return q_normalized == c_normalized
    
    def _is_trim_match(self, query: str, candidate: str) -> bool:
        """版式是否匹配（模糊）"""
        # 简单的包含匹配
        return query in candidate or candidate in query
    
    def _calculate_confidence(self, score: float, matched_entities: List[str]) -> float:
        """计算置信度"""
        max_score = sum(self.weights.values())
        confidence = score / max_score
        return round(min(confidence, 1.0), 2)
    
    def batch_match(
        self,
        queries: List[str],
        top_k: int = 5
    ) -> List[MatchResult]:
        """
        批量匹配
        
        Args:
            queries: 车辆名称列表
            top_k: 每条返回结果数量
            
        Returns:
            匹配结果列表
        """
        results = []
        for query in queries:
            result = self.match(query, top_k=top_k)
            results.append(result)
        return results


# 测试代码
if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)
    
    # 初始化
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    
    # 加载索引
    index.load("index/vehicle_index.pkl")
    
    # 初始化匹配引擎
    engine = MatchingEngine(extractor, index, "config/matching_config.yaml")
    
    # 测试匹配
    test_queries = [
        "宝马/X1/2016款 2.0T 自动 20Li豪华型前驱",
        "大众 帕萨特 2023款 1.4TSI 双离合 280TSI 星空精英版",
    ]
    
    for query in test_queries:
        result = engine.match(query)
        print(f"\n查询: {query}")
        print(f"识别实体: {result.extracted_entities}")
        print(f"匹配结果: {len(result.matches)} 个")
        for m in result.matches:
            print(f"  {m.level_id}: {m.vehicle_info['sales_name']} (分数: {m.score}, 置信度: {m.confidence})")
        print(f"处理时间: {result.debug.processing_time_ms:.2f}ms")
