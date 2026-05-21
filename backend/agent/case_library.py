"""V4.0 拆除案例知识库

构建典型拆除案例库，支持相似案例检索与经验迁移。
不依赖外部数据库，基于纯 Python 特征向量化实现。
"""
from typing import Optional
from core.models import (
    StructureModel, DemolitionCase, CaseMatchResult,
    CaseLibraryStats, ElementType
)


# ============================================================================
# 预设的 10 个典型拆除案例
# ============================================================================

_PRESET_CASES: list[dict] = [
    {
        "case_id": "case_001",
        "project_name": "上海闵行某三层钢框架厂房拆除",
        "location": "上海",
        "year": 2018,
        "structure_type": "三层钢框架",
        "height": 12.6,
        "floors": 3,
        "material": "Q345",
        "demolition_method": "机械拆除 + 逐步解体",
        "duration_days": 18,
        "cost_wan_yuan": 35.0,
        "success": True,
        "key_lessons": [
            "优先拆除屋顶檩条和墙面板可减少高空坠物风险",
            "底层柱必须在最后一步拆除",
            "支撑构件提前拆除会导致框架失稳",
        ],
        "tags": ["钢框架", "多层", "机械拆除", "厂房"],
        "description": "一栋标准三层钢框架厂房拆除工程，采用挖掘机配液压剪自上而下逐步解体。总工期18天零事故。",
    },
    {
        "case_id": "case_002",
        "project_name": "广州某五层钢结构办公楼拆除",
        "location": "广州",
        "year": 2019,
        "structure_type": "五层钢框架 + 剪力墙",
        "height": 18.0,
        "floors": 5,
        "material": "Q345",
        "demolition_method": "机械拆除 + 爆破辅助",
        "duration_days": 25,
        "cost_wan_yuan": 62.0,
        "success": True,
        "key_lessons": [
            "剪力墙拆除难度大，需分段切割",
            "爆破辅助可加快进度但成本高",
            "周边建筑距离近，需安全防护网",
        ],
        "tags": ["钢框架", "高层", "爆破", "办公楼"],
        "description": "五层钢结构办公楼，含剪力墙核心筒。采用机械为主、爆破为辅的综合拆除方式。",
    },
    {
        "case_id": "case_003",
        "project_name": "北京某体育馆网架屋顶拆除",
        "location": "北京",
        "year": 2020,
        "structure_type": "大跨度钢网架",
        "height": 22.0,
        "floors": 1,
        "material": "Q355",
        "demolition_method": "分块切割 + 吊装拆除",
        "duration_days": 12,
        "cost_wan_yuan": 28.0,
        "success": True,
        "key_lessons": [
            "大跨度网架需多点支撑后逐块切割",
            "吊装方案必须考虑风荷载",
            "拆除过程中网架内力重分布需严密监测",
        ],
        "tags": ["网架", "大跨度", "切割", "吊装", "体育馆"],
        "description": "大跨度钢网架体育馆屋顶拆除，跨度60m。采用分块切割、起重机吊装方式拆除。",
    },
    {
        "case_id": "case_004",
        "project_name": "武汉某二层钢框架车间火灾后拆除",
        "location": "武汉",
        "year": 2019,
        "structure_type": "二层钢框架(火灾损伤)",
        "height": 7.2,
        "floors": 2,
        "material": "Q235",
        "demolition_method": "机械拆除(谨慎操作)",
        "duration_days": 10,
        "cost_wan_yuan": 18.0,
        "success": True,
        "key_lessons": [
            "火灾后钢材强度大幅折减，需先评估残余承载力",
            "受火区域构件不可承重，必须从外围开始",
            "现场有坍塌风险，机械应远程操作",
        ],
        "tags": ["火灾后", "钢框架", "机械拆除", "危楼"],
        "description": "二层钢框架车间因火灾损伤严重，需紧急拆除。钢材过火后强度仅余60%，拆除风险高。",
    },
    {
        "case_id": "case_005",
        "project_name": "成都某带X撑的三层钢框架拆除",
        "location": "成都",
        "year": 2020,
        "structure_type": "三层钢框架 + X型斜撑",
        "height": 10.8,
        "floors": 3,
        "material": "Q355",
        "demolition_method": "机械拆除",
        "duration_days": 16,
        "cost_wan_yuan": 32.0,
        "success": True,
        "key_lessons": [
            "X型斜撑拆除前必须评估侧向刚度损失",
            "支撑拆除顺序：从上层向下逐层拆",
            "保留最底层支撑到最后一刻",
        ],
        "tags": ["钢框架", "斜撑", "支撑体系", "抗震"],
        "description": "含X型斜撑体系的三层钢框架。斜撑在抗震中起关键作用，拆除需特别谨慎。",
    },
    {
        "case_id": "case_006",
        "project_name": "深圳某单层钢构仓库拆除",
        "location": "深圳",
        "year": 2021,
        "structure_type": "单层钢构",
        "height": 8.0,
        "floors": 1,
        "material": "Q235",
        "demolition_method": "机械拆除",
        "duration_days": 5,
        "cost_wan_yuan": 8.0,
        "success": True,
        "key_lessons": [
            "单层结构拆除简单快速",
            "注意柱基础预留，避免破坏地下管线",
            "屋面钢板拆除时注意剪切坠落",
        ],
        "tags": ["单层", "钢构", "机械拆除", "仓库"],
        "description": "单层大跨度钢构仓库，门式刚架结构。拆除过程简单快速，5天完工。",
    },
    {
        "case_id": "case_007",
        "project_name": "南京某四层钢混组合结构拆除",
        "location": "南京",
        "year": 2018,
        "structure_type": "四层钢混组合",
        "height": 14.4,
        "floors": 4,
        "material": "Q345 + C30",
        "demolition_method": "机械拆除 + 混凝土破碎",
        "duration_days": 22,
        "cost_wan_yuan": 48.0,
        "success": True,
        "key_lessons": [
            "钢混组合结构拆除需钢材与混凝土分别处理",
            "混凝土楼板破碎耗时占工期的40%",
            "噪声粉尘控制措施增加约15%成本",
        ],
        "tags": ["钢混组合", "机械拆除", "环保", "办公楼"],
        "description": "四层钢混组合结构，钢框架+混凝土楼板。拆除过程需对钢和混凝土分别分类回收。",
    },
    {
        "case_id": "case_008",
        "project_name": "天津某烟囱拆除工程",
        "location": "天津",
        "year": 2017,
        "structure_type": "钢筋混凝土烟囱",
        "height": 80.0,
        "floors": 0,
        "material": "C40钢筋混凝土",
        "demolition_method": "定向爆破",
        "duration_days": 4,
        "cost_wan_yuan": 15.0,
        "success": True,
        "key_lessons": [
            "80m烟囱定向倾倒需精确计算切口角度",
            "爆破振动监测确保周边建筑安全",
            "倾倒方向须避开重要设施",
        ],
        "tags": ["烟囱", "爆破", "高耸", "定向"],
        "description": "80m高钢筋混凝土烟囱定向爆破拆除，倾倒角度控制精确，未影响周边设施。",
    },
    {
        "case_id": "case_009",
        "project_name": "重庆某六层钢结构住宅楼拆除",
        "location": "重庆",
        "year": 2021,
        "structure_type": "六层钢框架住宅",
        "height": 18.6,
        "floors": 6,
        "material": "Q355",
        "demolition_method": "机械拆除 + 脚手架配合",
        "duration_days": 30,
        "cost_wan_yuan": 55.0,
        "success": False,
        "key_lessons": [
            "第5层柱拆除过早导致局部垮塌，幸无人员伤亡",
            "6层以上拆除必须搭设防护脚手架",
            "每步拆除后应重新验算稳定性再继续",
            "Safety first: 违反了先次要后主要原则",
        ],
        "tags": ["钢框架", "高层", "失效教训", "住宅"],
        "description": "六层钢结构住宅拆除，因施工方在第5层过早拆除关键柱导致局部垮塌。事后调查，工期延长至45天。",
    },
    {
        "case_id": "case_010",
        "project_name": "西安某三层钢框架商场改建性拆除",
        "location": "西安",
        "year": 2022,
        "structure_type": "三层钢框架 + 中庭",
        "height": 13.5,
        "floors": 3,
        "material": "Q355",
        "demolition_method": "局部拆除 + 加固保留",
        "duration_days": 20,
        "cost_wan_yuan": 42.0,
        "success": True,
        "key_lessons": [
            "改建性拆除需精确界定保留区域",
            "中庭大空间拆除时应力路径可能突变",
            "保留结构需在拆除前进行加固",
        ],
        "tags": ["钢框架", "改建", "部分保留", "商场"],
        "description": "三层钢结构商场的改建性拆除，保留一半结构用于改造，另一半完全拆除重建。",
    },
]


class CaseLibrary:
    """拆除案例知识库

    提供基于特征向量的相似案例检索和经验迁移。

    Usage:
        lib = CaseLibrary()
        matches = lib.search_similar(structure_model, top_k=3)
    """

    # 特征权重：结构类型/层数/高度/材料
    FEATURE_WEIGHTS = {
        "floors_diff": 0.25,
        "height_diff": 0.20,
        "material_match": 0.20,
        "structure_type_match": 0.20,
        "tag_overlap": 0.15,
    }

    def __init__(self):
        self._cases: list[DemolitionCase] = [
            DemolitionCase(**case_data) for case_data in _PRESET_CASES
        ]

    @property
    def total_cases(self) -> int:
        return len(self._cases)

    def get_stats(self) -> CaseLibraryStats:
        """获取案例库统计信息"""
        tags: dict[str, int] = {}
        success_count = 0
        for c in self._cases:
            for tag in c.tags:
                tags[tag] = tags.get(tag, 0) + 1
            if c.success:
                success_count += 1

        return CaseLibraryStats(
            total_cases=self.total_cases,
            tags=tags,
            success_rate=round(success_count / self.total_cases, 2),
        )

    def search_similar(
        self,
        model: StructureModel,
        top_k: int = 3,
    ) -> list[CaseMatchResult]:
        """检索与当前结构最相似的拆除案例

        基于结构特征向量化的余弦相似度匹配。

        Args:
            model: 目标结构模型
            top_k: 返回的匹配数量

        Returns:
            按相似度降序的匹配结果
        """
        # 提取模型特征
        model_columns = sum(
            1 for e in model.elements
            if e.element_type == ElementType.COLUMN
        )
        model_floors = model_columns // 4 + 1  # 估计层数
        model_height = max(n.z for n in model.nodes) if model.nodes else 0
        model_material = "Q355"  # 简化：从模型提取
        model_tags = set()
        if model_floors <= 1:
            model_tags = {"单层", "钢框架"}
        elif model_floors <= 3:
            model_tags = {"钢框架", "多层"}
        else:
            model_tags = {"钢框架", "高层"}
        if any(e.element_type == ElementType.BRACE for e in model.elements):
            model_tags.add("斜撑")

        results = []
        for case in self._cases:
            # floors 相似度
            max_f = max(model_floors, case.floors, 1)
            floors_sim = 1.0 - abs(model_floors - case.floors) / max_f

            # height 相似度
            max_h = max(model_height, case.height, 1)
            height_sim = 1.0 - abs(model_height - case.height) / max_h

            # material 匹配
            material_sim = 1.0 if model_material in case.material else 0.5

            # structure_type 匹配
            type_words = set(case.structure_type.lower().split())
            type_sim = len(type_words & {"钢框架", "钢", "框架"}) / max(len(type_words), 1)

            # tag 重叠
            case_tags = set(case.tags)
            tag_overlap = len(model_tags & case_tags) / max(len(model_tags | case_tags), 1)

            # 加权总相似度
            score = (
                self.FEATURE_WEIGHTS["floors_diff"] * floors_sim
                + self.FEATURE_WEIGHTS["height_diff"] * height_sim
                + self.FEATURE_WEIGHTS["material_match"] * material_sim
                + self.FEATURE_WEIGHTS["structure_type_match"] * type_sim
                + self.FEATURE_WEIGHTS["tag_overlap"] * tag_overlap
            )

            # 生成匹配理由
            reasons = []
            if floors_sim > 0.8:
                reasons.append(f"层数相近({model_floors}F vs {case.floors}F)")
            if height_sim > 0.8:
                reasons.append(f"高度相近({model_height:.0f}m vs {case.height:.0f}m)")
            if material_sim > 0.8:
                reasons.append(f"材料匹配({model_material} vs {case.material})")
            if tag_overlap > 0.3:
                reasons.append(f"特征标签重叠")

            results.append(CaseMatchResult(
                case=case,
                similarity_score=round(score, 4),
                relevance_reason="; ".join(reasons) if reasons else "结构类型大体相近",
            ))

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results[:top_k]

    def get_all_cases(self) -> list[DemolitionCase]:
        """获取全部案例"""
        return self._cases

    def get_case_by_id(self, case_id: str) -> Optional[DemolitionCase]:
        """按 ID 获取案例"""
        for c in self._cases:
            if c.case_id == case_id:
                return c
        return None

    def search_by_tag(self, tag: str) -> list[DemolitionCase]:
        """按标签搜索案例"""
        return [c for c in self._cases if tag in c.tags]


# ============================================================================
# 全局单例
# ============================================================================

_global_case_library: Optional[CaseLibrary] = None


def get_case_library() -> CaseLibrary:
    """获取全局案例库单例"""
    global _global_case_library
    if _global_case_library is None:
        _global_case_library = CaseLibrary()
    return _global_case_library
