# Triage Labels

这些技能用五个规范分诊角色来说话。这份文件把这些角色映射到这个仓库的议题跟踪器实际使用的标签字符串。

| mattpocock/skills 里的标签 | 我们跟踪器里的标签 | 含义 |
| -------------------------- | ------------------ | ---- |
| `needs-triage`             | `needs-triage`     | 维护者需要评估这条议题 |
| `needs-info`               | `needs-info`       | 等待报告者补充信息 |
| `ready-for-agent`          | `ready-for-agent`  | 已经完整说明，可以交给 AFK 代理 |
| `ready-for-human`          | `ready-for-human`  | 需要由人来实现 |
| `wontfix`                  | `wontfix`          | 不打算处理 |

当某个技能提到一个角色时（例如「套用 AFK 就绪的分诊标签」），就使用这张表里对应的标签字符串。

## Wayfinder 标签

`/wayfinder` 用下面五个标签区分地图与四种工单；它们只在寻路流程里使用，不要求每个议题都带：

| 标签 | 用途 |
| ---- | ---- |
| `wayfinder:map` | 探索地图：承载 Destination / Notes / Decisions so far / Fog 的那个议题 |
| `wayfinder:research` | 研究型工单（AFK）：查资料、第三方 API 或本地知识库，回答一个决策所依赖的事实 |
| `wayfinder:prototype` | 原型型工单（HITL）：做一个粗糙但具体的产物，把讨论的保真度提上来 |
| `wayfinder:grilling` | 讨论 / 决策型工单（HITL，默认类型）：通过对话把问题问清楚 |
| `wayfinder:task` | 前置任务型工单（HITL 或 AFK）：必须先完成的手工工作，完成后决策才能继续 |

后续打标签严格遵循技能规则，不额外强制任何标签。
