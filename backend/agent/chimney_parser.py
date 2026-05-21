"""V3.0 烟囱结构自然语言解析器

将烟囱自然语言描述解析为 ChimneyModel。
支持钢筋混凝土烟囱的变截面、材料分层、顶部附属结构等参数提取。

解析能力覆盖：
- 高度参数：总高、段标高
- 直径参数：底径、顶径、变截面
- 壁厚参数
- 材料等级：C30/C40/C50 混凝土，Q235/Q355 钢材
- 顶部附属：排气筒、钢帽等
- 切口/定向拆除参数
"""

import re
import logging
from typing import Optional
from core.models import (
    ChimneyModel, ChimneySegment, ChimneyAttachment
)

logger = logging.getLogger(__name__)

# ============================================================================
# 预设混凝土材料参数
# ============================================================================

CONCRETE_GRADES = {
    "C30": {"fc": 20.1, "E": 30000, "density": 2400},
    "C35": {"fc": 23.4, "E": 31500, "density": 2400},
    "C40": {"fc": 26.8, "E": 32500, "density": 2450},
    "C45": {"fc": 29.6, "E": 33500, "density": 2450},
    "C50": {"fc": 32.4, "E": 34500, "density": 2500},
}

STEEL_GRADES = {
    "Q235": {"E": 206000, "fy": 235, "density": 7850},
    "Q355": {"E": 206000, "fy": 355, "density": 7850},
}


class ChimneyParser:
    """烟囱自然语言解析器

    示例描述：
    "建立一个高60m、底径5m、顶径3m、壁厚0.3m的C40钢筋混凝土烟囱，
     顶部设5m钢制排气筒"

    支持参数：
    - 高度 (m): 总高、段高
    - 直径 (m): 底径、顶径
    - 壁厚 (m)
    - 材料: C30~C50, 钢筋混凝土/钢结构
    - 配筋率: 默认 0.8%
    - 切口高度: 拆除切口位置
    - 定向方向: 倾倒方向
    """

    # ---- 主正则模式 ----
    PATTERN_HEIGHT = re.compile(
        r'(?:高|总高|高度)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_BASE_DIAMETER = re.compile(
        r'(?:底径|底部直径|基底直径|底部外径)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_TOP_DIAMETER = re.compile(
        r'(?:顶径|顶部直径|顶部外径|顶口直径|顶部)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_WALL_THICKNESS = re.compile(
        r'(?:壁厚|壁体厚度|管壁厚度)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_CONCRETE_GRADE = re.compile(
        r'(C\d{2})',
        re.IGNORECASE
    )
    PATTERN_REBAR_RATIO = re.compile(
        r'(?:配筋率|含筋率|钢筋率)\s*(\d+\.?\d*)\s*%',
        re.IGNORECASE
    )
    PATTERN_NOTCH_HEIGHT = re.compile(
        r'(?:切口|开槽|爆破口)\s*(?:高|高度|标高)?\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_NOTCH_ANGLE = re.compile(
        r'(?:切口角度|开口角)\s*(\d+\.?\d*)\s*(?:度|°)',
        re.IGNORECASE
    )
    PATTERN_DIRECTION = re.compile(
        r'(?:定向|倾倒方向)\s*(\d+\.?\d*)\s*(?:度|°)',
        re.IGNORECASE
    )
    # 附属结构
    PATTERN_ATTACHMENT = re.compile(
        r'(?:顶部|顶端|上部)\s*(?:设|有|安装|设置)?\s*(\d+\.?\d*)\s*(?:m|米)\s*'
        r'(?:高(?:的)?)?\s*(钢(?:制)?|金属|Q\d{3})?\s*(?:排气筒|排气管|钢帽|钢制|钢管|金属管)',
        re.IGNORECASE
    )
    # 变截面段 "x米处直径变为ym"
    PATTERN_SEGMENT_CHANGE = re.compile(
        r'(?:在|于|从)?\s*(\d+\.?\d*)\s*(?:m|米)\s*(?:处|高度)?\s*'
        r'(?:直径|变径|外径)\s*(?:变?为|是|约)?\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )

    def __init__(self):
        self._id_counter = 1

    # =========================================================================
    # 主解析接口
    # =========================================================================

    def parse(self, text: str, model_id: str = "chimney_nl") -> ChimneyModel:
        """将自然语言解析为烟囱模型

        Args:
            text: 自然语言描述
            model_id: 模型 ID

        Returns:
            ChimneyModel 实例
        """
        params = self._extract_params(text)
        return self._build_model(params, model_id)

    def _extract_params(self, text: str) -> dict:
        """提取所有烟囱参数"""
        params = {}

        # 总高度
        h_match = self.PATTERN_HEIGHT.search(text)
        if h_match:
            params["total_height"] = float(h_match.group(1))
        else:
            # 通用高度: "50m烟囱", "80米烟囱" 等
            generic_h = re.search(r'(\d+\.?\d*)\s*(?:m|米)\s*(?:烟囱|的烟囱)?', text)
            params["total_height"] = float(generic_h.group(1)) if generic_h else 60.0

        # 底部直径
        bd_match = self.PATTERN_BASE_DIAMETER.search(text)
        params["base_diameter"] = float(bd_match.group(1)) if bd_match else 5.0

        # 顶部直径
        td_match = self.PATTERN_TOP_DIAMETER.search(text)
        params["top_diameter"] = float(td_match.group(1)) if td_match else 3.0

        # 壁厚
        wt_match = self.PATTERN_WALL_THICKNESS.search(text)
        params["wall_thickness"] = float(wt_match.group(1)) if wt_match else 0.3

        # 混凝土等级
        cg_match = self.PATTERN_CONCRETE_GRADE.search(text)
        params["concrete_grade"] = cg_match.group(1) if cg_match else "C40"

        # 配筋率
        rr_match = self.PATTERN_REBAR_RATIO.search(text)
        params["reinforcement_ratio"] = (
            float(rr_match.group(1)) / 100
        ) if rr_match else 0.008

        # 切口高度
        nh_match = self.PATTERN_NOTCH_HEIGHT.search(text)
        params["notch_height"] = float(nh_match.group(1)) if nh_match else 5.0

        # 切口角度
        na_match = self.PATTERN_NOTCH_ANGLE.search(text)
        params["notch_angle"] = float(na_match.group(1)) if na_match else 45.0

        # 定向方向
        di_match = self.PATTERN_DIRECTION.search(text)
        params["direction"] = float(di_match.group(1)) if di_match else 0.0

        # 顶部附属结构
        params["attachments"] = self._extract_attachments(text)

        # 变截面段
        params["segments_data"] = self._extract_segments(text, params)

        logger.info(f"烟囱解析参数: {params}")
        return params

    # =========================================================================
    # 附属结构提取
    # =========================================================================

    def _extract_attachments(self, text: str) -> list[dict]:
        """提取顶部附属结构"""
        attachments = []

        for match in self.PATTERN_ATTACHMENT.finditer(text):
            height = float(match.group(1))
            steel_type = match.group(2) if match.group(2) else ""

            material = "Q235"
            for grade in STEEL_GRADES:
                if grade in steel_type.upper():
                    material = grade
                    break

            # 判断类型
            full = match.group(0)
            att_name = "钢制排气筒"
            if "排气管" in full:
                att_name = "排气管"
            elif "钢帽" in full:
                att_name = "钢帽"

            attachments.append({
                "name": att_name,
                "height": height,
                "diameter": 1.0,  # 默认 1m
                "material": material,
            })

        return attachments

    # =========================================================================
    # 变截面段提取
    # =========================================================================

    def _extract_segments(self, text: str, params: dict) -> list[dict]:
        """从文本提取变截面段信息

        如果没有显式变截面描述，则创建单一匀变截面段。
        """
        segments = []
        changes = list(self.PATTERN_SEGMENT_CHANGE.finditer(text))

        total_h = params["total_height"]
        base_d = params["base_diameter"]
        top_d = params["top_diameter"]
        wall_t = params["wall_thickness"]
        grade = params["concrete_grade"]
        rebar = params["reinforcement_ratio"]

        if not changes:
            # 单一匀变截面：从底到顶线性变化
            segments.append({
                "bottom_elevation": 0.0,
                "top_elevation": total_h,
                "outer_diameter_bottom": base_d,
                "outer_diameter_top": top_d,
                "wall_thickness": wall_t,
                "material": grade,
                "reinforcement_ratio": rebar,
            })
            return segments

        # 多段变截面
        sorted_changes = sorted(
            changes,
            key=lambda m: float(m.group(1))
        )
        change_points = []
        for c in changes:
            change_points.append({
                "elevation": float(c.group(1)),
                "diameter": float(c.group(2)),
            })

        change_points.sort(key=lambda p: p["elevation"])

        # 第一段: 0 -> 第一个变径点
        prev_elev = 0.0
        prev_d = base_d

        for cp in change_points:
            segments.append({
                "bottom_elevation": prev_elev,
                "top_elevation": cp["elevation"],
                "outer_diameter_bottom": prev_d,
                "outer_diameter_top": cp["diameter"],
                "wall_thickness": wall_t,
                "material": grade,
                "reinforcement_ratio": rebar,
            })
            prev_elev = cp["elevation"]
            prev_d = cp["diameter"]

        # 最后一段: 最后一个变径点 -> 顶部
        if prev_elev < total_h:
            segments.append({
                "bottom_elevation": prev_elev,
                "top_elevation": total_h,
                "outer_diameter_bottom": prev_d,
                "outer_diameter_top": top_d,
                "wall_thickness": wall_t,
                "material": grade,
                "reinforcement_ratio": rebar,
            })

        return segments

    # =========================================================================
    # 模型构建
    # =========================================================================

    def _build_model(self, params: dict, model_id: str) -> ChimneyModel:
        """根据参数构建 ChimneyModel"""
        # 构建附属结构
        attachments = [
            ChimneyAttachment(**att)
            for att in params.get("attachments", [])
        ]

        # 构建变截面段
        segments = []
        for i, seg in enumerate(params.get("segments_data", []), start=1):
            seg["id"] = i
            segments.append(ChimneySegment(**seg))

        name = (
            f"{params['concrete_grade']}钢筋混凝土烟囱 "
            f"(高{params['total_height']}m, "
            f"底径{params['base_diameter']}m→顶径{params['top_diameter']}m)"
        )

        return ChimneyModel(
            model_id=model_id,
            name=name,
            total_height=params["total_height"],
            segments=segments,
            attachments=attachments,
            base_diameter=params["base_diameter"],
            top_diameter=params["top_diameter"],
            notch_height=params["notch_height"],
            notch_angle=params["notch_angle"],
            notion_direction=params["direction"],
        )


# ============================================================================
# 工具函数
# ============================================================================

def create_chimney_from_text(
    text: str,
    model_id: str = "chimney_nl"
) -> ChimneyModel:
    """从自然语言创建烟囱模型（便捷函数）"""
    parser = ChimneyParser()
    return parser.parse(text, model_id)
