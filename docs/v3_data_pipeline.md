# v3 观测流水线与隔离契约

> 合成数据 / 已知 DGP。Phase C 工程验收文档；正式重复实验 R=0。

`scripts/11_build_v3_data.py` 是单场景工程入口，`scripts/12_validate_v3_data.py` 是工程矩阵校验入口。两者均不能把输出登记为正式模型实验。业务配置来自七份已冻结 YAML，技术参数与哈希另存 `configs/v3_data.yaml`。

单场景入口把生成器实际记录的 `population.metadata['stream_prefix']` 原样传给观测流水线。该前缀包含冻结配对组及跨组引用解析，不能以场景ID重新拼接，否则配对场景的原始事件、污染、延迟和拆分流会偏离生成器。场景ID仍用于产物目录与run_id，不参与重定义随机流。

## 观测数据流

生产函数 `build_observed_pipeline` 仅接受用户、实际分配、实际订单三个观测 DataFrame。它不能接收 `V3Population`、潜在订单、真实倾向或条件真值。

1. 构造 raw 五表；结果表暂为空。用户来源里的元/分购物车双表示必须一致，业务表只保留分字段。
2. 在独立命名随机流中注入缺失、历史 GMV 倍率异常、重复事件及入库延迟，形成 dirty。
3. clean 只确定性去重事件，保留缺失值、异常用户、退款、多单和全部分配用户。
4. raw 的 SQL 物化提供原始结果表，并只用观测分层字段确定拆分。拆分标签回写三阶段用户表，clean 的 SQL 重算产生最终分析宽表与双窗口结果表。
5. dirty 的结果表复用 clean 的 SQL 订单/分配投影：事件去重不会改变这两张事实表、金额或分母。该复用写入血缘清单。raw 结果来自 raw SQL，不使用 DGP 审计账本。
6. 训练子集拟合填补、截尾、标准化等参数，冻结后变换全体观测 X。变换特征另存，五张业务表不会被称为“已完成统计填补”。验证和测试不参与拟合。

字段及口径见 `docs/v3_data_dictionary.md`，时钟/金额见 `docs/v3_sql_contract.md`，拆分及拟合边界见 `docs/v3_preprocessing.md`。默认成熟快照与相对快照使用统一的 `assignment_day + (window_days + max_delay)` 完整到数时钟。

## 读取与落盘

`ObservedDataset.from_sql_result` 校验生产者类型、业务/技术配置、现行 SQL 源哈希和原始分析指纹；`from_manifest` 另外校验运行成功、文件字节、列顺序、类型/内容指纹，以及 Parquet 内嵌角色与配置。返回的观测副本不会改动原对象。

每次运行使用新目录，不覆盖已有 attempt。运行前后源哈希不同则失败；失败目录与原因保留。manifest 分别登记登记人数和实际工程人数，不能把小样本工程检查当作正式 N。文件中包含数据来源标记，CSV 校验结果使用 UTF-8-SIG。保留 SQLite 的代表产物另附分析前100行预览与完整组汇总、成本账CSV，manifest同时记录预览行数、全量行数和哈希。

观察数据保存在 `data/v3/engineering_checks/`。`dgp/v3_archive.py` 只向独立 `audit/v3/engineering_checks/` 写入封存模拟状态，保存原始 X、U、真实倾向、机制参数和潜在订单。观测读取函数拒绝 audit/truth 路径及审计角色。Python 任意文件访问不在该接口的安全边界内；这里防范的是分析路径中的意外泄漏。

封存状态的条件真值读取仍须在 F 阶段增加“策略和观测评估均已冻结”的释放门禁。当前写入封存文件不代表已经实现或通过 F 阶段审计。

## 独立验证与留存范围

历史队列有二元处理标签，独立随机政策验证队列有三臂标签与二元实际发券动作。`population_kind` 区分二者；验证队列可以进入观测评估、接受既有冻结变换，但不能重新拆成训练集或拟合预处理。诊断快照也不能成为历史训练数据。

本入口仅接受 `retention_scope=engineering_full` 或 `representative_full`。验证队列的代表模式限定为登记的代表 rep。它不接受正式非代表验证留存模式：F/G 须提供每次实际执行五表/SQL、随后仅保留政策名单、规定的逐用户观测摘要、汇总和 manifest 的专用路径。当前全量工程产物不能替代该验收项。

20 个局部功效格当前只验证模板继承与参数合同。`active_mde_multiplier` 非空的实际工程入口直接拒绝运行，直到 D 阶段完成独立 pilot MDE 校准并实现经评审的实际机制，防止静默运行原始效应。

`tests/test_v3_cli.py` 复制实际CLI字节到隔离的临时项目并调用项目`.venv`进程，记录原入口与副本的运行前后SHA256、stdout/stderr及产物位置。集成范围为L0-P/等成本L0-Pi配对与L3两个固定真值λT格，各取技术配置的smoke_n，实际执行五表、SQL、训练专属预处理和封存。测试比较配对raw事件，按canonical流重播MAR、历史金额异常及分配入库，复算拆分、训练键和冻结特征，并验证未校准功效模板在写产物前被拒绝。临时完整产物保留在`out/pytest/`，它们是CLI工程证据，不增加正式R，也不替代全101项矩阵。

C-R10修复的首轮定向实测为3 passed、44.10秒、exit0，日志`out/v3_phase_c/c_r10_cli_tests_attempt1.log`。四格各200人、各100训练用户的完整产物、逐格日志及四manifest机器清单保存在`out/pytest/run_74lzsins/temp/v3_cli0/`，总清单为其中的`cli_delivery.json`。L0两格均使用`v3.L0_controls.history`，MAR各选中8人；L3两格均使用`v3.L3_fixed_truth.history`且按主场景规则关闭污染。四格历史金额异常流均选中0人；逐值重播仍执行，非零异常和零金额选中反例由C-R09测试独立覆盖。独立评审和主控全回归完成前，此定向通过不单独构成C阶段整体放行。
