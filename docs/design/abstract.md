# SchemaMem — AAAI-27 Abstract & Title (Submission Draft v5)

> Target: AAAI-27 Main Technical Track. Abstract due 2026-07-21 (AoE). **AAAI abstract limit: 150–250 words** — primary is now 237 words, short variant ~216 words; both compliant. LOAD-BEARING THESIS: the three memory-evolution mechanisms (consolidation/updating/forgetting) share ONE defect — none carries an expectation, so each decides by a surface proxy instead of an observation's violation of the expectation (residual). Schema supplies the expectation → residual computable → one signal arbitrates all three. Integration is a byproduct, not a selling point; protected exception is the EXISTENCE PROOF arbitration is happening. Result claim: conservative ("competitive"), accuracy-only.

---

## Title (primary)

**SchemaMem: Building a Human-Memory-Inspired Memory Evolution System for LLM Agents**

*De-hyphenated phrasings of the same title (pick one before registration):*
- SchemaMem: A Human Memory Inspired Memory Evolution System for LLM Agents
- SchemaMem: Human Memory as a Blueprint for Agent Memory Evolution
- SchemaMem: Toward Human-Inspired Memory Evolution in LLM Agents

*Alternates (different angle):*
- SchemaMem: One Signal for Memory Evolution in Long-Running LLM Agents
- SchemaMem: Schema-Based Arbitration of Change, Redundancy, and Exception in Agent Memory

---

## Abstract (primary, ~237 words — within AAAI 150–250 limit)

As LLM agents move to long-running operation over weeks or months, memory evolution—distilling a stream of arriving, sometimes contradictory observations into a knowledge model that stays current—becomes a core capability. Existing work pursues it along three separately developed mechanisms: consolidation, updating, and forgetting. We argue they share one defect: none carries an expectation, so each decides by a surface proxy—similarity, recency, or time and frequency—instead of asking what a new observation means relative to what the agent currently believes. The same decision is answered wrongly in three ways, forcing a genuine change and an isolated anomaly down the same path. Human memory answers this with a schema, which carries graded expectations and is revised only when experience violates them repeatedly rather than once. Inspired by this, we introduce SchemaMem, which models what the agent believes as a schema of named slots with an evidence ledger and scores each observation by how strongly it violates the schema's expectation. This one quantity drives the whole evolution: low-violation observations are compressed, repeated violations revise the belief, and an isolated strong violation is kept as a protected exception—a third outcome proxy-only systems structurally cannot produce, and thus itself evidence that arbitration is occurring. On the same retrieval backbone as a flat baseline, SchemaMem is competitive on LongMemEval and LoCoMo, with gains concentrated in knowledge-update and exception questions and parity on single-hop facts—a built-in check that gains come from arbitration, not retrieval.

---

## Abstract (short variant, ~216 words — if OpenReview enforces a tight limit)

As LLM agents move to long-running operation over weeks or months, memory evolution—keeping a knowledge model current under a stream of contradictory observations—becomes a core capability. Existing work pursues it along three separately developed mechanisms: consolidation, updating, and forgetting. We argue they share one defect: none carries an expectation, so each decides by a surface proxy—similarity, recency, or time and frequency—instead of asking what a new observation means relative to what the system currently believes. The same decision is answered wrongly in three ways, forcing a genuine change and an isolated anomaly down the same path. Human memory answers this with a schema, which carries graded expectations and is revised only when experience violates them repeatedly rather than once. Inspired by this, we introduce SchemaMem, which models what the agent believes as a schema of named slots with an evidence ledger and scores each observation by how strongly it violates the schema's expectation. This one quantity drives the whole evolution: low-violation observations are compressed, repeated violations revise the belief, and an isolated strong violation is kept as a protected exception—a third outcome proxy-only systems structurally cannot produce. On the same retrieval backbone as a flat baseline, SchemaMem is competitive on LongMemEval and LoCoMo, with gains concentrated in knowledge-update and exception questions and parity on single-hop facts.

---

## 中文回译(供核意,非投稿文本)

随着大语言模型智能体从一次性问答走向跨越数周乃至数月的长时运行,记忆演化成为长时运行智能体的核心能力:它要把一串不断到来、时而矛盾的观测,提炼成一个始终最新的知识模型。当前工作沿着三条各自发展的机制来实现记忆演化——巩固、更新、遗忘。我们指出,这三条机制共享同一个缺陷:它们都不携带"期望",因而只能依据表层代理来决策——巩固凭相似度、更新凭新近度、遗忘凭时间与频率——而回避了唯一真正要紧的问题:一条新观测,相对于系统当前所信,究竟意味着什么。于是同一个决定被三种代理各自答歪,在同一类输入上一起失败:一次真实的改变与一次孤立的反常,被迫走同一条路。人类记忆用图式答对了这个问题:图式承载可分级的期望,把每条观测按其违反期望的程度来度量,并只在经验反复(而非一次)违反时才重构。受此启发,我们提出 SchemaMem:它把智能体所信建模为一个图式(具名槽位 + 证据账本),而图式提供的期望,使那个三支共需、却谁都算不出的信号第一次变得可算——观测对期望的违反度。正是这一个量统一驱动了全部演化:违反度低者被同化压缩,反复累积的违反把图式顺应为修订后的信念,而孤立的强违反被留作受保护的例外——这第三种结局,恰是仅靠表层代理的系统在结构上无法产生的,因而它本身就是"仲裁确实在发生"的证明。一条记忆只有当图式能将其重建到容差以内时才被释放遗忘;回答时,图式给出当前信念连同它已取代的历史链。在与扁平基线相同的检索骨架上,SchemaMem 在 LongMemEval 与 LoCoMo 上具有竞争力,增益集中于知识更新与例外类,而在单跳事实上与基线持平——用作"增益来自仲裁而非检索"的内建检验。

---

## Notes for the author (张老师 / 团队)

1. **Load-bearing thesis** (locked 2026-07-19): the paper's central claim is a COMMON DEFECT, not integration and not exception-retention-as-gap. Three mechanisms share one root — they use surface proxies (similarity/recency/time-frequency) because none carries an expectation; the right signal is the observation's violation of a schema expectation (residual). Schema is load-bearing because a residual is only computable if an expectation exists — this welds "why SchemaMem" to "why we can unify the three."
2. **Integration is a byproduct**, explicitly not sold as a contribution. **Protected exception is an existence proof** that arbitration is occurring (proxy-only systems structurally cannot produce this third outcome) — this argument does NOT depend on a benchmark measuring exception frequency, which is why it is more defensible than "exceptions are useful."
3. **RED LINE (honesty)**: "the three mechanisms share one root" is OUR synthesis. The Hu et al. 2026 survey names the three losses separately and never unifies them. Write it as "we argue / we identify," never as established consensus. The abstract opens the claim with "We argue."
4. **Reviewer comments 1–6 incorporated**: (1) motivation rests on robust schema properties (graded expectations + reconstruct-after-repeated-violation, Ghosh & Gilboa / Gilboa & Marlatte), NOT on the contested SLIMM congruent-vs-violating routing; CLS/SLIMM demoted to intro-level analogy. (2) no universal "always/never." (3) "supersede/invalidate," not "overwrite by recency" (Zep is time-aware). (4) "where merging occurs, by similarity," not all consolidation. (5) mechanism wording kept as "violation" (surprise), NOT "prediction residual / generative model likelihood" — left flexible pending a possible real algorithmic mechanism. (6) "temporal" DROPPED from the concentrated-gains claim to keep the falsification narrative clean (gains only on knowledge-update + exception).
5. **Result claim conservative ("competitive"); accuracy-only** (no token-efficiency claim anywhere).
6. **Consistency lock** (AAAI rejects without review if final abstract/title is *qualitatively different* from the registered one). Committed by BOTH variants: (a) competitive on LongMemEval + LoCoMo; (b) gains concentrated in knowledge-update + exception; (c) single-hop parity (falsification test). NOTE: to fit the 150–250 limit, the primary no longer states reconstruction-gated forgetting (d) — so (d) is NOT a locked claim in either variant. If forgetting must be a headline result, it has to be added back and something else cut. Back each committed claim with real numbers by Jul 28.
7. **Decide before registration**: which title, and which variant (primary locks (d), short does not).
