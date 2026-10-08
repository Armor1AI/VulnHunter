#!/bin/sh
set -eu

if [ -z "${HOME:-}" ]; then
    echo "error: HOME unset -- refusing to uninstall" >&2
    exit 1
fi

CONFIG_ROOT=${XDG_CONFIG_HOME:-"$HOME/.config"}/opencode
rm -rf "$CONFIG_ROOT/skills/vulnhunt"
rm -f "$CONFIG_ROOT/commands/vulnhunt.md"
rm -f "$CONFIG_ROOT/agents/vulnhunt-orchestrator.md"
rm -f "$CONFIG_ROOT/agents/vulnhunt-worker.md"
rm -f "$CONFIG_ROOT/vulnhunt.static.json"
echo "Uninstalled OpenCode VulnHunter scanner."
