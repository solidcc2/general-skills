#!/usr/bin/env python3
"""Validate the business-fact manifest used by a route diagram."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


KINDS = {"runtime-component", "logical-service", "device", "system-boundary"}
SCOPES = {"end-to-end", "ingress-only", "egress-only"}
PANELS = {"current", "target", "both"}
CALL_INTENT = re.compile(r"(?:调用|\bcall(?:s|ed|ing)?\b|\binvok(?:e|es|ed|ing)\b)", re.IGNORECASE)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_fact_manifest.py <manifest.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"invalid manifest: {error}", file=sys.stderr)
        return 1

    errors: list[str] = []
    components = data.get("components")
    routes = data.get("routes")
    if not isinstance(components, list) or not isinstance(routes, list):
        print("manifest must contain list fields: components, routes", file=sys.stderr)
        return 1

    component_ids: set[str] = set()
    alias_owner: dict[str, str] = {}
    component_kind: dict[str, str] = {}
    for index, component in enumerate(components):
        where = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{where}: must be an object")
            continue
        component_id = component.get("id")
        kind = component.get("kind")
        aliases = component.get("aliases", [])
        if not isinstance(component_id, str) or not component_id:
            errors.append(f"{where}.id: required non-empty string")
            continue
        if component_id in component_ids:
            errors.append(f"{where}.id: duplicate component id {component_id!r}")
        component_ids.add(component_id)
        component_kind[component_id] = kind
        if kind not in KINDS:
            errors.append(f"{where}.kind: expected one of {sorted(KINDS)}, got {kind!r}")
        if not isinstance(aliases, list) or not all(isinstance(x, str) and x for x in aliases):
            errors.append(f"{where}.aliases: expected a list of non-empty strings")
            continue
        for alias in [component_id, *aliases]:
            key = " ".join(alias.casefold().split())
            owner = alias_owner.get(key)
            if owner is not None and owner != component_id:
                errors.append(
                    f"{where}.aliases: {alias!r} already belongs to component {owner!r}"
                )
            alias_owner[key] = component_id

    route_keys: set[tuple[str, str]] = set()
    routes_by_panel_id: dict[tuple[str, str], dict] = {}
    for index, route in enumerate(routes):
        where = f"routes[{index}]"
        if not isinstance(route, dict):
            errors.append(f"{where}: must be an object")
            continue
        route_id = route.get("id")
        short_name = route.get("short_name")
        panel = route.get("panel")
        nodes = route.get("nodes")
        scope = route.get("scope")
        named_target = route.get("named_target")
        provider = route.get("provider")
        status = route.get("status")
        style = route.get("style")
        if not isinstance(route_id, str) or not route_id:
            errors.append(f"{where}.id: required non-empty string")
        if not isinstance(short_name, str) or not short_name.strip():
            errors.append(f"{where}.short_name: required non-empty fact-item title")
        if panel not in PANELS:
            errors.append(f"{where}.panel: expected one of {sorted(PANELS)}, got {panel!r}")
        if isinstance(route_id, str) and panel in PANELS:
            key = (panel, route_id)
            if key in route_keys:
                errors.append(f"{where}: duplicate route id {route_id!r} in panel {panel!r}")
            route_keys.add(key)
            routes_by_panel_id[key] = route
        if not isinstance(nodes, list) or len(nodes) < 2 or not all(
            isinstance(node, str) and node for node in nodes
        ):
            errors.append(f"{where}.nodes: expected at least two component ids")
            nodes = []
        for node in nodes:
            if node not in component_ids:
                errors.append(f"{where}.nodes: unknown component {node!r}")
        if scope not in SCOPES:
            errors.append(f"{where}.scope: expected one of {sorted(SCOPES)}, got {scope!r}")
        if style not in {"solid", "dashed"}:
            errors.append(f"{where}.style: expected solid or dashed, got {style!r}")
        if style == "dashed" and scope == "end-to-end" and status not in {
            "suspended",
            "uncertain",
        }:
            errors.append(
                f"{where}.style: closed end-to-end route must be solid unless suspended/uncertain"
            )
        if named_target is not None and (
            not isinstance(named_target, str) or named_target not in component_ids
        ):
            errors.append(f"{where}.named_target: expected null or a known component id")
        if isinstance(short_name, str) and CALL_INTENT.search(short_name):
            if not isinstance(named_target, str) or not named_target:
                errors.append(
                    f"{where}.named_target: required because short_name expresses a call/invoke intent"
                )
        if isinstance(named_target, str) and named_target in component_ids:
            if scope != "end-to-end":
                errors.append(f"{where}.scope: named target requires end-to-end scope")
            if provider != named_target:
                errors.append(
                    f"{where}.provider: named target {named_target!r} must be the provider"
                )
            if nodes and nodes[-1] != named_target:
                errors.append(
                    f"{where}: route with named target must end at {named_target!r}, "
                    f"got {nodes[-1]!r}"
                )
        if scope == "end-to-end":
            if not isinstance(provider, str) or not provider:
                errors.append(f"{where}.provider: required for end-to-end route")
            elif provider not in component_ids:
                errors.append(f"{where}.provider: unknown component {provider!r}")
            elif nodes and nodes[-1] != provider:
                errors.append(
                    f"{where}: end-to-end route must end at provider {provider!r}, "
                    f"got {nodes[-1]!r}"
                )
        else:
            evidence = route.get("scope_evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                errors.append(f"{where}.scope_evidence: required for non-end-to-end route")
        if isinstance(provider, str) and provider in component_kind:
            if component_kind[provider] not in KINDS:
                errors.append(f"{where}.provider: provider has invalid component kind")

    if data.get("mode") == "migration":
        disposition = data.get("component_disposition")
        if not isinstance(disposition, dict):
            errors.append("component_disposition: required in migration mode")
            disposition = {}
        else:
            for component_id in component_ids:
                state = disposition.get(component_id)
                if state not in {"retained", "retired", "new"}:
                    errors.append(
                        f"component_disposition[{component_id!r}]: expected retained, retired, or new"
                    )
            unknown = sorted(set(disposition) - component_ids)
            for component_id in unknown:
                errors.append(f"component_disposition: unknown component {component_id!r}")
        retired = {
            component_id
            for component_id, state in disposition.items()
            if state == "retired"
        }
        for (panel, route_id), target_route in routes_by_panel_id.items():
            if panel != "target":
                continue
            current_route = routes_by_panel_id.get(("current", route_id))
            if current_route is None:
                continue
            current_nodes = current_route.get("nodes", [])
            target_nodes = target_route.get("nodes", [])
            forbidden = [node for node in target_nodes if node in retired]
            if forbidden:
                errors.append(
                    f"target route {route_id!r}: contains retired components {forbidden!r}"
                )
            actual_removed = [node for node in current_nodes if node not in target_nodes]
            actual_added = [node for node in target_nodes if node not in current_nodes]
            migration = target_route.get("migration")
            where = f"target route {route_id!r}"
            if not isinstance(migration, dict):
                errors.append(f"{where}.migration: required in migration mode")
                continue
            declared_removed = migration.get("removed_nodes", [])
            declared_added = migration.get("added_nodes", [])
            if declared_removed != actual_removed:
                errors.append(
                    f"{where}.migration.removed_nodes: expected {actual_removed!r}, "
                    f"got {declared_removed!r}"
                )
            if declared_added != actual_added:
                errors.append(
                    f"{where}.migration.added_nodes: expected {actual_added!r}, "
                    f"got {declared_added!r}"
                )
            if (actual_removed or actual_added) and not str(migration.get("evidence", "")).strip():
                errors.append(f"{where}.migration.evidence: required for node changes")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"valid: {len(components)} components, {len(routes)} panel routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
