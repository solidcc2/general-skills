---
name: lark-deliver-file
description: 将本地文件分类上传到受管理的飞书云盘目录，向唯一确定的内部收件人授予文件级可编辑权限，验证下载设置后通过飞书单聊发送文件链接，并在全部成功后向 Base 追加一条交付日志。当用户要求“把文件、压缩包、构建产物或日志通过飞书发给某人”时使用；不用于直接发送消息附件、上传到云盘根目录、发送给群聊或外部联系人。
---

# 飞书文件交付

> 前置条件：先使用可用的 `lark-shared` skill 检查认证。执行真实交付前，明确说明 profile、用户身份、收件人和消息内容。

## 固定边界

- 始终以 `user` 身份操作。
- 每次只交付一个普通文件给一个内部收件人。
- 始终上传到 `<专用根目录>/<分类>/<YYYY-MM>/`；禁止省略根目录 token。
- 始终授予收件人当前文件的 `edit` 权限，不授予交付目录权限。
- 保留文件现有公共权限和密级设置，不自动修改。
- 发送前读回确认收件人具有 `edit` 或 `full_access`，且下载设置允许该角色下载。
- 只有上传、授权、权限验证和单聊发送全部成功后，才向 Base 追加日志。
- Base 只保存成功日志，不保存失败状态或本地文件名。
- 不自动删除云盘文件、撤销权限、覆盖同名文件或回滚已经发送的消息。

## 一次性配置

创建一个专用根目录，例如“文件交付中心”。在该目录中创建 Base“文件交付日志”，首张表命名为“交付日志”，字段固定为：

```json
[
  {"name":"文件","type":"text","style":{"type":"url"}},
  {"name":"交付时间","type":"created_at","style":{"format":"yyyy-MM-dd HH:mm"}},
  {"name":"收件人","type":"user","multiple":false},
  {"name":"分类","type":"text"},
  {"name":"备注","type":"text"}
]
```

把 [config.example.json](config.example.json) 复制到 `~/.config/lark-deliver-file/config.json`，填写：

- `profile`：飞书 CLI profile。
- `root_folder_token`：专用根目录 token，不能为空。
- `ledger.base_token`、`ledger.table_id`：日志 Base 和表的真实标识。

不要把 appSecret、accessToken 或 refreshToken 写入配置。

## 执行流程

1. 确认本地文件、内部收件人、分类、发送身份和消息内容。
2. 如果收件人查询可能命中多人，先让用户选择；不得自动取第一条。
3. 先运行本地预览：

```bash
python3 ~/.codex/skills/lark-deliver-file/scripts/deliver_file.py deliver \
  --file ./artifact.zip \
  --recipient "张三" \
  --category "builds" \
  --note "可选说明" \
  --dry-run
```

4. 用户已明确批准收件人、内容和用户身份后，执行真实交付：

```bash
python3 ~/.codex/skills/lark-deliver-file/scripts/deliver_file.py deliver \
  --file ./artifact.zip \
  --recipient "张三" \
  --category "builds" \
  --note "可选说明" \
  --yes
```

可用 `--name` 指定云盘文件名，`--message` 覆盖默认单聊正文，`--config` 指定其他配置文件。

脚本按以下顺序执行且失败即停：认证校验、唯一解析收件人、确认分类目录、上传、添加可编辑成员、读回验证成员权限及下载设置、发送单聊、追加成功日志。

## 失败处理

- 权限未读回验证成功时，不发送链接。
- 发送前失败时，不写 Base 日志；报告具体阶段和已创建的云盘资源，不做自动删除。
- 发送成功但记账失败时，脚本返回 `recovery` JSON。只补写日志，不得重新发送消息：

```bash
python3 ~/.codex/skills/lark-deliver-file/scripts/deliver_file.py log \
  --file-url "<recovery.file_url>" \
  --recipient-id "<recovery.recipient_id>" \
  --category "<recovery.category>" \
  --note "<recovery.note>" \
  --yes
```

## 交付结果

向用户报告：云盘链接、归档分类、收件人、已验证的成员权限及下载设置、飞书消息 ID 和 Base 记录 ID。不把配置验证描述为收件人实际下载成功。不要把脚本内部 token、完整 CLI 输出或认证信息作为主要结果。
