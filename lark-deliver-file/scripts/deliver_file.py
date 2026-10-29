#!/usr/bin/env python3
"""Upload one file to managed Feishu Drive storage and deliver its link."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


DEFAULT_CONFIG = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "lark-deliver-file/config.json"
)


class DeliveryError(RuntimeError):
    def __init__(self, stage: str, message: str, recovery: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.recovery = recovery


def required(value: Any, label: str, stage: str = "config") -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliveryError(stage, f"{label} must be a non-empty string")
    return value.strip()


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise DeliveryError("config", f"cannot read config {path}: {exc}") from exc
    if not isinstance(config, dict) or not isinstance(config.get("ledger"), dict):
        raise DeliveryError("config", "config must contain a ledger object")
    fields = config["ledger"].get("fields")
    if not isinstance(fields, dict):
        raise DeliveryError("config", "ledger.fields must be an object")
    for key in ("profile", "root_folder_token"):
        config[key] = required(config.get(key), key)
    if config["root_folder_token"].lower() in {"root", "none", "null"}:
        raise DeliveryError("config", "root_folder_token must be a dedicated folder")
    for key in ("base_token", "table_id"):
        config["ledger"][key] = required(config["ledger"].get(key), f"ledger.{key}")
    for key in ("file", "recipient", "category", "note"):
        fields[key] = required(fields.get(key), f"ledger.fields.{key}")
    return config


def safe_name(value: str, label: str) -> str:
    value = value.strip()
    if not value or len(value) > 80:
        raise DeliveryError("input", f"{label} must contain 1-80 characters")
    if value in {".", ".."} or re.search(r"[/\\\x00-\x1f]", value):
        raise DeliveryError("input", f"{label} cannot contain path separators or controls")
    return value


def cli(
    config: dict[str, Any],
    args: Sequence[str],
    stage: str,
    cwd: Path | None = None,
) -> dict[str, Any]:
    command = [os.environ.get("LARK_CLI_BIN", "lark-cli"), *args, "--profile", config["profile"]]
    env = os.environ.copy()
    env.update(
        LARKSUITE_CLI_NO_UPDATE_NOTIFIER="1",
        LARKSUITE_CLI_NO_SKILLS_NOTIFIER="1",
    )
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode:
        detail = result.stdout.strip() or result.stderr.strip()
        raise DeliveryError(stage, f"lark-cli failed ({result.returncode}): {detail}")
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DeliveryError(stage, "lark-cli did not return valid JSON") from exc
    if not isinstance(output, dict):
        raise DeliveryError(stage, "lark-cli result must be a JSON object")
    if output.get("ok") is False:
        raise DeliveryError(stage, json.dumps(output.get("error"), ensure_ascii=False))
    return output


def data(output: dict[str, Any]) -> dict[str, Any]:
    value = output.get("data", output)
    if not isinstance(value, dict):
        raise DeliveryError("response", "lark-cli response data must be an object")
    return value


def auth(config: dict[str, Any]) -> None:
    output = cli(config, ["auth", "status", "--json", "--verify"], "auth")
    user = output.get("identities", {}).get("user", {})
    if output.get("verified") is not True or user.get("status") != "ready":
        raise DeliveryError("auth", "configured user identity is not ready and verified")


def recipient(config: dict[str, Any], query: str) -> dict[str, str]:
    query = required(query, "recipient", "recipient")
    selector = ["--user-ids", query] if query.startswith("ou_") else ["--query", query]
    output = cli(
        config,
        ["contact", "+search-user", *selector, "--exclude-external-users", "--as", "user", "--format", "json"],
        "recipient",
    )
    users = data(output).get("users")
    if not isinstance(users, list):
        raise DeliveryError("recipient", "contact search returned no users array")
    unique = {
        item["open_id"]: item
        for item in users
        if isinstance(item, dict) and isinstance(item.get("open_id"), str)
    }
    if len(unique) != 1:
        names = [str(item.get("localized_name", "")) for item in unique.values()]
        raise DeliveryError("recipient", f"recipient must resolve uniquely; matches={names}")
    item = next(iter(unique.values()))
    if item.get("is_cross_tenant") is True or item.get("is_activated") is False:
        raise DeliveryError("recipient", "recipient must be an active internal user")
    return {
        "id": required(item.get("open_id"), "recipient.open_id", "recipient"),
        "name": required(item.get("localized_name") or item.get("open_id"), "recipient.name", "recipient"),
    }


def children(config: dict[str, Any], folder_token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(100):
        params: dict[str, Any] = {"folder_token": folder_token, "page_size": 200}
        if page_token:
            params["page_token"] = page_token
        output = cli(
            config,
            ["drive", "files", "list", "--params", json.dumps(params), "--as", "user", "--format", "json"],
            "folder-list",
        )
        page = data(output)
        files = page.get("files", [])
        if not isinstance(files, list):
            raise DeliveryError("folder-list", "drive returned invalid files")
        items.extend(item for item in files if isinstance(item, dict))
        if page.get("has_more") is not True:
            return items
        page_token = required(page.get("next_page_token"), "next_page_token", "folder-list")
    raise DeliveryError("folder-list", "folder listing exceeded 100 pages")


def folder(config: dict[str, Any], parent: str, name: str) -> str:
    matches = [
        item
        for item in children(config, parent)
        if item.get("type") == "folder" and item.get("name") == name
    ]
    if len(matches) > 1:
        raise DeliveryError("folder", f"multiple folders named {name!r} under parent")
    if matches:
        return required(matches[0].get("token"), "folder token", "folder")
    output = cli(
        config,
        ["drive", "+create-folder", "--folder-token", parent, "--name", name, "--as", "user", "--format", "json"],
        "folder-create",
    )
    return required(data(output).get("folder_token"), "created folder token", "folder-create")


def upload(
    config: dict[str, Any], local_file: Path, folder_token: str, remote_name: str
) -> tuple[str, str]:
    output = cli(
        config,
        [
            "drive", "+upload", "--file", f"./{local_file.name}",
            "--folder-token", folder_token, "--name", remote_name,
            "--as", "user", "--format", "json",
        ],
        "upload",
        local_file.parent,
    )
    uploaded = data(output)
    return required(uploaded.get("file_token"), "file token", "upload"), required(uploaded.get("url"), "file url", "upload")


def authorize(config: dict[str, Any], file_token: str, recipient_id: str) -> None:
    cli(
        config,
        [
            "drive", "+member-add", "--token", file_token, "--type", "file",
            "--member-id", recipient_id, "--member-type", "openid", "--perm", "edit",
            "--as", "user", "--format", "json", "--yes",
        ],
        "member-permission",
    )
    output = cli(
        config,
        [
            "api", "GET",
            f"/open-apis/drive/v1/permissions/{file_token}/members",
            "--params", json.dumps({"type": "file"}),
            "--as", "user", "--format", "json",
        ],
        "member-permission-read",
    )
    members = data(output).get("items")
    if not isinstance(members, list):
        raise DeliveryError("permission-verify", "member list is missing")
    granted = next(
        (
            item for item in members
            if isinstance(item, dict)
            and item.get("member_type") == "openid"
            and item.get("member_id") == recipient_id
        ),
        None,
    )
    if granted is None or granted.get("perm") not in {"edit", "full_access"}:
        raise DeliveryError(
            "permission-verify",
            "recipient edit permission was not confirmed",
        )

    params = json.dumps({"token": file_token, "type": "file"})
    output = cli(
        config,
        ["drive", "permission.public", "get", "--params", params, "--as", "user", "--format", "json"],
        "public-permission-read",
    )
    actual = data(output).get("permission_public")
    if not isinstance(actual, dict):
        raise DeliveryError("permission-verify", "permission_public is missing")
    security = actual.get("security_entity")
    allowed = {"anyone_can_view", "anyone_can_edit"}
    if granted["perm"] == "full_access":
        allowed.add("only_full_access")
    if security not in allowed:
        raise DeliveryError(
            "permission-verify",
            f"download setting does not permit recipient role: {security!r}",
        )


def message_text(name: str, url: str, category: str, note: str) -> str:
    text = f"### 文件交付\n\n- 分类：{category}\n- 文件：[{name}]({url})"
    return text + (f"\n- 说明：{note}" if note else "")


def send(
    config: dict[str, Any], recipient_id: str, markdown: str, file_token: str
) -> str:
    key = hashlib.sha256(f"{file_token}:{recipient_id}".encode()).hexdigest()[:32]
    output = cli(
        config,
        [
            "im", "+messages-send", "--user-id", recipient_id, "--markdown", markdown,
            "--idempotency-key", f"ldf-{key}", "--as", "user", "--format", "json",
        ],
        "message",
    )
    return required(data(output).get("message_id"), "message_id", "message")


def write_log(
    config: dict[str, Any], file_url: str, recipient_id: str, category: str, note: str
) -> list[str]:
    ledger = config["ledger"]
    fields = ledger["fields"]
    body = {
        "fields": [fields["file"], fields["recipient"], fields["category"], fields["note"]],
        "rows": [[file_url, [{"id": recipient_id}], category, note or None]],
    }
    output = cli(
        config,
        [
            "base", "+record-batch-create", "--base-token", ledger["base_token"],
            "--table-id", ledger["table_id"], "--json", json.dumps(body, ensure_ascii=False),
            "--as", "user", "--format", "json",
        ],
        "ledger",
    )
    record_ids = data(output).get("record_id_list")
    if not isinstance(record_ids, list) or not record_ids:
        raise DeliveryError("ledger", "Base write returned no record_id_list")
    return [str(value) for value in record_ids]


def deliver(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    try:
        local_file = Path(args.file).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise DeliveryError("input", str(exc)) from exc
    if not local_file.is_file():
        raise DeliveryError("input", f"not a regular file: {local_file}")
    category = safe_name(args.category, "category")
    remote_name = safe_name(args.name or local_file.name, "name")
    note = (args.note or "").strip()
    month = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")

    if args.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "identity": "user",
            "profile": config["profile"],
            "recipient_query": args.recipient,
            "archive_path": f"<configured-root>/{category}/{month}/{remote_name}",
            "steps": ["auth", "recipient", "folders", "upload", "authorize", "verify", "message", "log"],
        }
    if not args.yes:
        raise DeliveryError("confirmation", "real delivery requires --yes")

    auth(config)
    target = recipient(config, args.recipient)
    category_token = folder(config, config["root_folder_token"], category)
    month_token = folder(config, category_token, month)
    file_token, file_url = upload(config, local_file, month_token, remote_name)
    post_upload = {
        "file_url": file_url,
        "archive_path": f"{category}/{month}/{remote_name}",
        "recipient_id": target["id"],
        "category": category,
        "note": note,
    }
    try:
        authorize(config, file_token, target["id"])
        markdown = args.message or message_text(remote_name, file_url, category, note)
        message_id = send(config, target["id"], markdown, file_token)
    except DeliveryError as exc:
        raise DeliveryError(exc.stage, str(exc), post_upload) from exc

    log_values = {key: post_upload[key] for key in ("file_url", "recipient_id", "category", "note")}
    try:
        record_ids = write_log(config, **log_values)
    except DeliveryError as exc:
        raise DeliveryError(
            "ledger-after-send",
            f"message {message_id} was sent, but logging failed: {exc}",
            {**log_values, "message_id": message_id},
        ) from exc
    return {
        "ok": True,
        "file_url": file_url,
        "archive_path": f"{category}/{month}/{remote_name}",
        "recipient": target,
        "permission_verified": True,
        "message_id": message_id,
        "record_ids": record_ids,
    }


def log_only(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    if not args.yes:
        raise DeliveryError("confirmation", "log repair requires --yes")
    if not args.recipient_id.startswith("ou_") or not args.file_url.startswith("https://"):
        raise DeliveryError("input", "log repair needs an open_id and an https file URL")
    auth(config)
    record_ids = write_log(
        config,
        args.file_url,
        args.recipient_id,
        safe_name(args.category, "category"),
        (args.note or "").strip(),
    )
    return {"ok": True, "log_only": True, "record_ids": record_ids}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    deliver_parser = commands.add_parser("deliver")
    deliver_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    deliver_parser.add_argument("--file", required=True)
    deliver_parser.add_argument("--recipient", required=True)
    deliver_parser.add_argument("--category", required=True)
    deliver_parser.add_argument("--name")
    deliver_parser.add_argument("--note", default="")
    deliver_parser.add_argument("--message")
    deliver_parser.add_argument("--dry-run", action="store_true")
    deliver_parser.add_argument("--yes", action="store_true")
    log_parser = commands.add_parser("log")
    log_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    log_parser.add_argument("--file-url", required=True)
    log_parser.add_argument("--recipient-id", required=True)
    log_parser.add_argument("--category", required=True)
    log_parser.add_argument("--note", default="")
    log_parser.add_argument("--yes", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
        result = deliver(args, config) if args.command == "deliver" else log_only(args, config)
    except DeliveryError as exc:
        output: dict[str, Any] = {"ok": False, "stage": exc.stage, "error": str(exc)}
        if exc.recovery is not None:
            output["recovery"] = exc.recovery
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
