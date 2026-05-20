"""计算引擎抽象基类

定义所有求解器适配器的通用接口。
遵循洁净室原则，确保架构一致性。
"""
from abc import ABC, abstractmethod
from typing import Optional
from core.models import StructureModel, AnalysisResult, DemolitionAction


class BaseEngineAdapter(ABC):
    """计算引擎适配器抽象基类

    所有求解器 (Frame3DD, OpenSeesPy) 必须继承此类并实现其接口。
    这样可以保证双轨校验机制的一致性和可替换性。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """引擎版本"""
        pass

    @abstractmethod
    async def validate_model(self, model: StructureModel) -> tuple[bool, Optional[str]]:
        """验证结构模型的有效性

        Args:
            model: 待验证的结构模型

        Returns:
            (is_valid, error_message) 元组
        """
        pass

    @abstractmethod
    async def run_static_analysis(
        self,
        model: StructureModel,
        load_case: str = "DeadLoad"
    ) -> AnalysisResult:
        """执行静力分析

        Args:
            model: 结构模型
            load_case: 荷载工况名称

        Returns:
            分析结果
        """
        pass

    @abstractmethod
    async def run_dynamic_analysis(
        self,
        model: StructureModel,
        demolition_action: DemolitionAction
    ) -> AnalysisResult:
        """执行动力分析 (拆除模拟)

        Args:
            model: 结构模型
            demolition_action: 拆除动作

        Returns:
            分析结果
        """
        pass

    @abstractmethod
    async def check_stability(
        self,
        model: StructureModel,
        threshold: float = 0.05
    ) -> tuple[bool, float]:
        """检查结构稳定性

        Args:
            model: 结构模型
            threshold: 位移阈值 (m)

        Returns:
            (is_stable, max_displacement) 元组
        """
        pass
