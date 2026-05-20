using System;
using System.Collections.Generic;
using UnityEngine;

namespace IronFall.Physics
{
    /// <summary>
    /// 钢框架结构构建器
    /// 职责：根据 StructuralNode 和 StructuralElement 数据动态构建 Unity GameObject
    /// 
    /// 设计原则：
    /// - 所有 GameObject 必须通过 Prefab 实例化
    /// - 严禁硬编码路径
    /// - 使用对象池优化性能
    /// </summary>
    public class StructureBuilder : MonoBehaviour
    {
        [Header("Prefab 引用")]
        [SerializeField] private GameObject columnPrefab;
        [SerializeField] private GameObject beamPrefab;
        [SerializeField] private GameObject bracePrefab;
        [SerializeField] private GameObject nodePrefab;

        [Header("材质")]
        [SerializeField] private Material columnMaterial;
        [SerializeField] private Material beamMaterial;
        [SerializeField] private Material braceMaterial;
        [SerializeField] private Material nodeMaterial;

        [Header("构建参数")]
        [SerializeField] private float elementScale = 1f;
        [SerializeField] private bool useObjectPooling = true;

        // 对象池
        private Queue<GameObject> _columnPool;
        private Queue<GameObject> _beamPool;
        private Queue<GameObject> _bracePool;

        // 构建回调
        private Action<SteelFrameModel> _onBuildComplete;

        /// <summary>
        /// 构建钢框架结构
        /// </summary>
        public void BuildStructure(SteelFrameModel model, Transform parent, Action<SteelFrameModel> onComplete = null)
        {
            _onBuildComplete = onComplete;
            
            if (useObjectPooling)
            {
                InitializePools(model);
            }

            // 清空父对象
            ClearParent(parent);

            // 构建节点
            var nodeObjects = BuildNodes(model.nodes, parent);

            // 构建单元
            var elementObjects = BuildElements(model.elements, model.nodes, parent);

            // 通知构建完成
            _onBuildComplete?.Invoke(model);
        }

        /// <summary>
        /// 初始化对象池
        /// </summary>
        private void InitializePools(SteelFrameModel model)
        {
            int estimatedCount = model.elements.Count + model.nodes.Count;
            
            _columnPool = new Queue<GameObject>();
            _beamPool = new Queue<GameObject>();
            _bracePool = new Queue<GameObject>();

            // 预热对象池
            for (int i = 0; i < Mathf.Min(estimatedCount / 3, 50); i++)
            {
                _columnPool.Enqueue(CreatePooledObject(columnPrefab));
                _beamPool.Enqueue(CreatePooledObject(beamPrefab));
                _bracePool.Enqueue(CreatePooledObject(bracePrefab));
            }
        }

        /// <summary>
        /// 创建池化对象
        /// </summary>
        private GameObject CreatePooledObject(GameObject prefab)
        {
            var obj = Instantiate(prefab);
            obj.SetActive(false);
            return obj;
        }

        /// <summary>
        /// 从池中获取对象
        /// </summary>
        private GameObject GetFromPool(Queue<GameObject> pool, GameObject prefab)
        {
            if (pool.Count > 0)
            {
                var obj = pool.Dequeue();
                obj.SetActive(true);
                return obj;
            }
            return Instantiate(prefab);
        }

        /// <summary>
        /// 归还到池中
        /// </summary>
        private void ReturnToPool(Queue<GameObject> pool, GameObject obj)
        {
            obj.SetActive(false);
            pool.Enqueue(obj);
        }

        /// <summary>
        /// 清空父对象下的所有子对象
        /// </summary>
        private void ClearParent(Transform parent)
        {
            if (parent == null) return;

            var children = new List<GameObject>();
            foreach (Transform child in parent)
            {
                children.Add(child.gameObject);
            }

            foreach (var child in children)
            {
                if (useObjectPooling)
                {
                    child.SetActive(false);
                }
                else
                {
                    Destroy(child);
                }
            }
        }

        /// <summary>
        /// 构建节点
        /// </summary>
        private Dictionary<int, GameObject> BuildNodes(List<StructuralNode> nodes, Transform parent)
        {
            var nodeObjects = new Dictionary<int, GameObject>();

            foreach (var node in nodes)
            {
                GameObject nodeObj;
                
                if (useObjectPooling && _columnPool != null)
                {
                    nodeObj = GetFromPool(_columnPool, nodePrefab ?? columnPrefab);
                }
                else
                {
                    nodeObj = Instantiate(nodePrefab ?? columnPrefab);
                }

                nodeObj.transform.SetParent(parent);
                nodeObj.transform.position = node.Position * elementScale;
                nodeObj.name = $"Node_{node.id}";
                nodeObj.SetActive(true);

                // 设置节点材质
                var renderer = nodeObj.GetComponent<Renderer>();
                if (renderer != null && nodeMaterial != null)
                {
                    renderer.material = nodeMaterial;
                }

                nodeObjects[node.id] = nodeObj;
            }

            Debug.Log($"[StructureBuilder] Built {nodes.Count} nodes");
            return nodeObjects;
        }

        /// <summary>
        /// 构建单元
        /// </summary>
        private Dictionary<int, GameObject> BuildElements(
            List<StructuralElement> elements, 
            List<StructuralNode> nodes,
            Transform parent)
        {
            var nodeDict = new Dictionary<int, StructuralNode>();
            foreach (var node in nodes)
            {
                nodeDict[node.id] = node;
            }

            var elementObjects = new Dictionary<int, GameObject>();

            foreach (var element in elements)
            {
                if (!nodeDict.TryGetValue(element.nodeStartId, out var startNode) ||
                    !nodeDict.TryGetValue(element.nodeEndId, out var endNode))
                {
                    Debug.LogWarning($"[StructureBuilder] Missing nodes for element {element.id}");
                    continue;
                }

                // 选择 Prefab
                GameObject prefab = element.elementType switch
                {
                    ElementType.Column => columnPrefab,
                    ElementType.Beam => beamPrefab,
                    ElementType.Brace => bracePrefab,
                    _ => columnPrefab
                };

                GameObject elementObj;
                if (useObjectPooling)
                {
                    var pool = element.elementType switch
                    {
                        ElementType.Column => _columnPool,
                        ElementType.Beam => _beamPool,
                        ElementType.Brace => _bracePool,
                        _ => _columnPool
                    };
                    elementObj = GetFromPool(pool, prefab);
                }
                else
                {
                    elementObj = Instantiate(prefab);
                }

                elementObj.transform.SetParent(parent);
                
                // 设置位置和旋转
                Vector3 startPos = startNode.Position * elementScale;
                Vector3 endPos = endNode.Position * elementScale;
                Vector3 midpoint = (startPos + endPos) / 2f;
                Vector3 direction = endPos - startPos;

                elementObj.transform.position = midpoint;
                elementObj.transform.rotation = Quaternion.LookRotation(direction);

                // 缩放元素（长度适配）
                float length = direction.magnitude;
                var scale = elementObj.transform.localScale;
                elementObj.transform.localScale = new Vector3(scale.x, scale.y, length);

                elementObj.name = $"{element.elementType}_{element.id}";
                elementObj.SetActive(true);

                // 设置材质
                var renderer = elementObj.GetComponent<Renderer>();
                if (renderer != null)
                {
                    renderer.material = element.elementType switch
                    {
                        ElementType.Column => columnMaterial ?? renderer.material,
                        ElementType.Beam => beamMaterial ?? renderer.material,
                        ElementType.Brace => braceMaterial ?? renderer.material,
                        _ => renderer.material
                    };
                }

                // 配置 Rigidbody
                SetupRigidbody(elementObj, element, startNode);

                // 存储引用
                element.GameObject = elementObj;
                elementObjects[element.id] = elementObj;
            }

            Debug.Log($"[StructureBuilder] Built {elements.Count} elements");
            return elementObjects;
        }

        /// <summary>
        /// 配置刚体
        /// 根据节点约束设置物理属性
        /// </summary>
        private void SetupRigidbody(GameObject elementObj, StructuralElement element, StructuralNode startNode)
        {
            var rb = elementObj.GetComponent<Rigidbody>();
            if (rb == null)
            {
                rb = elementObj.AddComponent<Rigidbody>();
            }

            // 设置质量
            rb.mass = CalculateMass(elementObj.transform.localScale.y);
            
            // 设置约束
            rb.constraints = startNode.Constraints;
            
            // AMD 4500U 优化：使用离散碰撞检测
            rb.collisionDetectionMode = CollisionDetectionMode.Discrete;
            
            // 限制速度防止穿模
            rb.maxDepenetrationVelocity = 5f;
            
            // 适当的阻尼
            rb.drag = 0.5f;
            rb.angularDrag = 1f;

            element.Rigidbody = rb;
        }

        /// <summary>
        /// 计算质量
        /// 根据体积和材料密度估算
        /// </summary>
        private float CalculateMass(float scaleY)
        {
            // 简化的质量计算：假设 H 型钢截面面积约 0.01 m²
            float volumePerMeter = 0.01f; // m³/m
            float density = 7850f; // kg/m³
            return volumePerMeter * scaleY * density;
        }

        /// <summary>
        /// 创建默认 3 层钢框架模型（测试用）
        /// </summary>
        public static SteelFrameModel CreateDefault3StoryModel()
        {
            var model = new SteelFrameModel
            {
                modelId = "default_3story",
                nodes = new List<StructuralNode>(),
                elements = new List<StructuralElement>(),
                material = new MaterialData(),
                section = new SectionData()
            };

            float storyHeight = 3.0f;  // 每层高度 3m
            float bayWidth = 6.0f;     // 每跨宽度 6m
            int nodeId = 0;
            int elementId = 0;

            // 创建 3x3 的平面框架，然后复制 3 层
            int colsPerFloor = 3;  // 每层 3 根柱

            for (int floor = 0; floor < 3; floor++)
            {
                float y = floor * storyHeight;
                int floorNodeStart = nodeId;

                // 创建当前层的节点 (4 个角点 + 中间点)
                // 列 (4根柱)
                for (int i = 0; i < 2; i++)
                {
                    for (int j = 0; j < 2; j++)
                    {
                        model.nodes.Add(new StructuralNode
                        {
                            id = nodeId++,
                            x = i * bayWidth,
                            y = y,
                            z = j * bayWidth,
                            ux = (i == 0 && j == 0),  // 只有底部角点固定
                            uy = (floor == 0),         // 底层固定
                            uz = (i == 0 && j == 0)
                        });
                    }
                }

                // 添加当前层的梁 (横向和纵向)
                if (floor > 0)
                {
                    // 连接下层柱顶
                    for (int i = 0; i < 2; i++)
                    {
                        model.elements.Add(new StructuralElement
                        {
                            id = elementId++,
                            nodeStartId = floorNodeStart - colsPerFloor + i,
                            nodeEndId = floorNodeStart + i,
                            elementType = ElementType.Column
                        });
                    }
                }

                // 层间支撑（对角支撑）
                if (floor > 0 && floor < 2)
                {
                    model.elements.Add(new StructuralElement
                    {
                        id = elementId++,
                        nodeStartId = floorNodeStart - colsPerFloor,
                        nodeEndId = floorNodeStart + 1,
                        elementType = ElementType.Brace
                    });
                    model.elements.Add(new StructuralElement
                    {
                        id = elementId++,
                        nodeStartId = floorNodeStart - colsPerFloor + 1,
                        nodeEndId = floorNodeStart,
                        elementType = ElementType.Brace
                    });
                }
            }

            return model;
        }
    }
}
