# Phase C 数据工程验证与验收

> 合成数据 / 已知 DGP。维护时间：2026-10-25 10:09（北京时间）。C独立工程验收已通过；正式R始终为0。下文保留计划、返工与执行历史。

## 最终验收

最终批准为`outputs/v3/data_validation/approval.json`，独立评审为`docs/reviews/v3_phase_C_review.md`；数字与证据哈希统一登记在`outputs/tables/v3_phase_C_acceptance.csv`。完整矩阵`phase_c_20261025T013445468783Z_pid18708`的101项作业、6977项检查全部通过：73个场景各5000人，四个20万人代表数据库，四个5000人的独立工程队列，以及20项不生成用户的功效模板合同。实际81批队列累计1185000行，不能称为去重用户数。

68个登记源前后/当前一致，全部3015个实物的哈希和Parquet元数据核对通过。主控逐双窗比较30810000个整分单元；独立评审另从原始订单重算三阶段、双窗及金额/事件统计，共120870000单元一致。四库五表全行、全部SQL分析列、quick_check、外键和CSV示例通过。CLI11的四格真实执行与其源文件另行绑定，不属于该68源的矩阵执行链。

最终全回归803项通过、1条既有B积分roundoff告警；凭据为`outputs/v3/data_validation/pytest_gate.json`。历史失败尝试保留，C-R09和C-R10已完成返工复审。首次临时批准早于评审文档最终冻结，已保留中间文件并重新绑定最终评审SHA，现行批准以approval.json为准。

C01/C02仅在上述工程范围通过。20个实际功效机制待D；工程三臂占位政策不算F的学习策略验证；正式非代表验证精简留存、冻结后真值释放及全部正式N/R仍待F/G。本轮用户要求C后收尾交接，D未启动。

依据 `GOAL.md` 的C01/C02、`docs/v3_协议.md` 与技术配置 `configs/v3_data.yaml`，执行清单从冻结场景注册表派生：全部73个完整场景各5000用户、四个核心场景各20万用户并保留可查询SQLite、四层各5000人的独立三臂工程队列。另20个局部功效模板仅检查继承与参数合同，机制状态保留 `pending_phase_d_actual_calibrated_mechanism`。

独立队列按冻结三臂概率随机分配，使用显式工程占位发券规则检验数据路径与全臂分母，不声称已完成模型选择、策略冻结或Phase F随机验证。占位随机/定向规则按10元最坏面额预算限制人数；此规则没有被用来产生任何正式策略收益结论。

生产路径只接收 `observation_bundle()` 的三张事实表，经过原始/污染/去重五表、SQL核算和训练专属预处理。外层检查器另用Phase B独立账本逐用户、逐窗口、逐分核对所有货币列，私有审计文件写入 `audit/v3/engineering_checks/`，不能进入学习接口。每个场景同时检查全用户分母、7天购买与30天利润窗口（各窗口在全部组等长）、退款/多单保留、污染及修复数量、拆分完整性、SQL来源、训练用户键和全部落盘哈希。所有金额误差容限取冻结的 `business.money.profit_identity_tolerance_cent=0`。

历史金额倍率异常分开记录“随机流选中数”和“实际数值改变数”。检查器以冻结的 `project.master_seed`、原manifest记录的 `stream_prefix` 与 `rep_id` 重放 `dirty.hist_fraud`，将选中人数与生产 `hist_fraud_injected` 精确核对，再逐行比较原金额乘倍率所得的期望脏值。零金额被选中后仍为零，倍率为1时所有选中金额也可保持不变；这些情况不降低逐值校验标准。`checks.csv` 的异常检查详情保存 `selected_count`、`changed_count`、`expected_changed_count` 与 `recorded_selected_count`，逐作业summary的 `pollution_audit` 保存 `hist_fraud_selected` 和 `hist_fraud_changed`。

每个实际队列另保存原始用户、隐藏状态、两种潜在订单和机制元数据的封存副本，标记 `sealed_pending_frozen_policy_and_observed_results`。封存只写、不计算条件真值，也没有为学习接口增加读取入口；逐分对账文件与封存状态分目录保存。

新尝试启动前，以操作系统跨进程文件锁保护“检查旧记录→登记新尝试”的完整临界区。同一输出根目录中，任何非终态记录的预定作业集合相交都触发进程身份检查，配置不同也不能绕过。不相交范围可并存；`--resume`和普通启动均受此约束。Windows通过 `OpenProcess`、`GetExitCodeProcess`、`GetProcessTimes` 读取PID与创建FILETIME，明确查得进程退出或PID已复用才把旧记录视作失活；权限不足或创建身份缺失明确拒绝。旧记录及失败输出不删除，进程退出由操作系统释放登记锁。

Windows的 `.venv/Scripts/python.exe` 可能通过redirector启动真实Python，因此 `Popen.pid` 不能直接当作计算进程PID。运行manifest写入脚本内 `os.getpid()` 及其创建身份；D阶段进程/资源监测也应使用该实际PID。进程测试由子程序回传身份，并分别接收stdin指令正常退出或调用 `os._exit(1)` 模拟崩溃，避免只终止启动器而留下真实子进程。项目执行仍使用 `.venv` 入口，不改用基础解释器。

实际数据写入 `data/v3/engineering_checks/<job>/<attempt>/`；检查结果写入 `outputs/v3/data_validation/<unique>/checks.csv`、`scenario_summary.csv`、`manifest.json`及逐作业凭据。每个新尝试使用新目录，失败文件和错误记录保留。恢复只允许复用已通过、来源代码/全部配置/SQL与文件内容哈希均匹配的凭据，逐作业凭据本身须匹配上次报告的哈希。独立队列还绑定历史SQL manifest，避免借用不匹配的预处理状态；没有匹配凭据就新建尝试，不能将旧配置结果当作当前验收。

完整清单有101个作业：73个完整场景、4个20万代表队列、4个独立工程队列与20个功效模板合同。`n_registered` 保存冻结正式设计人数，`n_actual` 保存实际工程人数。`full_required_engineering_coverage` 只有未筛选的 `all` 范围全部实际通过才置为真；模板合同通过仍不改变其机制待Phase D状态。每类计划数、已过数、失败数另写 `category_counts`，正式重复完成数恒为0。

先执行默认小样本预检：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& '.\.venv\Scripts\python.exe' scripts/12_validate_v3_data.py --scope smoke
```

源码稳定且主控允许后，执行完整工程清单：

```powershell
& '.\.venv\Scripts\python.exe' scripts/12_validate_v3_data.py --scope all --resume
```

`--scope matrix`、`representatives`、`validation`、`power`用于分别执行可审计范围；`--scenario`可选择注册的完整场景。部分范围成功不能支持“全场景通过”。人数、正式完成计数和数值容限均来自技术配置或冻结业务配置，不提供任意改n/R的命令参数。

当前作者测试：17项自动测试已通过，覆盖完整作业枚举、20个功效合同不生成数据、真实历史与独立工程队列、封存隔离、SQLite重开、精确恢复、错账/文件与凭据篡改/来源变动反例，以及真实进程的活跃拒绝、退出恢复、PID复用识别、未知身份拒绝、不相交并行、双进程抢占与异常退出释放锁。新增7项覆盖异常mask选中零值、选中非零值、未选中不变、三类用户脏值篡改、选中计数篡改，以及关闭污染或倍率为1时合法的零变化。最终定向日志为 `out/v3_phase_c/c_r09_checker_tests.log`：17 passed、61.56秒、exit0。测试临时文件与失败尝试保留在 `out/pytest/`；作者测试不能替代独立评审。

受控返工记录：旧源码smoke位于 `outputs/v3/data_validation/phase_c_20261024T190015627535Z_pid18532/`，8队列/664项检查通过。旧全量尝试 `phase_c_20261024T190058960334Z_pid15820/` 完成73个5000用户场景后，因新增并发门禁改变源码，在第一个20万代表队列触发source-changed失败保护。旧结果完整保留，不能复用为新源码最终验收；此失败是计划内源码返工，不能计作金额不一致。修复后须重新通过独立进程测试、smoke及全101作业。当前尚不能据本文宣称C01/C02通过，正式R仍为0。

其后 `phase_c_20261024T191836270464Z_pid2300/` 在73个场景通过后，于首个20万代表队列暴露C-R09：checker错误要求选中数等于数值改变数。该队列实际选中362人，改变361人，存在1名被选中的零金额用户；按原流及倍率重播时全部20万脏值均正确，生产污染机制未作修改。此次失败及73项局部结果继续保留，不能追认为修复后源码的完整证据。修复后的旧实物只读重播记录为 `out/v3_phase_c/c_r09_retained_artifact_recheck.json`，后续仍由主控重新执行smoke、全101作业及全回归，再交独立评审。
