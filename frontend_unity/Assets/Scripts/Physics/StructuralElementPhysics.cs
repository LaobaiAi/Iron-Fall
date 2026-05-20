using UnityEngine;

namespace IronFall.Physics
{
    /// <summary>
    /// 结构单元物理组件
    /// 挂在每个钢构件 Prefab 上，负责其物理行为
    /// 
    /// 遵循项目宪法 6.2：
    /// - 单一职责：只负责物理行为
    /// - 性能优化：在 FixedUpdate 中处理
    /// </summary>
    [RequireComponent(typeof(Rigidbody))]
    public class StructuralElementPhysics : MonoBehaviour
    {
        [Header("断裂阈值")]
        [SerializeField] private float maxStress = 355f;        // 最大应力 (Q355)
        [SerializeField] private float maxDisplacement = 0.08f;  // 最大位移 (H/50)
        [SerializeField] private float fractureForceThreshold = 50000f; // 断裂力阈值 (N)

        [Header("断裂效果")]
        [SerializeField] private GameObject fractureParticle;
        [SerializeField] private AudioClip fractureSound;

        // 物理状态
        private Rigidbody _rb;
        private Vector3 _initialPosition;
        private Quaternion _initialRotation;
        private bool _isBroken;
        
        // 累积应力
        private float _accumulatedStress;

        // 事件
        public System.Action<StructuralElementPhysics> OnFracture;

        /// <summary>
        /// 是否已断裂
        /// </summary>
        public bool IsBroken => _isBroken;

        /// <summary>
        /// 当前位移
        /// </summary>
        public float CurrentDisplacement => Vector3.Distance(transform.position, _initialPosition);

        /// <summary>
        /// 初始化
        /// </summary>
        private void Awake()
        {
            _rb = GetComponent<Rigidbody>();
        }

        /// <summary>
        /// 记录初始状态
        /// </summary>
        private void Start()
        {
            _initialPosition = transform.position;
            _initialRotation = transform.rotation;
            _accumulatedStress = 0f;
            _isBroken = false;
        }

        /// <summary>
        /// 物理更新
        /// </summary>
        private void FixedUpdate()
        {
            if (_isBroken) return;

            // 检查断裂条件
            CheckFractureConditions();
        }

        /// <summary>
        /// 检查断裂条件
        /// </summary>
        private void CheckFractureConditions()
        {
            // 位移检查
            if (CurrentDisplacement > maxDisplacement)
            {
                TriggerFracture();
                return;
            }

            // 应力检查
            if (_rb != null)
            {
                float currentForce = _rb.velocity.magnitude * _rb.mass;
                if (currentForce > fractureForceThreshold)
                {
                    _accumulatedStress += currentForce;
                    if (_accumulatedStress > maxStress * 1000f) // 转换为 N
                    {
                        TriggerFracture();
                    }
                }
            }
        }

        /// <summary>
        /// 触发断裂
        /// </summary>
        public void TriggerFracture()
        {
            if (_isBroken) return;
            
            _isBroken = true;
            Debug.Log($"[StructuralElementPhysics] Element fractured at {transform.position}");

            // 禁用碰撞
            var collider = GetComponent<Collider>();
            if (collider != null)
            {
                collider.enabled = false;
            }

            // 解除约束，让其自由下落
            _rb.constraints = UnityEngine.RigidbodyConstraints.None;
            _rb.drag = 0.1f;
            _rb.angularDrag = 0.2f;

            // 添加随机力模拟断裂
            var fractureForce = new Vector3(
                Random.Range(-10f, 10f),
                Random.Range(-5f, 2f),
                Random.Range(-10f, 10f)
            );
            _rb.AddForceAtPosition(fractureForce, transform.position, ForceMode.Impulse);

            // 播放断裂效果
            PlayFractureEffect();

            // 触发回调
            OnFracture?.Invoke(this);
        }

        /// <summary>
        /// 播放断裂效果
        /// </summary>
        private void PlayFractureEffect()
        {
            // 粒子效果
            if (fractureParticle != null)
            {
                var particles = Instantiate(fractureParticle, transform.position, Quaternion.identity);
                var main = particles.GetComponent<ParticleSystem>().main;
                main.stopAction = ParticleSystemStopAction.Destroy;
            }

            // 音效
            if (fractureSound != null)
            {
                AudioSource.PlayClipAtPoint(fractureSound, transform.position);
            }
        }

        /// <summary>
        /// 添加外部应力
        /// </summary>
        public void AddStress(float stress)
        {
            _accumulatedStress += stress;
        }

        /// <summary>
        /// 重置单元
        /// </summary>
        public void Reset()
        {
            _isBroken = false;
            _accumulatedStress = 0f;
            
            transform.position = _initialPosition;
            transform.rotation = _initialRotation;
            
            _rb.velocity = Vector3.zero;
            _rb.angularVelocity = Vector3.zero;

            var collider = GetComponent<Collider>();
            if (collider != null)
            {
                collider.enabled = true;
            }
        }

        /// <summary>
        /// 获取刚体速度
        /// </summary>
        public Vector3 GetVelocity()
        {
            return _rb != null ? _rb.velocity : Vector3.zero;
        }

        /// <summary>
        /// 获取角速度
        /// </summary>
        public Vector3 GetAngularVelocity()
        {
            return _rb != null ? _rb.angularVelocity : Vector3.zero;
        }
    }
}
