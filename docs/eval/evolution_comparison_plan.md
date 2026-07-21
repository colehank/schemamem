# AAAI-27 演化维度对比实验计划

**状态**: 活文档,随实验推进更新。Claude Code 接手时按此执行。
**同层材料**: `benchmark_catalog.md`(四 benchmark 全维度清单)。

---

## 1. 硬目标

在**演化维度**上超过 Mem0 / A-MEM / MemoryBank。非演化维度可持平或落后,但**必须如实报告**(不隐藏 temporal 短板等)。

**演化维度 = 三条能力轴**:

| 轴 | 定义 | benchmark 抓手 | 主要对标 |
|---|---|---|---|
| **A. 改变检测** | 冲突时正确改信念 | MAB FactConsolidation SH-6k | Mem0(SH 原报告 18%) |
| **B. 知识更新** | 用户属性演化 | LongMemEval-s knowledge-update(**MAB 子集 45 题**;官方 78 题版每实例独立 haystack,500 次构建不可行) | Mem0、A-MEM |
| **C. 例外保留** | 孤立冲突留作 protect-as-exception | MemBench noisy | 三 baseline 都缺此能力 |

**兜底论证**(即使数字差,也必须站住):C 轴上 SchemaMem 结构性独有——`Slot.superseded` 演化链 + `Slot.exceptions` 例外层是别的方法**无法表达**的。

---

## 2. 实验矩阵(状态记账)

标注 `✓done` / `→now` / `⏳pending`。所有 SchemaMem 数字用 **gpt-4o-mini** + text-embedding-3-small(见 §6 端点)。

| 子集 | SchemaMem | Mem0 | A-MEM | MemoryBank |
|---|---|---|---|---|
| **LME-KU 15 题(pilot)** | ✓ 11/15 (73%) | ⏳ | ⏳ | ⏳ |
| **LME-KU 全 78** | ⏳ | ⏳ | ⏳ | ⏳ |
| **MAB FC-SH 6k** | ⏳ | ⏳ | ⏳ | ⏳ |
| **MAB FC-MH 6k** | ⏳ | ⏳ | ⏳ | ⏳ |
| **MB-noisy 全 500** | ⏳ | ⏳ | ⏳ | ⏳ |
| **LME-s 全 6 类**(诚实报告) | ⏳ | ⏳ | ⏳ | ⏳ |

**记忆结构对比**(不进主表,作 §5 头版图):见 §5。

---

## 3. 执行 Phase(按 ROI 排序,先便宜后昂贵)

### Phase 1 — LME-KU 15 题 pilot(先验证方向)

**为什么先跑**:我们已有 11/15;三 baseline 各跑一次约几分钟(15 题小、gpt-4o-mini 便宜)。**若 baseline 打到 12+,连夜看是什么帮了他们再决定策略**;若普遍 6-8,方向对,开跑全 78。

**输入**: `/tmp/lme_oracle.json`(500 题官方 oracle)中的 15 个 KU instance(≤3 sessions),id 列表(锁死,不换):
```
6a1eabeb, 6aeb4375, 830ce83f, 852ce960, 945e3d21, d7c942c3, 71315a70,
89941a93, ce6d2d27, 9ea5eabc, 07741c44, a1eacc2a, 184da446, 031748ae, 4d6b87c8
```

**SchemaMem 侧接口**(已就绪):
```python
from schemamem import SchemaMemorySystem
mem = SchemaMemorySystem(model="gpt-4o-mini", ...)   # 见 §6
for sess in instance["haystack_sessions"]:
    body = "\n".join(f"user: {t['content']}" for t in sess if t["role"]=="user")
    mem.add_chunk(body, timestamp=sess["timestamp"], speakers=["user"])
mem.finalize()
# 注意:没有 mem.answer() —— 早期草稿写错了。真实接口是两步(与 harness 契约一致):
ctx, _groups = mem.retrieve_with_source_groups(instance["question"])
ans = mem.ask_with_retrieved_context(instance["question"], ctx)
```

**输出格式**(必须四方法共用):
```json
{"method": "schemamem|mem0|a_mem|memorybank",
 "model": "gpt-4o-mini",
 "results": [
   {"qid": "89941a93...", "gold": "4", "pred": "4", "correct": true,
    "memory_snapshot_path": "snapshots/schemamem/89941a93.json"}, ...
 ],
 "accuracy": 0.73}
```

**验收**: SchemaMem > 每个 baseline 至少 2 分。达不到 → 见 §7 应对。

### Phase 2 — 全 benchmark 主结果

**Phase 1 通过**后启动。三个 benchmark 并行:

- **A 轴 · MAB FC**: `commit 141e23c` 的 `schemamem.bench_adapters.add_fc_fact()` 是接口。数据 host 上,SH-6k 已抽到本地 `bench_samples.json`。执行:
  ```python
  from schemamem.bench_adapters import add_fc_fact
  for line in fc_context.split("\n"):
      if line[:1].isdigit(): add_fc_fact(mem, line, timestamp=f"t{i:03d}")
  mem.finalize()
  # answer each of 100 questions
  ```
  基线在 host 上跑(baselines session 负责),SchemaMem 也在 host 跑保持环境一致。

- **B 轴 · LME 全 78**: pilot 通过后直接扩子集,无需改代码。

- **C 轴 · MB-noisy 全 500 traj**: 已在 traj0 验证(见 §5 附样本);每 traj 一 QA,一致的 memory dump 格式。

**验收**: A/B 两轴各超过至少一个 baseline;C 轴 SchemaMem 独有 exception-slot 数 > 0 且 competitive on accuracy。

### Phase 3 — 记忆结构对比图(§5 头版)

即使数字差,这张图独立成立。四方法在**同一 case** 上建出的记忆结构可视化并列:

**Case 1**(A 轴,来自 FC-SH-6k,已核实): `Hines Ward.position` — wide receiver(fact #3) → cornerback(fact #36)。
**Case 2**(A 轴): `Frank Zappa.location` — Los Angeles(fact #37) → Berlin(fact #51)。
**Case 3**(B 轴,来自 LME-KU): bikes 3→4(instance 89941a93,gold=4)。
**Case 4**(C 轴,来自 MB-noisy): 找一个 traj 里同一实体两次给出冲突值(在孤立位置)。

**每方法要 dump 的最小 memory state**(baselines session 需要接):
```json
{"entities": {"Hines Ward": {
    "position": {"current": "cornerback",
                 "history": [{"value": "wide receiver", "t": "t3"}],
                 "exceptions": [],
                 "n_obs": 2}}}}
```
- Mem0: current 有;history 通常空(它 overwrite);exceptions 空——**这就是缺陷**。
- A-MEM: 无 current(两 note 并列关联);history 有;exceptions 空。
- MemoryBank: current 有(高分那条);history 有(低分那条);exceptions 空。
- **SchemaMem**: 四字段全有。

**产出**: `docs/eval/figures/memory_structure_comparison.pdf`,4 案例 × 4 方法 = 16 面板。

### Phase 4 — 非演化维度(诚实报告)

**必须报**:
- LME temporal-reasoning 133 题(已知短板,在 §5 明说"图式压缩时间轴的固有代价"+ 我们已实现 timeline_view 但 A/B 测试无帮助——诚实结果值得写);
- LME multi-session 133 题;
- LoCoMo 主表(已有 gpt-4o-mini 结果 em=5.26/f1=11.6,temporal f1=2.7)。

**不报**: MAB Long_Range_Understanding、Test_Time_Learning、RULER(不测演化)。

---

## 4. Handoff 给 baselines session

**baselines session 需要在这三个 benchmark 上跑三个 baseline,并共享**:

1. **每 instance 的准确率 JSON**(见 §3 Phase 1 输出格式);
2. **每方法的 memory dump**(见 §3 Phase 3 格式)——用于对比图;
3. **同一 model + 同一 15/78/500 题 ID 列表**(必须逐字符对齐)。

**接线要求**:
- 模型: `gpt-4o-mini` via `OPENAI_BASE_URL=https://www.dmxapi.cn/v1`(local dev)或 turing_pub 的 Qwen3-8B(远程 batch);两种都可,但**一次实验内必须统一**。
- Mem0 / A-MEM / MemoryBank 的 adapter 参考各自 GitHub 的 quickstart;每个 adapter 加一个 `dump_memory(traj_id) -> dict` 钩子输出上面 §3 Phase 3 的最小格式。

**这个仓库(SchemaMem)**不实现 baselines——那是 baselines session 的分工(见 project memory: `cline_ownership = "C，另一个session在搭建A"`)。

---

## 5. 现有材料索引

- **Benchmark 数据本地样本**: `bench_samples.json`(仓库根,120KB;含 FC-SH-6k、FC-MH-6k、MB-noisy-traj0);
- **SchemaMem 已构建的记忆样本**:
  - FC-SH 60 事实: artifact `664f2502-acaf-44bd-99eb-0800ff20e24d`
  - MB-noisy traj0: artifact `055c8854-bda8-41ab-9e48-136e05bd7dc1`
  - 合集: artifact `6cc70cdc-822e-4322-895e-18ba1fb34176`
- **LME-KU 15 题诊断**(11/15 迭代过程): artifact `4e14fd91-3fd5-4d8f-b55d-c96c560c2d7d`;
- **SchemaMem 主接口**: `SchemaMemorySystem.add_chunk / .add_chunks / .finalize / .retrieve_with_source_groups / .ask_with_retrieved_context`;`bench_adapters.add_fc_fact` for FC。(**没有 `.answer()`** —— 本文档早期版本误载,已订正。)

---

## 5b. 接线现状与本轮决定(2026-07-22 核实)

**host 上的真实状态**(`turing` → `~/SchemaMem-eval/MemoryData`,ssh config 里是 `turing` 不是 `turing_pub`):

- **三个基线 + 两个无演化对照全部已接好**,不需要重写 adapter:
  `methods/{a_mem,mem0,memorybank,schemamem,embedding_rag}/` 齐全;
  `config/{hybrid_a_mem,sequential_mem0,memorybank,hybrid_schemamem}.yaml` +
  `config/reference_{long_context_agent,embedding_rag}.yaml`。
- **数据齐全**:`~/.cache/huggingface` 42G,含 `datasets--ai-hyz--MemoryAgentBench`
  与 `datasets--xiaowu0162--longmemeval-cleaned`;`datasets/{LoCoMo,MemBench,longBench_*}`。
- **既有结果只是 smoke**:四方法都只在 Qwen3-8B、`max_test_samples: 5` 下跑过,**无任何真实规模数字**。
- **本地缺失**:`bench_samples.json` 只在 host 家目录,从未提交进本仓库;`/tmp/lme_oracle.json` 已随 /tmp 清空消失。

**本轮决定**:

1. **统一口径 = gpt-4o-mini + text-embedding-3-small(dim 1536),经 dmxapi 网关**。
   一度考虑 gpt-4o,按 harness 实参估算主表全量约 $5k–10k(mini 约 1/16),且 §7 已记录
   "4o probe 对已诊断失败无用",故维持 mini。四个 gpt-4o-mini config 已建:
   `config/{schemamem,a_mem,mem0,memorybank}_gpt4omini.yaml`,除机制外 LLM/embedding 完全同源。
2. **检索预算:保持各方法 harness 默认,不对齐**(选项 a)。当前值:
   A-MEM `retrieve_num=2`、Mem0 `100`、SchemaMem `10`、MemoryBank `10`。
   单位不可比(A-MEM 的 note 含上下文+关键词+链接,Mem0 的 memory 是单句事实)。
   **论文须主动披露这张表并说明单位差异** —— 主动说是免疫,被问出来是失分。
   选 (a) 而非按 token 对齐,是为了不落"为求胜而调对手参数"的口实。
3. **凭据**:host `~/.schemamem_env`(`chmod 600`,不进仓库),内含 `OPENAI_API_KEY` /
   `OPENAI_BASE_URL`;运行前 `. ~/.schemamem_env`。

**仍缺的接线**:

- `benchmark/memoryagentbench/Conflict_Resolution/config/` 下**只有 `Factconsolidation_mh_6k.yaml`,缺 SH-6k**,而 A 轴要 SH+MH 两档 → 需建 SH config。
- 各 dataset config 的 `max_test_samples: 5` 是 smoke 值,全量跑须改。
- Phase 3 对比图要求的 `dump_memory(traj_id) -> dict` 钩子,**SchemaMem 侧尚未实现**(数据都在 `SchemaGraph` 里,预计 ~20 行)。

**运行方式**(host 上,conda env `memory-bench`):

```bash
cd ~/SchemaMem-eval/MemoryData && . ~/.schemamem_env
source ~/miniconda3/etc/profile.d/conda.sh && conda activate memory-bench
python main.py --agent_config config/schemamem_gpt4omini.yaml \
  --dataset_config benchmark/memoryagentbench/Accurate_Retrieval/config/LongMemEval/Longmemeval_s.yaml \
  --max_test_queries_ablation 1 --force
```

---

## 6. 环境与端点(必须统一)

**本地开发端点**(gpt-4o-mini):
```
OPENAI_BASE_URL=https://www.dmxapi.cn/v1
OPENAI_API_KEY=<env>
model=gpt-4o-mini
embedding=text-embedding-3-small (dim 1536)
```

**远程(turing_pub, Qwen3-8B)**: 见 `benchmark_catalog.md` §八。

**Python env**: `uv sync` 后 `uv run pytest`。测试当前 5/5 + 13/13 全过(commit 141e23c)。

---

## 7. 若 Phase 1 pilot 不达标

**若 baselines 打到 12+/15**:
1. **诊断差异**——他们改的哪个失败 case(mortgage $400k? Rachel 共指? 5K 27:12?)对了;
2. **不是抄机制**——机制是我们的立意,不能改;
3. **可能是他们的抽取更好**——考虑给 SchemaMem 加 sample-based L1(l1_samples>1)或更强模型(4o probe 已验证 4o 对已诊断失败无用,见 mem `mem_0e18d8ac64b7`),但**代价是训练/推理成本**。

**若我们 11/15、Mem0 8/15、A-MEM 7/15、MemoryBank 6/15**(乐观预期):
方向对,直接开跑 Phase 2 全 78 + FC + MB。

**若 SchemaMem 掉到 <10/15**(kernel/依赖导致的回归):
先 `git bisect` 到 commit 141e23c(已知 11/15 的 baseline commit)复现。

---

## 8. 交付时间线(锚定 AAAI-27)

- **7/22 AoE**: 摘要截止 — 摘要已注册(user handles);
- **7/23-24**: Phase 1 pilot;
- **7/24-26**: Phase 2 主实验;Phase 3 图并行;
- **7/27**: Phase 4 + 全文最终稿;
- **7/28 AoE**: 全文截止。

Phase 2 单个 benchmark 若卡壳 > 24h,砍到子集(如 MAB 只报 6k+32k 两档,不报 64k/262k)。**保 3 个 benchmark 都有数**,别孤注一掷单个跑全。
