using UnityEngine;

namespace IronFall.Physics
{
    /// <summary>
    /// AMD 4500U 性能优化管理器
    /// 根据项目宪法第七章配置 Unity 物理和渲染参数
    /// 
    /// 优化策略：
    /// - 限制模型单元数 < 500
    /// - 物理步长 30 FPS (Fixed Timestep = 0.033)
    /// - URP Low Quality 设置
    /// </summary>
    public class PerformanceOptimizer : MonoBehaviour
    {
        [Header("物理优化")]
        [SerializeField] private float fixedTimestep = 0.033f;      // 30 FPS
        [SerializeField] private float maxTimestep = 0.1f;           // 防止卡顿
        [SerializeField] private int maxElementCount = 500;         // 最大构件数
        [SerializeField] private bool useAutoSimulate = true;

        [Header("渲染优化")]
        [SerializeField] private bool limitFPS = true;
        [SerializeField] private int targetFPS = 30;
        [SerializeField] private int maxPixelLights = 1;
        [SerializeField] private bool disableAntiAliasing = true;
        [SerializeField] private bool disableShadows = true;

        // 当前状态
        private float _averageFrameTime;
        private int _currentElementCount;

        /// <summary>
        /// 初始化优化设置
        /// </summary>
        private void Start()
        {
            ApplyPhysicsOptimizations();
            ApplyRenderOptimizations();
            
            Debug.Log("[PerformanceOptimizer] Optimizations applied for AMD 4500U");
        }

        /// <summary>
        /// 应用物理优化
        /// </summary>
        public void ApplyPhysicsOptimizations()
        {
            // 设置固定时间步长
            Time.fixedDeltaTime = fixedTimestep;
            Time.maximumDeltaTime = maxTimestep;

            // 禁用自动模拟（由 DemolitionController 控制）
            if (!useAutoSimulate)
            {
                Physics.autoSimulation = false;
            }

            Debug.Log($"[PerformanceOptimizer] Physics: FixedTimestep={fixedTimestep}, MaxTimestep={maxTimestep}");
        }

        /// <summary>
        /// 应用渲染优化
        /// </summary>
        public void ApplyRenderOptimizations()
        {
            // 限制帧率
            if (limitFPS)
            {
                Application.targetFrameRate = targetFPS;
            }

            // 设置质量等级
            QualitySettings.SetQualityLevel(0, true); // Lowest

            // 获取 URP 设置
            var urpAsset = UnityEngine.Rendering.Universal.UniversalRenderPipeline.asset;
            if (urpAsset != null)
            {
                // 光照限制
                urpAsset.maxNumLightsPerCell = 1;

                // 禁用阴影
                urpAsset.supportsShadows = false;
                
                // 降低后处理质量
                urpAsset.msaaSampleCount = 1; // 禁用 MSAA
            }

            // 全局设置
            QualitySettings.pixelLightCount = maxPixelLights;
            QualitySettings.antiAliasing = disableAntiAliasing ? 0 : 1;
            QualitySettings.shadowQuality = disableShadows ? ShadowQuality.Disable : ShadowQuality.High;

            // 全局粒子设置
            ParticleSystem[] particles = FindObjectsOfType<ParticleSystem>();
            foreach (var ps in particles)
            {
                var main = ps.main;
                main.maxParticles = Mathf.Min(main.maxParticles, 100);
            }

            Debug.Log($"[PerformanceOptimizer] Render: TargetFPS={targetFPS}, MaxLights={maxPixelLights}");
        }

        /// <summary>
        /// 更新性能监控
        /// </summary>
        private void Update()
        {
            // 帧率监控（每 60 帧更新一次）
            if (Time.frameCount % 60 == 0)
            {
                _averageFrameTime = Time.unscaledDeltaTime * 1000f;
                
                if (_averageFrameTime > 50f) // 超过 50ms 警告
                {
                    Debug.LogWarning($"[PerformanceOptimizer] Frame time high: {_averageFrameTime:F2}ms");
                }
            }
        }

        /// <summary>
        /// 检查是否超出元素数量限制
        /// </summary>
        public bool IsWithinElementLimit(int count)
        {
            return count <= maxElementCount;
        }

        /// <summary>
        /// 获取建议的简化等级
        /// </summary>
        public int GetSimplificationLevel()
        {
            if (_currentElementCount > 400) return 3;
            if (_currentElementCount > 200) return 2;
            if (_currentElementCount > 100) return 1;
            return 0;
        }

        /// <summary>
        /// 获取当前帧时间（毫秒）
        /// </summary>
        public float CurrentFrameTime => _averageFrameTime;

        /// <summary>
        /// 获取当前 FPS
        /// </summary>
        public float CurrentFPS => 1000f / _averageFrameTime;

        /// <summary>
        /// 设置元素数量
        /// </summary>
        public void SetElementCount(int count)
        {
            _currentElementCount = count;
        }
    }
}
