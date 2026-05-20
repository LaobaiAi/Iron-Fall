using System;
using System.Collections.Generic;
using UnityEngine;

namespace IronFall.Physics
{
    /// <summary>
    /// 钢框架模型数据结构
    /// 与后端 IFCS (Iron-Fall Core Schema) 对齐
    /// 用于客户端结构表示和物理模拟
    /// </summary>
    [Serializable]
    public class SteelFrameModel
    {
        public string modelId;
        public List<StructuralNode> nodes;
        public List<StructuralElement> elements;
        public MaterialData material;
        public SectionData section;

        /// <summary>
        /// 从后端 JSON 创建模型
        /// </summary>
        public static SteelFrameModel FromJson(string json)
        {
            return JsonUtility.FromJson<SteelFrameModel>(json);
        }

        /// <summary>
        /// 转换为字典用于发送
        /// </summary>
        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                ["model_id"] = modelId,
                ["nodes"] = nodes.ConvertAll(n => n.ToDictionary()),
                ["elements"] = elements.ConvertAll(e => e.ToDictionary()),
                ["material"] = material.ToDictionary(),
                ["section"] = section.ToDictionary()
            };
        }
    }

    /// <summary>
    /// 结构节点
    /// 对应后端 IFCS Node 模型
    /// </summary>
    [Serializable]
    public class StructuralNode
    {
        public int id;
        public float x, y, z;
        // 约束状态 [Ux, Uy, Uz, Rx, Ry, Rz]
        public bool ux = true, uy = true, uz = true, rx = false, ry = false, rz = false;

        /// <summary>
        /// 节点世界坐标
        /// </summary>
        public Vector3 Position => new Vector3(x, y, z);

        /// <summary>
        /// 约束向量 (用于物理模拟)
        /// </summary>
        public RigidbodyConstraints Constraints
        {
            get
            {
                var constraints = RigidbodyConstraints.None;
                if (ux) constraints |= RigidbodyConstraints.FreezePositionX;
                if (uy) constraints |= RigidbodyConstraints.FreezePositionY;
                if (uz) constraints |= RigidbodyConstraints.FreezePositionZ;
                if (rx) constraints |= RigidbodyConstraints.FreezeRotationX;
                if (ry) constraints |= RigidbodyConstraints.FreezeRotationY;
                if (rz) constraints |= RigidbodyConstraints.FreezeRotationZ;
                return constraints;
            }
        }

        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                ["id"] = id,
                ["x"] = x,
                ["y"] = y,
                ["z"] = z,
                ["restraint"] = new[] { ux, uy, uz, rx, ry, rz }
            };
        }
    }

    /// <summary>
    /// 单元类型枚举
    /// </summary>
    public enum ElementType
    {
        Column,   // 柱
        Beam,     // 梁
        Brace     // 支撑
    }

    /// <summary>
    /// 结构单元
    /// 对应后端 IFCS Element 模型
    /// </summary>
    [Serializable]
    public class StructuralElement
    {
        public int id;
        public int nodeStartId;
        public int nodeEndId;
        public ElementType elementType;
        
        // 物理属性
        [HideInInspector] public GameObject GameObject;
        [HideInInspector] public Rigidbody Rigidbody;

        /// <summary>
        /// 转换为字典
        /// </summary>
        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                ["id"] = id,
                ["node_i_id"] = nodeStartId,
                ["node_j_id"] = nodeEndId,
                ["element_type"] = elementType.ToString()
            };
        }
    }

    /// <summary>
    /// 材料数据
    /// </summary>
    [Serializable]
    public class MaterialData
    {
        public string name = "Q355";           // 钢材牌号
        public float density = 7850f;          // 密度 kg/m³
        public float youngsModulus = 206000f;   // 弹性模量 MPa
        public float yieldStrength = 355f;      // 屈服强度 MPa

        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                ["name"] = name,
                ["density"] = density,
                ["E"] = youngsModulus,
                ["fy"] = yieldStrength
            };
        }
    }

    /// <summary>
    /// 截面数据
    /// </summary>
    [Serializable]
    public class SectionData
    {
        public string name = "H400x200x8x13";
        public float area = 9480f;              // 截面积 mm²
        public float momentOfInertiaY = 237000000f; // 绕Y轴惯性矩 mm⁴
        public float momentOfInertiaZ = 45000000f;  // 绕Z轴惯性矩 mm⁴
        public float torsionalConstant = 2900000f;   // 扭转常数 mm⁴

        // Unity 物理参数
        public float width = 0.2f;
        public float height = 0.4f;

        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                ["name"] = name,
                ["A"] = area,
                ["Iy"] = momentOfInertiaY,
                ["Iz"] = momentOfInertiaZ,
                ["J"] = torsionalConstant
            };
        }
    }

    /// <summary>
    /// 拆除动作数据结构
    /// 与后端 DemolitionAction 对齐
    /// </summary>
    [Serializable]
    public class DemolitionAction
    {
        public int step;
        public List<int> targetElementIds;
        public string actionType;  // "Remove" or "ApplyForce"
        public float[] forceVector; // [Fx, Fy, Fz]

        /// <summary>
        /// 是否为移除操作
        /// </summary>
        public bool IsRemove => actionType == "Remove";

        /// <summary>
        /// 是否为施加力操作
        /// </summary>
        public bool IsApplyForce => actionType == "ApplyForce";

        /// <summary>
        /// 获取力向量
        /// </summary>
        public Vector3 GetForceVector()
        {
            if (forceVector == null || forceVector.Length < 3)
                return Vector3.zero;
            return new Vector3(forceVector[0], forceVector[1], forceVector[2]);
        }

        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                ["step"] = step,
                ["target_element_ids"] = targetElementIds,
                ["action_type"] = actionType,
                ["force_vector"] = forceVector != null ? forceVector : new float[3]
            };
        }
    }

    /// <summary>
    /// 通用消息包装器
    /// 用于 JSON 序列化/反序列化
    /// </summary>
    [Serializable]
    public class MessageWrapper
    {
        public string type;
    }
}
