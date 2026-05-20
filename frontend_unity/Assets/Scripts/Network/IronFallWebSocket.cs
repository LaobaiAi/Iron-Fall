using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using WebSocketSharp;
using IronFall.Physics;

namespace IronFall.Network
{
    /// <summary>
    /// Iron-Fall WebSocket 客户端
    /// 负责与后端 FastAPI 服务建立连接并通信
    /// </summary>
    public class IronFallWebSocket : MonoBehaviour
    {
        [Header("服务器配置")]
        [SerializeField] private string serverUrl = "ws://localhost:8000/ws/demolition";
        
        private WebSocket _ws;
        private bool _isConnected;
        private CancellationTokenSource _cts;
        
        // 事件回调
        public event Action<DemolitionResult> OnDemolitionResult;
        public event Action<bool, string> OnValidationResult;
        public event Action<string> OnError;
        public event Action OnConnected;
        public event Action OnDisconnected;
        
        /// <summary>
        /// 是否已连接
        /// </summary>
        public bool IsConnected => _isConnected;
        
        /// <summary>
        /// 连接服务器
        /// </summary>
        public async void Connect()
        {
            if (_isConnected) return;
            
            _cts = new CancellationTokenSource();
            
            try
            {
                _ws = new WebSocket(serverUrl);
                
                _ws.OnOpen += (sender, e) =>
                {
                    _isConnected = true;
                    Debug.Log("[IronFallWS] Connected to server");
                    OnConnected?.Invoke();
                };
                
                _ws.OnMessage += HandleMessage;
                
                _ws.OnError += (sender, e) =>
                {
                    Debug.LogError($"[IronFallWS] Error: {e.Message}");
                    OnError?.Invoke(e.Message);
                };
                
                _ws.OnClose += (sender, e) =>
                {
                    _isConnected = false;
                    Debug.Log("[IronFallWS] Disconnected");
                    OnDisconnected?.Invoke();
                };
                
                await Task.Run(() => _ws.Connect());
            }
            catch (Exception ex)
            {
                Debug.LogError($"[IronFallWS] Connection failed: {ex.Message}");
                OnError?.Invoke(ex.Message);
            }
        }
        
        /// <summary>
        /// 断开连接
        /// </summary>
        public void Disconnect()
        {
            _cts?.Cancel();
            _ws?.Close();
            _ws = null;
            _isConnected = false;
        }
        
        /// <summary>
        /// 发送拆除请求
        /// </summary>
        public void SendDemolishRequest(SteelFrameModel model, DemolitionAction action)
        {
            if (!_isConnected)
            {
                OnError?.Invoke("Not connected to server");
                return;
            }
            
            var message = new Dictionary<string, object>
            {
                ["type"] = "demolish",
                ["model"] = model.ToDictionary(),
                ["action"] = action.ToDictionary()
            };
            
            _ws.Send(JsonUtility.ToJson(message));
        }
        
        /// <summary>
        /// 发送模型验证请求
        /// </summary>
        public void SendValidationRequest(SteelFrameModel model)
        {
            if (!_isConnected)
            {
                OnError?.Invoke("Not connected to server");
                return;
            }
            
            var message = new Dictionary<string, object>
            {
                ["type"] = "validate",
                ["model"] = model.ToDictionary()
            };
            
            _ws.Send(JsonUtility.ToJson(message));
        }
        
        /// <summary>
        /// 发送心跳检测
        /// </summary>
        public void SendPing()
        {
            if (!_isConnected) return;
            _ws.Send("{\"type\":\"ping\"}");
        }
        
        private void HandleMessage(object sender, MessageEventArgs e)
        {
            var json = e.Data;
            
            try
            {
                var wrapper = JsonUtility.FromJson<MessageWrapper>(json);
                
                switch (wrapper.type)
                {
                    case "pong":
                        Debug.Log("[IronFallWS] Pong received");
                        break;
                        
                    case "result":
                        var result = JsonUtility.FromJson<DemolitionResult>(json);
                        OnDemolitionResult?.Invoke(result);
                        break;
                        
                    case "validation_result":
                        var validation = JsonUtility.FromJson<ValidationResult>(json);
                        OnValidationResult?.Invoke(validation.is_valid, validation.error);
                        break;
                        
                    case "error":
                        var error = JsonUtility.FromJson<ErrorMessage>(json);
                        OnError?.Invoke(error.message);
                        break;
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[IronFallWS] Parse error: {ex.Message}");
            }
        }
        
        private void OnDestroy()
        {
            Disconnect();
        }
        
        #region 数据结构
        
        [Serializable]
        public class MessageWrapper
        {
            public string type;
        }
        
        [Serializable]
        public class ErrorMessage
        {
            public string type;
            public string message;
        }
        
        [Serializable]
        public class ValidationResult
        {
            public string type;
            public bool is_valid;
            public string error;
        }
        
        [Serializable]
        public class DemolitionResult
        {
            public string type;
            public bool success;
            public AnalysisData analysis;
            public float latency_ms;
        }
        
        [Serializable]
        public class AnalysisData
        {
            public float max_displacement;
            public string stability_status;
            public bool is_safe;
            public List<string> warnings;
        }
        
        #endregion
    }
}
