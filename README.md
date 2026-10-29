# General Skills

个人维护的 Codex 全局 skill 集合，用于跨项目复用沟通与执行原则、编码风格、系统图绘制和飞书文件交付流程。

## Skill 列表

| Skill | 用途 |
| --- | --- |
| [codex-operating-principles](codex-operating-principles/SKILL.md) | 保持沟通简洁、执行范围明确，避免未经要求的扩展和隐式兜底。 |
| [personal-coding-principles](personal-coding-principles/SKILL.md) | 统一状态建模、模块边界、生命周期、错误处理和渐进式重构原则。 |
| [design-system-route-diagrams](design-system-route-diagrams/SKILL.md) | 绘制系统调用链、消息流、服务交互及现状与目标迁移对比图，输出 SVG / Graphviz 图形。 |
| [lark-deliver-file](lark-deliver-file/SKILL.md) | 将文件归档到飞书专用目录，授予内部收件人文件级可编辑权限，验证下载设置后发送单聊链接，并记录成功交付日志。 |

## 目录结构

每个 skill 以独立目录维护：

```text
<skill-name>/
├── SKILL.md       # 用途、适用范围和执行流程
├── agents/        # 可选：界面元数据
├── scripts/       # 可选：执行脚本
├── references/    # 可选：按需读取的参考资料
└── assets/        # 可选：模板与其他资源
```

`.system/` 为系统内置 skill 目录，已由 `.gitignore` 排除，不属于本仓库维护的自定义内容。

## 使用方式

先阅读对应目录的 `SKILL.md`，确认适用范围、依赖和执行边界。可在对话中明确指定 skill，例如：

```text
请使用 $design-system-route-diagrams 绘制这份方案的消息流图。
```

涉及外部服务的 skill 需要单独配置对应工具、身份及目标资源。飞书文件交付的配置步骤见 [lark-deliver-file](lark-deliver-file/SKILL.md)；凭据和真实交付配置不应写入本仓库。

## 维护范围

- 全局 skill 保存跨项目可复用的规则与流程。
- 固定仓库路径、机器人台架、项目构建链路等项目专属内容放在对应工作区的 `.agents/skills/` 下。
- 更新 skill 时同步维护说明和脚本，明确副作用及失败停止条件。
- Skill 不扩大用户授权范围；提交、推送、权限变更和消息发送仍遵循当前任务授权与所在项目约定。
