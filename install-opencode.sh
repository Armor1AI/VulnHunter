#!/bin/sh
set -eu

if [ -z "${HOME:-}" ]; then
    echo "error: HOME unset -- refusing to install" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONFIG_ROOT=${XDG_CONFIG_HOME:-"$HOME/.config"}/opencode
SKILL_DST="$CONFIG_ROOT/skills/vulnhunt"
COMMAND_DST="$CONFIG_ROOT/commands/vulnhunt.md"
AGENT_DIR="$CONFIG_ROOT/agents"
PROFILE_DST="$CONFIG_ROOT/vulnhunt.static.json"

mkdir -p "$CONFIG_ROOT/skills" "$CONFIG_ROOT/commands" "$AGENT_DIR"
rm -rf "$SKILL_DST"
cp -R "$SCRIPT_DIR/vulnhunt" "$SKILL_DST"
cp "$SCRIPT_DIR/opencode/commands/vulnhunt.md" "$COMMAND_DST"
cp "$SCRIPT_DIR/opencode/agents/vulnhunt-orchestrator.md" "$AGENT_DIR/vulnhunt-orchestrator.md"
cp "$SCRIPT_DIR/opencode/agents/vulnhunt-worker.md" "$AGENT_DIR/vulnhunt-worker.md"
cp "$SCRIPT_DIR/opencode/opencode.vulnhunt.json" "$PROFILE_DST"

echo "Installed OpenCode VulnHunter scanner:"
echo "  skill:   $SKILL_DST"
echo "  command: $COMMAND_DST"
echo "  agents:  $AGENT_DIR/vulnhunt-{orchestrator,worker}.md"
echo "  profile: $PROFILE_DST"
echo "Run: OPENCODE_CONFIG=$PROFILE_DST opencode run --agent vulnhunt-orchestrator \"Load the vulnhunt skill and scan the current repository.\""
