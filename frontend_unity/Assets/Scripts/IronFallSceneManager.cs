using UnityEngine;
using System.Collections.Generic;
using IronFall.Physics;
using IronFall.Network;

namespace IronFall
{
    /// <summary>
    /// Iron-Fall 场景管理器
    /// 负责协调 WebSocket、物理控制器和结构构建器
    /// 
    /// 遵循项目宪法 6.2：
    /// - 单一职责：协调各子系统
    /// - 性能优先：在 Start() 中缓存引用
    /// </summary>
    public class IronFallSceneManager : MonoBehaviour
    {
        [Header("组件引用")]
        [SerializeField] private IronFallWebSocket webSocket;
        [SerializeField] private DemolitionController demolitionController;
        [SerializeField] private StructureBuilder structureBuilder;
        [SerializeField] private Transform structureRoot;

        [Header("UI 引用")]
        [SerializeField] private UnityEngine.UI.Text statusText;
        [SerializeField] private UnityEngine.UI.Button connectButton;
        [SerializeField] private UnityEngine.UI.Button demolishButton;
        [SerializeField] private UnityEngine.UI.Button resetButton;

        // 缓存的引用
        private SteelFrameModel _currentModel;

        /// <summary>
        /// 初始化
        /// </summary>
        private void Start()
        {
            // 缓存组件引用（项目宪法：严禁在 Update 中使用 FindObjectOfType）
            if (webSocket == null)
                webSocket = FindObjectOfType<IronFallWebSocket>();
            if (demolitionController == null)
                demolitionController = FindObjectOfType<DemolitionController>();
            if (structureBuilder == null)
                structureBuilder = FindObjectOfType<StructureBuilder>();

            // 绑定事件
            BindEvents();

            // 绑定 UI 按钮
            BindUIButtons();

            // 构建默认测试模型
            BuildDefaultStructure();

            UpdateStatus("Ready");
        }

        /// <summary>
        /// 绑定事件
        /// </summary>
        private void BindEvents()
        {
            if (webSocket != null)
            {
                webSocket.OnConnected += () => UpdateStatus("Connected");
                webSocket.OnDisconnected += () => UpdateStatus("Disconnected");
                webSocket.OnError += (err) => UpdateStatus($"Error: {err}");
                webSocket.OnDemolitionResult += HandleDemolitionResult;
            }

            if (demolitionController != null)
            {
                demolitionController.OnStepComplete += (step, stable) =>
                {
                    Debug.Log($"[SceneManager] Step {step} complete, stable: {stable}");
                };
                demolitionController.OnSimulationComplete += () =>
                {
                    UpdateStatus("Simulation Complete");
                };
                demolitionController.OnError += (err) =>
                {
                    UpdateStatus($"Error: {err}");
                };
            }
        }

        /// <summary>
        /// 绑定 UI 按钮
        /// </summary>
        private void BindUIButtons()
        {
            if (connectButton != null)
                connectButton.onClick.AddListener(ConnectToServer);

            if (demolishButton != null)
                demolishButton.onClick.AddListener(StartDemolition);

            if (resetButton != null)
                resetButton.onClick.AddListener(ResetScene);
        }

        /// <summary>
        /// 连接服务器
        /// </summary>
        public void ConnectToServer()
        {
            UpdateStatus("Connecting...");
            webSocket?.Connect();
        }

        /// <summary>
        /// 开始拆除
        /// </summary>
        public void StartDemolition()
        {
            if (_currentModel == null)
            {
                UpdateStatus("No model loaded");
                return;
            }

            if (webSocket == null || !webSocket.IsConnected)
            {
                UpdateStatus("Not connected to server");
                return;
            }

            UpdateStatus("Calculating...");

            // 创建默认拆除动作：移除第一层的支撑
            var action = new DemolitionAction
            {
                step = 1,
                targetElementIds = new List<int> { 0, 1, 2 },
                actionType = "Remove"
            };

            // 发送到后端计算
            webSocket.SendDemolishRequest(_currentModel, action);
        }

        /// <summary>
        /// 处理拆除结果
        /// </summary>
        private void HandleDemolitionResult(DemolitionResult result)
        {
            Debug.Log($"[SceneManager] Demolition result: {result.success}, latency: {result.latency_ms}ms");

            if (result.success)
            {
                // 3秒法则：检查延迟
                if (result.latency_ms > 3000f)
                {
                    Debug.LogWarning($"[SceneManager] Latency exceeds 3s threshold: {result.latency_ms}ms");
                }

                // 根据稳定性状态执行
                if (result.analysis.is_safe)
                {
                    UpdateStatus($"Stable (Displacement: {result.analysis.max_displacement:F4})");
                    // 可以执行下一步拆除
                }
                else
                {
                    UpdateStatus("Unstable - Collapse triggered");
                    // 触发倒塌动画
                    demolitionController?.Pause();
                }
            }
            else
            {
                UpdateStatus("Calculation failed");
            }
        }

        /// <summary>
        /// 构建默认结构
        /// </summary>
        public void BuildDefaultStructure()
        {
            _currentModel = StructureBuilder.CreateDefault3StoryModel();
            
            structureBuilder?.BuildStructure(_currentModel, structureRoot);
            
            demolitionController?.LoadModel(_currentModel);
            
            UpdateStatus("Structure Built");
        }

        /// <summary>
        /// 重置场景
        /// </summary>
        public void ResetScene()
        {
            demolitionController?.Reset();
            BuildDefaultStructure();
            UpdateStatus("Scene Reset");
        }

        /// <summary>
        /// 更新状态显示
        /// </summary>
        private void UpdateStatus(string status)
        {
            if (statusText != null)
            {
                statusText.text = $"Status: {status}";
            }
            Debug.Log($"[SceneManager] {status}");
        }

        /// <summary>
        /// 加载外部模型
        /// </summary>
        public void LoadExternalModel(string jsonPath)
        {
            // TODO: 从文件或网络加载模型
            Debug.Log($"[SceneManager] Loading model from {jsonPath}");
        }

        /// <summary>
        /// 导出当前模型为 JSON
        /// </summary>
        public string ExportModelToJson()
        {
            if (_currentModel == null) return null;
            return JsonUtility.ToJson(_currentModel);
        }

        private void OnDestroy()
        {
            // 断开连接
            webSocket?.Disconnect();
        }
    }
}
