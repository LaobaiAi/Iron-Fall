"""自然语言结构解析器

将自然语言描述解析为标准化 StructureModel 数据。
支持两种模式：
1. 关键词规则解析（快速，无需 LLM）- 支持常见结构模式
2. LLM 辅助解析（精确，需要 API）- 支持复杂描述

解析能力覆盖：
- 框架结构：层数、跨度、层高、开间
- 构件类型：柱 (Column)、梁 (Beam)、支撑 (Brace)
- 支撑形式：X 型斜撑、V 型撑、K 型撑、人字撑
- 截面规格：H 型钢、箱型截面
- 材料等级：Q235, Q355, Q390
"""
import re
import json
import logging
from typing import Optional
from core.models import (
    StructureModel, Node, Element, Section, Material, ElementType
)

logger = logging.getLogger(__name__)

# ============================================================================
# 预设截面库 (常用 H 型钢)
# ============================================================================

STANDARD_SECTIONS = {
    "H200x150": {"A": 3976, "Iy": 2.69e7, "Iz": 5.07e6, "J": 5.2e4},
    "H250x175": {"A": 5537, "Iy": 5.79e7, "Iz": 1.08e7, "J": 1.5e5},
    "H300x200": {"A": 7608, "Iy": 1.14e8, "Iz": 1.94e7, "J": 3.42e6},
    "H350x250": {"A": 10150, "Iy": 2.10e8, "Iz": 3.65e7, "J": 8.5e5},
    "H400x200": {"A": 10000, "Iy": 2.50e8, "Iz": 3.30e8, "J": 1.00e7},
    "H400x300": {"A": 13330, "Iy": 3.75e8, "Iz": 6.05e7, "J": 2.0e6},
    "H450x300": {"A": 15040, "Iy": 5.28e8, "Iz": 8.11e7, "J": 3.0e6},
    "H500x300": {"A": 16350, "Iy": 6.89e8, "Iz": 1.04e8, "J": 4.5e6},
    "H600x300": {"A": 18850, "Iy": 1.12e9, "Iz": 1.55e8, "J": 8.0e6},
}

# ============================================================================
# 预设材料库
# ============================================================================

STANDARD_MATERIALS = {
    "Q235": {"E": 206000, "fy": 235, "density": 7850},
    "Q355": {"E": 206000, "fy": 355, "density": 7850},
    "Q390": {"E": 206000, "fy": 390, "density": 7850},
    "Q420": {"E": 206000, "fy": 420, "density": 7850},
}


class StructureParser:
    """自然语言结构解析器

    支持从自然语言描述生成完整 StructureModel。
    内置钢结构工程知识，覆盖常见框架结构模式。
    """

    # 结构描述关键词模式
    PATTERN_STORIES = re.compile(
        r'(\d+)\s*(?:层|楼|story|stories|floor|floors)',
        re.IGNORECASE
    )
    PATTERN_STORY_HEIGHT = re.compile(
        r'(?:首层|底层|第一层|1层|ground)\s*(?:层?高)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_TYPICAL_HEIGHT = re.compile(
        r'(?:标准层|典型层|标准|typical)\s*(?:层?高)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_SPAN_X = re.compile(
        r'(?:跨度|开间|x\s*方向|x\s*向|span)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_SPAN_Y = re.compile(
        r'(?:进深|y\s*方向|y\s*向|depth)\s*(\d+\.?\d*)\s*(?:m|米)',
        re.IGNORECASE
    )
    PATTERN_BAYS_X = re.compile(
        r'(\d+)\s*(?:跨|开间|bay|bays)',
        re.IGNORECASE
    )
    PATTERN_BAYS_Y = re.compile(
        r'(\d+)\s*(?:进深|depth\s*bay)',
        re.IGNORECASE
    )
    PATTERN_BRACE_TYPE = re.compile(
        r'(X\s*型|V\s*型|K\s*型|人字|交叉|斜撑|brac)',
        re.IGNORECASE
    )
    PATTERN_SECTION = re.compile(
        r'H\s*(\d+)\s*[x×X]\s*(\d+)',
        re.IGNORECASE
    )
    PATTERN_MATERIAL = re.compile(
        r'(Q\d{3})',
        re.IGNORECASE
    )

    def __init__(self):
        self._section_counter = 0
        self._material_counter = 0

    # =========================================================================
    # 主解析接口
    # =========================================================================

    def parse(self, text: str, model_id: str = "nl_model") -> StructureModel:
        """将自然语言解析为结构模型

        Args:
            text: 自然语言描述
            model_id: 模型 ID

        Returns:
            StructureModel 实例
        """
        params = self._extract_parameters(text)
        return self._build_model(params, model_id)

    def parse_with_llm(
        self,
        text: str,
        llm=None,
        model_id: str = "nl_llm_model"
    ) -> Optional[StructureModel]:
        """使用 LLM 辅助解析复杂描述

        Args:
            text: 自然语言描述
            llm: LangChain LLM 实例
            model_id: 模型 ID

        Returns:
            StructureModel 或 None（解析失败时）
        """
        if llm is None:
            return None

        prompt = self._build_llm_prompt(text)
        try:
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            params = self._parse_llm_response(content)
            if params:
                return self._build_model(params, model_id)
        except Exception as e:
            logger.warning(f"LLM 解析失败: {e}")

        # 降级到规则解析
        return self.parse(text, model_id)

    # =========================================================================
    # 参数提取
    # =========================================================================

    def _extract_parameters(self, text: str) -> dict:
        """提取结构参数

        Returns:
            {
                "num_stories": int,
                "ground_height": float,
                "typical_height": float,
                "span_x": float,
                "span_y": float,
                "num_bays_x": int,
                "num_bays_y": int,
                "brace_type": str | None,
                "section_name": str,
                "material_name": str,
            }
        """
        params = {}

        # 层数
        stories_match = self.PATTERN_STORIES.search(text)
        params["num_stories"] = int(stories_match.group(1)) if stories_match else 3

        # 层高
        ground_match = self.PATTERN_STORY_HEIGHT.search(text)
        typical_match = self.PATTERN_TYPICAL_HEIGHT.search(text)

        # 全局层高匹配（如"层高3.6m"）
        global_height = re.search(r'层?高\s*(\d+\.?\d*)\s*(?:m|米)', text)
        default_height = float(global_height.group(1)) if global_height and not (ground_match or typical_match) else 3.6

        params["ground_height"] = float(ground_match.group(1)) if ground_match else 4.5
        params["typical_height"] = float(typical_match.group(1)) if typical_match else default_height

        # 跨度和开间
        span_x_match = self.PATTERN_SPAN_X.search(text)
        span_y_match = self.PATTERN_SPAN_Y.search(text)

        # 如果没有指定，尝试通用数值: "6m" 等
        generic_spans = re.findall(r'(\d+\.?\d*)\s*(?:m|米)\s*(?:跨度|开间|进深)?', text)
        params["span_x"] = float(span_x_match.group(1)) if span_x_match else (
            float(generic_spans[0]) if generic_spans else 6.0
        )
        params["span_y"] = float(span_y_match.group(1)) if span_y_match else params["span_x"]

        # 跨数
        bays_x_match = self.PATTERN_BAYS_X.search(text)
        bays_y_match = self.PATTERN_BAYS_Y.search(text)
        params["num_bays_x"] = int(bays_x_match.group(1)) if bays_x_match else (
            2 if "多跨" in text else 1
        )
        params["num_bays_y"] = int(bays_y_match.group(1)) if bays_y_match else 1

        # 支撑类型
        brace_match = self.PATTERN_BRACE_TYPE.search(text)
        if brace_match:
            bt = brace_match.group(1).upper()
            if "X" in bt or "交叉" in bt:
                params["brace_type"] = "X"
            elif "V" in bt:
                params["brace_type"] = "V"
            elif "K" in bt:
                params["brace_type"] = "K"
            elif "人" in bt:
                params["brace_type"] = "inverted_v"
            else:
                params["brace_type"] = "X"
        else:
            params["brace_type"] = None if "斜撑" not in text and "支撑" not in text and "brac" not in text.lower() else "X"

        # 截面
        section_match = self.PATTERN_SECTION.search(text)
        params["section_name"] = f"H{section_match.group(1)}x{section_match.group(2)}" if section_match else "H400x200"

        # 材料
        material_match = self.PATTERN_MATERIAL.search(text)
        params["material_name"] = material_match.group(1) if material_match else "Q355"

        logger.info(f"解析参数: {params}")
        return params

    # =========================================================================
    # 模型构建
    # =========================================================================

    def _build_model(self, params: dict, model_id: str) -> StructureModel:
        """根据参数构建完整 StructureModel"""
        ns = params["num_stories"]
        gh = params["ground_height"]
        th = params["typical_height"]
        sx = params["span_x"]
        sy = params["span_y"]
        nbx = params["num_bays_x"]
        nby = params["num_bays_y"]
        bt = params.get("brace_type")
        sn = params["section_name"]
        mn = params["material_name"]

        # 截面和材料
        section_data = STANDARD_SECTIONS.get(
            sn, STANDARD_SECTIONS["H400x200"]
        )
        material_data = STANDARD_MATERIALS.get(
            mn, STANDARD_MATERIALS["Q355"]
        )

        section = Section(
            id=1, name=sn,
            A=section_data["A"],
            Iy=section_data["Iy"],
            Iz=section_data["Iz"],
            J=section_data["J"]
        )
        material = Material(
            id=1, name=mn,
            E=material_data["E"],
            fy=material_data["fy"],
            density=material_data["density"]
        )

        # 生成节点
        nodes = self._generate_nodes(ns, gh, th, sx, sy, nbx, nby)

        # 节点 ID 映射
        node_ids = {node.id: node for node in nodes}

        # 生成构件
        elements = self._generate_elements(
            nodes, ns, nbx, nby, section.id, material.id
        )

        # 生成支撑
        if bt:
            brace_elements = self._generate_braces(
                nodes, node_ids, ns, sx, sy, nbx, nby, bt,
                section.id, material.id
            )
            elements.extend(brace_elements)

        name = f"{ns}层{mn}钢框架"
        if bt:
            name += f"({bt}型斜撑)"

        return StructureModel(
            model_id=model_id,
            name=name,
            nodes=nodes,
            elements=elements,
            sections=[section],
            materials=[material]
        )

    def _generate_nodes(
        self,
        num_stories: int,
        ground_height: float,
        typical_height: float,
        span_x: float,
        span_y: float,
        num_bays_x: int,
        num_bays_y: int
    ) -> list[Node]:
        """生成网格节点"""
        nodes = []
        node_id = 1

        for story in range(num_stories + 1):  # 含基础
            if story == 0:
                z = 0.0
            elif story == 1:
                z = ground_height
            else:
                z = ground_height + (story - 1) * typical_height

            for iy in range(num_bays_y + 1):
                y = iy * span_y
                for ix in range(num_bays_x + 1):
                    x = ix * span_x

                    # 基础节点固定
                    if story == 0:
                        restraint = [True, True, True, False, False, False]
                    else:
                        restraint = [False] * 6

                    nodes.append(Node(
                        id=node_id, x=x, y=y, z=z,
                        restraint=restraint
                    ))
                    node_id += 1

        return nodes

    def _generate_elements(
        self,
        nodes: list[Node],
        num_stories: int,
        num_bays_x: int,
        num_bays_y: int,
        section_id: int,
        material_id: int
    ) -> list[Element]:
        """生成柱和梁构件"""
        elements = []
        elem_id = 1

        # 每行节点数
        nodes_per_row = (num_bays_x + 1) * (num_bays_y + 1)

        for story in range(num_stories):
            base_start = story * nodes_per_row + 1
            top_start = (story + 1) * nodes_per_row + 1

            # 柱: 每个网格点
            for iy in range(num_bays_y + 1):
                for ix in range(num_bays_x + 1):
                    idx = iy * (num_bays_x + 1) + ix
                    elements.append(Element(
                        id=elem_id,
                        node_i_id=base_start + idx,
                        node_j_id=top_start + idx,
                        section_id=section_id,
                        material_id=material_id,
                        element_type=ElementType.COLUMN
                    ))
                    elem_id += 1

            # 梁 (X 方向)
            for iy in range(num_bays_y + 1):
                for ix in range(num_bays_x):
                    idx = iy * (num_bays_x + 1) + ix
                    elements.append(Element(
                        id=elem_id,
                        node_i_id=top_start + idx,
                        node_j_id=top_start + idx + 1,
                        section_id=section_id,
                        material_id=material_id,
                        element_type=ElementType.BEAM
                    ))
                    elem_id += 1

            # 梁 (Y 方向)
            for iy in range(num_bays_y):
                for ix in range(num_bays_x + 1):
                    idx = iy * (num_bays_x + 1) + ix
                    elements.append(Element(
                        id=elem_id,
                        node_i_id=top_start + idx,
                        node_j_id=top_start + idx + (num_bays_x + 1),
                        section_id=section_id,
                        material_id=material_id,
                        element_type=ElementType.BEAM
                    ))
                    elem_id += 1

        return elements

    def _generate_braces(
        self,
        nodes: list[Node],
        node_ids: dict,
        num_stories: int,
        span_x: float,
        span_y: float,
        num_bays_x: int,
        num_bays_y: int,
        brace_type: str,
        section_id: int,
        material_id: int
    ) -> list[Element]:
        """生成支撑构件"""
        braces = []
        elem_id_offset = 1000  # 支撑 ID 从 1000 开始

        nodes_per_row = (num_bays_x + 1) * (num_bays_y + 1)

        # 支撑加在外围框架的 X-Z 平面上
        for story in range(num_stories):
            base_start = story * nodes_per_row + 1
            top_start = (story + 1) * nodes_per_row + 1

            # 两侧外立面 (y=0 和 y=max)
            for y_idx in [0, num_bays_y]:
                y_offset = y_idx * (num_bays_x + 1)

                for x_idx in range(num_bays_x):
                    idx_bl = y_offset + x_idx         # 底部左
                    idx_br = y_offset + x_idx + 1      # 底部右
                    idx_tl = y_offset + x_idx + nodes_per_row  # 顶部左
                    idx_tr = y_offset + x_idx + 1 + nodes_per_row  # 顶部右

                    base_bl = base_start + idx_bl
                    base_br = base_start + idx_br
                    top_tl = top_start + idx_tl - nodes_per_row
                    top_tr = top_start + idx_tr - nodes_per_row

                    # 实际顶部节点在顶层
                    top_bl = base_start + nodes_per_row + idx_bl
                    top_br = base_start + nodes_per_row + idx_br

                    if brace_type == "X":
                        # X 型: 两条交叉支撑
                        braces.append(Element(
                            id=9000 + len(braces) + 1,
                            node_i_id=base_bl if story == 0 else (
                                story * nodes_per_row + 1 + idx_bl
                            ),
                            node_j_id=top_tr,
                            section_id=section_id, material_id=material_id,
                            element_type=ElementType.BRACE
                        ))
                        braces.append(Element(
                            id=9000 + len(braces) + 1,
                            node_i_id=base_br if story == 0 else (
                                story * nodes_per_row + 1 + idx_br
                            ),
                            node_j_id=top_tl,
                            section_id=section_id, material_id=material_id,
                            element_type=ElementType.BRACE
                        ))
                    elif brace_type == "V":
                        # V 型: 从顶部两端到中间底部
                        braces.append(Element(
                            id=9000 + len(braces) + 1,
                            node_i_id=base_bl,
                            node_j_id=top_tl,
                            section_id=section_id, material_id=material_id,
                            element_type=ElementType.BRACE
                        ))
                    elif brace_type == "K":
                        # K 型
                        braces.append(Element(
                            id=9000 + len(braces) + 1,
                            node_i_id=base_bl,
                            node_j_id=top_tl,
                            section_id=section_id, material_id=material_id,
                            element_type=ElementType.BRACE
                        ))

        return braces

    # =========================================================================
    # LLM 辅助
    # =========================================================================

    def _build_llm_prompt(self, text: str) -> str:
        """构建 LLM 解析 prompt"""
        return f"""你是一位钢结构工程专家。请将以下自然语言描述解析为钢结构模型参数。

描述: "{text}"

请输出 JSON 格式，包含以下字段：
{{
    "num_stories": int (层数, 默认3),
    "ground_height": float (首层层高 m, 默认4.5),
    "typical_height": float (标准层层高 m, 默认3.6),
    "span_x": float (X方向跨度 m, 默认6.0),
    "span_y": float (Y方向进深 m, 默认6.0),
    "num_bays_x": int (X方向跨数, 默认1),
    "num_bays_y": int (Y方向跨数, 默认1),
    "brace_type": "X" | "V" | "K" | "none" (支撑类型, 默认"none"),
    "section_name": str (如 "H400x200", 默认"H400x200"),
    "material_name": str (如 "Q355", 默认"Q355")
}}

只输出 JSON，不要添加任何其他文字。"""

    def _parse_llm_response(self, content: str) -> Optional[dict]:
        """解析 LLM 响应"""
        try:
            # 提取 JSON
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            elif "{" in content:
                json_str = content[content.index("{"):content.rindex("}") + 1]
            else:
                json_str = content

            params = json.loads(json_str)
            # 验证必要字段
            required = ["num_stories", "ground_height", "typical_height",
                       "span_x", "span_y", "num_bays_x", "num_bays_y"]
            for key in required:
                if key not in params:
                    params[key] = {
                        "num_stories": 3, "ground_height": 4.5,
                        "typical_height": 3.6, "span_x": 6.0, "span_y": 6.0,
                        "num_bays_x": 1, "num_bays_y": 1
                    }[key]

            return params
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"LLM 响应解析失败: {e}")
            return None


# ============================================================================
# 工具函数
# ============================================================================

def create_structure_from_text(
    text: str,
    model_id: str = "nl_model",
    use_llm: bool = False,
    llm=None
) -> StructureModel:
    """从自然语言文本创建结构模型（便捷函数）"""
    parser = StructureParser()
    if use_llm and llm:
        result = parser.parse_with_llm(text, llm, model_id)
        if result:
            return result
    return parser.parse(text, model_id)
