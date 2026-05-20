using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using IronFall.Network;

namespace IronFall.Physics
{
    /// <summary>
    /// 拆除物理控制器
    /// 核心职责：将后端 DemolitionAction 映射为 Unity Rigidbody 物理操作
    /// 
    /// 设计原则（项目宪法 6.2）：
    /// - 单一职责：每个 MonoBehaviour 只负责一个功能
    /// - 性能优先：在 FixedUpdate() 中处理物理
    /// - 引用缓存：在 Start() 中缓存所有组件引用
    /// </summary>
    public class DemolitionController : MonoBehaviour
    {
        [Header("WebSocket 连接")]
        [SerializeField] private IronFallWebSocket webSocket;

        [Header("物理参数 - AMD 4500U 优化")]
        [SerializeField] private float fixedTimestep = 0.033f;  // 30 FPS 物理更新
        [SerializeField] private float maxTimestep = 0.1f;       // 防止卡顿
        [SerializeField] private float maxDisplacementThreshold = 0.08f; // H/50 位移阈值

        [Header("结构模型引用")]
        [SerializeField] private Transform structureRoot;
        [SerializeField] private GameObject columnPrefab;
        [SerializeField] private GameObject beamPrefab;
        [SerializeField] private GameObject bracePrefab;

        // 缓存的组件引用
        private Dictionary<int, StructuralElement> _elementMap;
        private Dictionary<int, StructuralNode> _nodeMap;
        private SteelFrameModel _currentModel;

        // 状态机
        private enum ControllerState { Idle, Simulating, Paused }
        private ControllerState _state = ControllerState.Idle;

        // 事件
        public event Action<int, bool> OnStepComplete;
        public event Action OnSimulationComplete;
        public event Action<string> OnError;

        /// <summary>
        /// 当前状态
        /// </summary>
        public ControllerState State => _state;

        /// <summary>
        /// 初始化控制器
        /// </summary>
        private void Start()
        {
            // 优化：设置固定时间步长（AMD 4500U 优化）
            Time.fixedDeltaTime = fixedTimestep;
            Time.maximumDeltaTime = maxTimestep;

            // 初始化映射表
            _elementMap = new Dictionary<int, StructuralElement>();
            _nodeMap = new Dictionary<int, StructuralNode>();

            // 缓存 WebSocket 事件订阅
            if (webSocket != null)
            {
                webSocket.OnDemolitionResult += HandleDemolitionResult;
                webSocket.OnError += HandleWebSocketError;
            }
        }

        /// <summary>
        /// 清理
        /// </summary>
        private void OnDestroy()
        {
            if (webSocket != null)
            {
                webSocket.OnDemolitionResult -= HandleDemolitionResult;
                webSocket.OnError -= HandleWebSocketError;
            }
        }

        /// <summary>
        /// 加载结构模型
        /// </summary>
        public void LoadModel(SteelFrameModel model)
        {
            if (model == null)
            {
                OnError?.Invoke("Model is null");
                return;
            }

            _currentModel = model;

            // 清空旧映射
            _elementMap.Clear();
            _nodeMap.Clear();

            // 构建节点映射
            foreach (var node in model.nodes)
            {
                _nodeMap[node.id] = node;
            }

            Debug.Log($"[DemolitionController] Model loaded: {model.nodes.Count} nodes, {model.elements.Count} elements");
        }

        /// <summary>
        /// 执行拆除动作序列
        /// 根据项目宪法 3.3 数据流转协议：
        /// 当 Max_Displacement > Threshold 时发送 Collapse_Command
        /// </summary>
        public IEnumerator ExecuteDemolitionSequence(List<DemolitionAction> actions)
        {
            _state = ControllerState.Simulating;

            foreach (var action in actions)
            {
                yield return StartCoroutine(ExecuteSingleAction(action));

                // 等待物理稳定
                yield return new WaitForSeconds(fixedTimestep * 10);

                // 检查稳定性
                bool isStable = CheckStability();

                OnStepComplete?.Invoke(action.step, isStable);

                if (!isStable)
                {
                    Debug.Log($"[DemolitionController] Step {action.step}: Structure collapsed!");
                    yield break;
                }
            }

            _state = ControllerState.Idle;
            OnSimulationComplete?.Invoke();
            Debug.Log("[DemolitionController] Simulation complete - all steps stable");
        }

        /// <summary>
        /// 执行单个拆除动作
        /// </summary>
        private IEnumerator ExecuteSingleAction(DemolitionAction action)
        {
            Debug.Log($"[DemolitionController] Executing action step {action.step}: {action.actionType}");

            if (action.IsRemove)
            {
                yield return StartCoroutine(RemoveElementsRoutine(action.targetElementIds));
            }
            else if (action.IsApplyForce)
            {
                ApplyForceToElements(action.targetElementIds, action.GetForceVector());
            }

            yield return new WaitForFixedUpdate();
        }

        /// <summary>
        /// 移除构件协程
        /// </summary>
        private IEnumerator RemoveElementsRoutine(List<int> elementIds)
        {
            foreach (var id in elementIds)
            {
                if (_elementMap.TryGetValue(id, out var element) && element.GameObject != null)
                {
                    // 触发断裂动画效果
                    StartCoroutine(BreakElementRoutine(element));
                    yield return new WaitForSeconds(0.1f);
                }
            }
        }

        /// <summary>
        /// 构件断裂效果协程
        /// </summary>
        private IEnumerator BreakElementRoutine(StructuralElement element)
        {
            if (element.Rigidbody == null) yield break;

            // 禁用碰撞器（模拟断裂）
            var collider = element.GameObject.GetComponent<Collider>();
            if (collider != null)
            {
                collider.enabled = false;
            }

            // 添加随机初始速度模拟断裂
            var randomForce = new Vector3(
                UnityEngine.Random.Range(-5f, 5f),
                UnityEngine.Random.Range(-10f, -2f),
                UnityEngine.Random.Range(-5f, 5f)
            );
            element.Rigidbody.AddForce(randomForce, ForceMode.Impulse);
            element.Rigidbody.AddTorque(randomForce * 0.5f, ForceMode.Impulse);

            // 延迟销毁
            yield return new WaitForSeconds(3f);
            
            if (element.GameObject != null)
            {
                Destroy(element.GameObject);
            }
        }

        /// <summary>
        /// 向构件施加力
        /// </summary>
        private void ApplyForceToElements(List<int> elementIds, Vector3 force)
        {
            foreach (var id in elementIds)
            {
                if (_elementMap.TryGetValue(id, out var element) && element.Rigidbody != null)
                {
                    element.Rigidbody.AddForce(force, ForceMode.Impulse);
                }
            }
        }

        /// <summary>
        /// 检查结构稳定性
        /// 根据项目宪法：当计算位移 > H/50 时触发断裂动画
        /// </summary>
        private bool CheckStability()
        {
            float maxDisplacement = 0f;

            foreach (var kvp in _elementMap)
            {
                var element = kvp.Value;
                if (element.Rigidbody != null)
                {
                    var velocity = element.Rigidbody.velocity.magnitude;
                    var angularVelocity = element.Rigidbody.angularVelocity.magnitude;
                    
                    // 检查是否超出阈值
                    if (velocity > 10f || angularVelocity > 5f)
                    {
                        return false; // 失稳
                    }

                    maxDisplacement = Mathf.Max(maxDisplacement, velocity);
                }
            }

            return maxDisplacement < maxDisplacementThreshold;
        }

        /// <summary>
        /// 处理后端拆除结果
        /// </summary>
        private void HandleDemolitionResult(DemolitionResult result)
        {
            Debug.Log($"[DemolitionController] Received result: success={result.success}, latency={result.latency_ms}ms");

            if (!result.success)
            {
                OnError?.Invoke("Server reported failure");
                return;
            }

            // 解析分析数据
            var analysis = result.analysis;
            Debug.Log($"[DemolitionController] Max displacement: {analysis.max_displacement}, Status: {analysis.stability_status}");

            // 根据稳定性状态执行下一步
            if (analysis.is_safe)
            {
                // 稳定状态：更新 UI 显示
            }
            else
            {
                // 失稳状态：触发倒塌动画
                TriggerCollapseAnimation();
            }
        }

        /// <summary>
        /// 触发倒塌动画
        /// </summary>
        private void TriggerCollapseAnimation()
        {
            Debug.Log("[DemolitionController] Triggering collapse animation");

            foreach (var kvp in _elementMap)
            {
                var element = kvp.Value;
                if (element.Rigidbody != null)
                {
                    // 移除约束让其自由下落
                    element.Rigidbody.constraints = RigidbodyConstraints.None;
                    
                    // 添加重力加速
                    element.Rigidbody.AddForce(Vector3.down * 20f, ForceMode.Acceleration);
                }
            }
        }

        /// <summary>
        /// 处理 WebSocket 错误
        /// </summary>
        private void HandleWebSocketError(string error)
        {
            Debug.LogError($"[DemolitionController] WebSocket error: {error}");
            OnError?.Invoke(error);
        }

        /// <summary>
        /// 注册构件（由 StructureBuilder 调用）
        /// </summary>
        public void RegisterElement(StructuralElement element)
        {
            _elementMap[element.id] = element;
        }

        /// <summary>
        /// 获取构件
        /// </summary>
        public StructuralElement GetElement(int id)
        {
            return _elementMap.TryGetValue(id, out var element) ? element : null;
        }

        /// <summary>
        /// 获取节点
        /// </summary>
        public StructuralNode GetNode(int id)
        {
            return _nodeMap.TryGetValue(id, out var node) ? node : null;
        }

        /// <summary>
        /// 暂停模拟
        /// </summary>
        public void Pause()
        {
            _state = ControllerState.Paused;
            Time.timeScale = 0f;
        }

        /// <summary>
        /// 恢复模拟
        /// </summary>
        public void Resume()
        {
            _state = ControllerState.Simulating;
            Time.timeScale = 1f;
        }

        /// <summary>
        /// 重置模拟
        /// </summary>
        public void Reset()
        {
            _state = ControllerState.Idle;
            Time.timeScale = 1f;
            
            // 销毁所有动态创建的构件
            if (structureRoot != null)
            {
                foreach (Transform child in structureRoot)
                {
                    Destroy(child.gameObject);
                }
            }
            
            _elementMap.Clear();
        }
    }
}
