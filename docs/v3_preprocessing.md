# 观测拆分与训练预处理契约

> 合成数据 / 已知 DGP。Phase C 工程实现；本模块不读取 DGP 对象、潜在结果、U 或审计文件，也不完成正式实验重复。输入为 SQL 观测分析表或其明确切片。

## 用户拆分

`assign_user_splits(observed, cfg, master_seed=..., stream=..., index=...)` 返回 `SplitResult`。其中 `assignments` 只含 `run_id,user_id,split`，须由主控按双键一对一合并回分析表；它不修改原数据，也不读取利润与核销结果。`manifest` 保存角色人数、逐运行人数、非时间场景逐层人数、配置哈希、种子和拆分指纹。

非 L2 场景按冻结字段 `treatment,channel,is_new` 分层。普通历史数据的 treatment 是日志处理分配；真正 AA 中它是虚拟随机标签，实际动作另列且恒为不发券。每个运行先按最大余数法确定总训练、验证、测试人数，再在各层分配精确训练数，最后从剩余层人数分配精确验证数。极小层允许某角色人数为零，不复制用户填满。该办法保留分层结构及全局整数人数；20 万人对应精确的 10 万训练、4 万验证、6 万测试。

每层先按用户键稳定排序，再使用配置种子、调用者提供的运行随机流、层身份和重复号派生 RNG。输入行顺序、结果值和后续模型名称不影响同批用户的拆分。所有用户恰有一个角色，同一运行内重复用户键直接报错。

L2 使用冻结的日历周角色：1–5 周训练，10/11 周验证，16/22/28 周测试。周次未知或三组周次交叉时报错；不将时间场景重新随机切分。

## 滚动训练的可见性

`rolling_training_candidates(observed, cfg, origin_week=...)` 默认读取 `required_ingestion_day` 与 `complete_after_day` 两列；可用显式参数传入其他名称，字段名会写入凭据。截止日为 `(origin_week−1)×days_per_week`。

候选必须同时满足：原角色是 train 或更早测试周、入组在起点之前、30 天利润窗口已经结束、所需事件已经入库、覆盖最大延迟的完整性保障时点已经到达。仅检查“已到事件的最晚入库日”不够，因为尚未到达的事件可能改变利润。原 validation 保留作选模，不进入滚动训练；当前与未来测试周不进入训练。评估键只包含起点对应测试周。

返回的 `RollingSplitResult` 包含训练用户键、当前评估用户键及 `manifest`。该 manifest 同时是 selection receipt，保存用户键哈希、起点、截止日、配置哈希、SQL 来源类别及路径、成熟/入库字段名、完整性条件和按原因排除人数。主控的 ObservedDataset 负责绑定真实 SQL 来源。它不是一份允许任意数据改名为训练集的声明。

## 显式 fit 与冻结 transform

```python
state = fit_preprocessor(train_frame, cfg, role="train", time_mode="static")
features = state.transform(test_frame)
manifest_state = state.to_dict()
restored = FrozenPreprocessor.from_dict(manifest_state)
```

`role` 没有默认值。常规拟合只接受 split 全为 train 的非空用户切片。滚动拟合须显式指定 `role="rolling_train"` 并传入选择凭据，函数重新检查用户键、配置、起点以及每行成熟、入库和完整性条件，不能仅靠字符串角色放行测试用户。

拆分、滚动选择与 fit 入口还检查队列来源：`population_kind=validation`、任何非空 `assigned_policy_arm`，或任一为真的 `diagnostic_snapshot` 都会拒绝，即使调用者将 split 改成 train。属性标记与数据列同时检查。独立政策验证的新 X 可以使用已有冻结状态的 transform；这一操作不会把验证数据用于拟合。

冻结对象以不可变规范 JSON 保存状态；`to_dict()` 返回独立副本。完整 SHA-256 指纹覆盖训练统计、角色、用户键集合、特征名称、配置与工程参数哈希。`transform()` 返回 `FeatureMatrix(matrix,feature_names,preprocessor_hash,log)`，不更新任何参数。日志记录各字段填补、截尾和标准化裁剪人数。训练结果列不参与状态；验证与测试值不会参与任何拟合。

## 缺失、截尾与类别

数值字段由 `configs/v3_data.yaml` 的四项分配前字段和模型白名单共同限定。缺失先用训练渠道中位数，再用训练全局中位数回退；某特征训练部分全缺失时抛错，不借用验证/测试值，也不编造常数。缺失指示单独保留。

分位数、均值及标准差仅在训练切片拟合。训练缺失填补后计算截尾阈值，再对截尾训练值计算标准化参数；零方差列采用配置的单位尺度，避免除零且保留未来偏离。分位数端点 0 和 1 表示该侧真正不截尾，分别存为无下界和无上界；不能把它们解释为训练最小值和最大值。

渠道编码使用业务配置给定的固定类别字典，在 fit 时写入冻结状态。该字典不从验证/测试取值扩充。合法但训练小样本未出现的渠道保留其固定编码，其填补使用训练全局中位数；字典之外的渠道直接报错。渠道不缺失是当前 MAR 设定的输入约束。

L3 完整共同原因主场景的 winsor `[0,1]` 与 clip `null` 因此实现真正可逆的标准化，包括测试值超出训练范围的情形。`L3_missing_confounders` 压力场景仍按自己的显式配置处理信息损失，不能与完整主基准混称。

## 模型特征与日历字段

只输出白名单分配前特征。处理标签、实际动作、设计概率、利润、退款、核销成本和控制旋钮均不进入矩阵。输入出现真值/潜在结果列或 audit/truth 来源路径时立即拒绝；序列化恢复也验证合法数值特征边界。

`models.feature_specification=omit_new_user_and_channel` 时省略显式新客及渠道特征，也省略新客缺失指示；数据清洗仍遵守统一的渠道分组填补规则。因此这项对照是省略显式模型输入，不宣称清除了金额特征中所有渠道信息。

static 不含日历特征。L2 的 time_features 与 rolling_retrain 根据冻结时间白名单添加 `assignment_week` 与 `assignment_elapsed_days`；若后者尚未单列，可由同义的 `assignment_day` 生成。它们只用训练均值和标准差变换，不做用户异常值截尾或标准化裁剪。该工程规则已由主控确认并记录为 `preprocessing.time_feature_transform=standardize_without_winsor_or_clip`，防止把未来 16/22/28 周挤成同一个裁剪值。它不依据结果选择有利时间模式。

## 验证边界

本域测试覆盖 20 万人精确角色人数、分层计数、顺序不变性、极小层、复合用户键、日历角色、成熟与完整性门禁，以及训练独享统计、渠道回退、状态往返、未知类别、L3 极端外推可逆、漏入真值和测试用户的拒绝、错设特征与未来时间保序。

主控仍须以真正五表/SQL 产物完成来源绑定、持久化和端到端泄漏测试。工程用例通过不能推进任何正式 R 计数。
