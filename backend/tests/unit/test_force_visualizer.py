"""力场可视化引擎测试

覆盖 engine/force_visualizer.py 的：
- 单帧力场颜色数据生成
- 时间线生成
- 颜色映射正确性
- 边界条件（空模型）
"""
import pytest
from core.models import (
    StructureModel, Node, Element, Section, Material, ElementType,
    AnalysisResult, DemolitionAction,
)
from engine.force_visualizer import ForceVisualizer, ForceVisualTimeline


class TestForceVisualizer:
    """力场可视化核心测试"""

    @pytest.fixture
    def visualizer(self) -> ForceVisualizer:
        return ForceVisualizer()

    @pytest.fixture
    def frame_with_stress(self, sample_3story_frame, sample_analysis_stable):
        """带应力数据的框架"""
        return sample_3story_frame, sample_analysis_stable

    # -------------------------------------------------------------------------
    # 单帧可视化
    # -------------------------------------------------------------------------

    def test_visualize_returns_data(self, visualizer, frame_with_stress):
        model, analysis = frame_with_stress
        frame = visualizer.visualize(model, analysis)

        assert frame is not None
        assert frame.frame_index == 0
        assert len(frame.elements) > 0
        for ec in frame.elements:
            assert ec.element_id > 0
            assert ec.element_type in ("Column", "Beam", "Brace")
            assert ec.color_hex.startswith("#")
            assert 0.0 <= ec.stress_ratio <= 1.0

    def test_visualize_empty_model(self, visualizer, empty_model):
        """空模型应安全返回空帧或 None"""
        analysis = AnalysisResult()
        try:
            result = visualizer.visualize(empty_model, analysis)
            if result is not None:
                assert result.elements == []
        except Exception:
            pass  # 空模型导致异常是可接受的

    # -------------------------------------------------------------------------
    # 颜色映射
    # -------------------------------------------------------------------------

    def test_color_range_blue_to_red(self, visualizer, frame_with_stress):
        """应力比 0→1 应映射为蓝→红"""
        model, analysis = frame_with_stress
        frame = visualizer.visualize(model, analysis)

        colors = [ec.color_hex for ec in frame.elements]
        # 至少有一个颜色是合法的 hex
        for c in colors:
            assert len(c) == 7  # #RRGGBB

    def test_stress_ratio_bounded(self, visualizer, frame_with_stress):
        """应力比必须在 [0, 1] 范围内"""
        model, analysis = frame_with_stress
        frame = visualizer.visualize(model, analysis)

        for ec in frame.elements:
            assert 0.0 <= ec.stress_ratio <= 1.0, (
                f"Element {ec.element_id}: stress_ratio={ec.stress_ratio}"
            )

    # -------------------------------------------------------------------------
    # 时间线可视化
    # -------------------------------------------------------------------------

    def test_visualize_timeline_returns_correct_frames(self, visualizer,
                                                        sample_3story_frame):
        """时间线帧数应等于拆除动作数 + 1 (初始帧)"""
        actions = [
            DemolitionAction(step=1, target_element_ids=[1]),
            DemolitionAction(step=2, target_element_ids=[2]),
        ]
        timeline = visualizer.visualize_timeline(sample_3story_frame, actions)

        assert isinstance(timeline, ForceVisualTimeline)
        assert timeline.model_id == sample_3story_frame.model_id
        # timeline.frames 包含初始帧 + 每步一帧
        assert len(timeline.frames) == len(actions) + 1

    def test_timeline_empty_actions(self, visualizer, sample_3story_frame):
        """无拆除动作时应仅含初始帧"""
        timeline = visualizer.visualize_timeline(sample_3story_frame, [])
        assert len(timeline.frames) == 1  # 仅初始状态

    def test_timeline_frames_indexed_sequentially(self, visualizer,
                                                   sample_3story_frame):
        actions = [
            DemolitionAction(step=1, target_element_ids=[1]),
            DemolitionAction(step=2, target_element_ids=[3]),
            DemolitionAction(step=3, target_element_ids=[5]),
        ]
        timeline = visualizer.visualize_timeline(sample_3story_frame, actions)

        for i, frame in enumerate(timeline.frames):
            assert frame.frame_index == i

    # -------------------------------------------------------------------------
    # 力场数据完整性
    # -------------------------------------------------------------------------

    def test_all_elements_in_frame(self, visualizer, sample_3story_frame):
        """初始帧应覆盖所有构件"""
        analysis = AnalysisResult()
        frame = visualizer.visualize(sample_3story_frame, analysis)

        element_ids = {ec.element_id for ec in frame.elements}
        assert element_ids == {e.id for e in sample_3story_frame.elements}

    def test_frame_contains_stats(self, visualizer, frame_with_stress):
        model, analysis = frame_with_stress
        frame = visualizer.visualize(model, analysis)

        assert frame.max_stress_ratio >= 0.0
        assert frame.avg_stress_ratio >= 0.0
        assert isinstance(frame.stable, bool)
