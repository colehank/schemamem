# SchemaMem 评测 benchmark 完整清单

> 开发参照文档。所有结构均于 2026-07-21 从 turing_pub 上 MemoryData 仓库的**真实数据**(parquet metadata + config 文件)核实,非凭记忆。
> host 路径根:`/nfs/t1/userhome/zzl-zgh/SchemaMem-eval/MemoryData`
> ★ = 对 SchemaMem 立意(改变/更新/例外仲裁)的贴合度。

---

## 一、MemoryData 上全部四个 benchmark 框架

| 框架 | 位置 | 数据就绪 |
|---|---|---|
| MemoryAgentBench (MAB) | `benchmark/memoryagentbench/` | HF parquet 缓存 `datasets--ai-hyz--MemoryAgentBench`(4 split) |
| MemBench | `benchmark/membench/` + `datasets/MemBench/MemData/FirstAgent/` | 本地 |
| LongMemEval-s | 经 MAB/Accurate_Retrieval 提供,或独立 `datasets--xiaowu0162--longmemeval-cleaned` | 缓存 |
| LoCoMo | `benchmark/locomo/` + `datasets/LoCoMo/{locomo10.json,rq1_4cat_600_dist}` | 本地 |
| LongBench | `benchmark/longbench/` + `datasets/longBench_rep150_proportional` | 本地 |

---

## 二、MemoryAgentBench —— 四大能力维度(category)

按"记忆能力"分四类,每类下多个 sub_dataset(数字=上下文长度档)。来自 parquet `metadata` 字段真实计数。

### Accurate_Retrieval(精确检索,22 instances)
- `longmemeval_s*` (5) ★★★★ — 长期记忆问答,含 knowledge-update 子类
- `eventqa_full` / `eventqa_65536` / `eventqa_131072` (各5) ★★ — 事件问答,偏时序(我方短板)
- `ruler_qa1_197K` (1) / `ruler_qa2_421K` (1) ★ — 超长上下文检索
- **已建 config**: `Accurate_Retrieval/config/LongMemEval/Longmemeval_s.yaml`, `.../EventQA/Eventqa_full.yaml`(2 个)

### Conflict_Resolution(冲突消解,8 instances)★★★★★ 最贴合
- `factconsolidation_mh_{6k,32k,64k,262k}` (各1) — multi-hop 事实冲突,4 长度档
- `factconsolidation_sh_{6k,32k,64k,262k}` (各1) — single-hop,4 长度档
- **已建 config**: `Conflict_Resolution/config/Factconsolidation_mh_6k.yaml`(1 个;其余长度档/sh 有数据需自建 config)

### Long_Range_Understanding(长程理解,110 instances)★ 不测演化
- `infbench_sum_eng_shots2` (100) — 长文摘要
- `detective_qa` (10) — 侦探推理
- **已建 config**: 0 个

### Test_Time_Learning(测试时学习,6 instances)★ 不对口
- `recsys_redial_full` (1) — 推荐
- `icl_{banking77,clinic150,nlu,trec_coarse,trec_fine}_*shot_balance` (各1) — 上下文内分类
- **已建 config**: `Test_Time_Learning/config/ICL/ICL_banking77.yaml`(1 个)

> **MAB config 现状(全 4 类核实)**: Accurate_Retrieval 2 + Conflict_Resolution 1 + Test_Time_Learning 1 + Long_Range_Understanding 0 = **共 4 个 config**。其余 sub_dataset 有数据但需自建 config。

---

## 三、MemBench —— 五个 slice(逐文件核实 slice↔branch)

| config 文件 | slice | branches | ★ |
|---|---|---|---|
| `MemBench_knowledge_update.yaml` | knowledge_update | roles, events | ★★★★★ 更新 |
| `MemBench_noisy.yaml` | noisy | roles, events | ★★★★ 例外/噪声 |
| `MemBench_simple.yaml` | simple | roles, events | ★ 基础 |
| `MemBench_highlevel.yaml` | highlevel | movie, food, book | ★★ 高层偏好 |
| `MemBench_RecMultiSession.yaml` | RecMultiSession | multi_agent | ★★ 多会话推荐 |

- 数据: `datasets/MemBench/MemData/FirstAgent/`
- 关键 config 字段(KU 例): `context_max_length 200000`, `generation_max_length 8`(短答案精确匹配), `membench_agent_view FirstAgent`, `membench_max_scenarios_per_branch 50`, `membench_trajectory_group_size 3`

---

## 四、LongMemEval-s —— 六个 question_type(官方 500 题划分)

| question_type | 题数 | ★ |
|---|---|---|
| temporal-reasoning | 133 | ★ 已知短板(图式压掉时间轴) |
| multi-session | 133 | ★★★ 跨会话整合 |
| knowledge-update | 78 | ★★★★★ 本地已迭代到 11/15 的战场 |
| single-session-user | 70 | ★★ |
| single-session-assistant | 56 | ★★ |
| single-session-preference | 30 | ★★ |

- 本地诊断副本: `/tmp/lme_oracle.json`(500 题,HF `xiaowu0162/longmemeval` file `longmemeval_oracle`)
- config: `benchmark/memoryagentbench/Accurate_Retrieval/config/LongMemEval/Longmemeval_s.yaml`(sub_dataset `longmemeval_s*`)

---

## 五、LoCoMo —— 已完整跑通(次要证据)

- 四类 QA config: `Locomo_qa_4cat_600_dist_cat{1_multi_hop,2_temporal,3_open_domain,4_single_hop}.yaml` + 全集 `Locomo_qa_4cat_600_dist.yaml` + smoke `Locomo_1conv_smoke.yaml`
- 数据: `datasets/LoCoMo/{locomo10.json, rq1_4cat_600_dist}`
- 已有 gpt-4o-mini 单 conv 结果: exact_match 5.26 / f1 11.6;temporal f1 仅 2.7(如实承认为图式压缩时间轴的固有代价)

---

## 六、按能力轴的开发选择(实验计划)

主结果按"能力轴不重复"选,而非堆同类:

| 能力轴 | 选用子集 | 理由 |
|---|---|---|
| 更新/冲突 | **MAB FactConsolidation** + **LME-s knowledge-update** | 两个独立数据集 → 跨数据集泛化,不需第三个 |
| 例外/噪声 | **MemBench noisy** | 我方独有的"受保护例外"第三结局的专属舞台 |
| 全谱(含短板) | **LME-s 全 6 类** | 暴露 temporal 短板,避免选择性报告 |
| 覆盖面旁证 | **LoCoMo**(已有) | 多跳/时序/开放域/单跳 |

- **MemBench 主结果只报 noisy**;MB knowledge_update 与 LME-KU 重复(同为更新轴),降为可选(同一 adapter 换 slice 字段即可跑,留附录/rebuttal)。
- **不进主结果**: Long_Range_Understanding、Test_Time_Learning(ICL)、EventQA、RULER、LongBench(不测记忆演化或为已知短板)。

---

## 七、SchemaMem 接线现状(2026-07-21 核实)

- adapter: `methods/schemamem/schemamem_adapter.py`(6259 B)+ `methods/schemamem/source/`(打包的 schemamem 源码)✅ 已就绪
- agent config: `config/hybrid_schemamem.yaml`, `config/schemamem_gpt4omini.yaml` ✅ 已建
- **benchmark 侧绑定: 目前没有任何 dataset-config 绑定 schemamem**(`grep -rl schemamem benchmark/*/config/` 为空)——只有之前 LoCoMo smoke 临时接过。
- **两个已知白名单补丁**(接新 benchmark 时都要):
  1. `apply_schemamem_hooks.py` 接 agent dispatch(utils/agent.py)
  2. `utils/conversation_creator.py` 的 `MEMORY_AGENT_NAME_HINTS` tuple 需含 `"schemamem"`,否则 main.py 死在 conversation_creator.py:76 AssertionError
- **待办**: 为 FactConsolidation / MemBench-noisy / LongMemEval-s 分别接 SchemaMem dataset-config 并验证(基线侧 LongMemEval-s 已跑通 Long Context / Embedding RAG / Mem0)。

## 八、端点与环境(接线必需)

- host env: conda `memory-bench`(py3.11);vllm 0.25.1 + torch 2.11+cu130
- chat: Qwen3-8B @ `:9908`;embed: Qwen3-Embedding-4B @ `:9009`(dim **2560**,configs 统一此维度,勿用 8B 的 4096)
- 启动经 `at now`(从 /tmp 提交)守护;HF_HUB_OFFLINE=1;gpu-mem-util 0.90;禁 FlashInfer + enforce-eager
- 本地开发端点(gpt-4o-mini 迭代): dmxapi 网关 `https://www.dmxapi.cn/v1` + text-embedding-3-small(dim 1536)
