/**
 * Iron-Fall Unity Frontend
 * 
 * Phase 3: 实时可视化 (Week 3) —— 3秒动画推演
 * 
 * 项目结构:
 * - Assets/Scripts/
 *   - Network/         # WebSocket 通信
 *   - Physics/         # 物理控制器
 * 
 * 核心组件:
 * - IronFallWebSocket:     WebSocket 客户端，与后端 FastAPI 通信
 * - DemolitionController:  拆除物理控制器，执行拆除动作
 * - StructureBuilder:       钢框架结构构建器
 * - PerformanceOptimizer:   AMD 4500U 性能优化
 * 
 * 使用方法:
 * 1. 导入 WebSocketSharp 包 (com.unity.package-manager)
 * 2. 在场景中创建空物体 "IronFallManager"
 * 3. 添加 IronFallSceneManager 组件
 * 4. 配置 WebSocket 服务器地址 (默认 ws://localhost:8000/ws/demolition)
 * 5. 确保后端 FastAPI 服务运行中
 * 
 * 性能目标 (项目宪法):
 * - 端到端延迟 ≤ 3 秒
 * - 物理更新 30 FPS (Fixed Timestep = 0.033)
 * - 最大构件数 < 500
 */
namespace IronFall
{
    public static class Version
    {
        public const string CURRENT = "1.0.0";
        public const string TARGET_LATENCY_MS = "3000";
    }
}
