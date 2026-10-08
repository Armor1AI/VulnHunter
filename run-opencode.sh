#!/bin/sh
set -eu

if [ "$#" -gt 1 ]; then
    echo "usage: $0 [repository]" >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
TARGET=${1:-.}
OPENCODE_BIN=${OPENCODE_BIN:-opencode}

command -v git >/dev/null 2>&1 || { echo "error: git is required" >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "error: tar is required" >&2; exit 1; }
command -v readlink >/dev/null 2>&1 || { echo "error: readlink is required" >&2; exit 1; }
command -v "$OPENCODE_BIN" >/dev/null 2>&1 || {
    echo "error: OpenCode not found: $OPENCODE_BIN" >&2
    exit 1
}

SOURCE_ROOT=$(git -C "$TARGET" rev-parse --show-toplevel 2>/dev/null) || {
    echo "error: repository must be a Git checkout" >&2
    exit 1
}
if [ -n "$(git -C "$SOURCE_ROOT" status --porcelain --untracked-files=all)" ]; then
    echo "error: repository must be clean; the isolated scan uses the committed HEAD" >&2
    exit 1
fi

TEMP_BASE=${TMPDIR:-/tmp}
TEMP_BASE=${TEMP_BASE%/}
WORK_ROOT_RAW=$(mktemp -d "$TEMP_BASE/vulnhunter-opencode.XXXXXX")
WORK_ROOT=$(CDPATH='' cd -- "$WORK_ROOT_RAW" && pwd -P)
WORKSPACE="$WORK_ROOT/repo"
SAFE_CONFIG="$WORKSPACE/.opencode"
SNAPSHOT_GIT="$WORK_ROOT/snapshot.git"
SNAPSHOT_INDEX="$WORK_ROOT/index"
SNAPSHOT_WORK="$WORK_ROOT/snapshot-work"
RIPGREP_CONFIG="$WORK_ROOT/empty-ripgreprc"
mkdir -p "$WORKSPACE" "$SAFE_CONFIG/agents" "$SAFE_CONFIG/commands" \
    "$SAFE_CONFIG/skills" "$WORK_ROOT/home" "$WORK_ROOT/xdg" "$SNAPSHOT_WORK"
: > "$RIPGREP_CONFIG"

COMMIT=$(git -C "$SOURCE_ROOT" rev-parse HEAD)
git clone --bare --shared -q "$SOURCE_ROOT" "$SNAPSHOT_GIT"

export GIT_DIR="$SNAPSHOT_GIT"
export GIT_WORK_TREE="$SNAPSHOT_WORK"
export GIT_INDEX_FILE="$SNAPSHOT_INDEX"
git read-tree "$COMMIT"

git ls-files --stage > "$WORK_ROOT/index-entries"
if grep -q '^160000 ' "$WORK_ROOT/index-entries"; then
    echo "error: repositories with submodules are not supported" >&2
    exit 1
fi

git ls-files -z -- \
    '.gitattributes' ':(glob)**/.gitattributes' \
    '.gitignore' ':(glob)**/.gitignore' \
    '.ignore' ':(glob)**/.ignore' \
    '.rgignore' ':(glob)**/.rgignore' \
    'AGENTS.md' ':(glob)**/AGENTS.md' \
    'CLAUDE.md' ':(glob)**/CLAUDE.md' \
    '.github/copilot-instructions.md' \
    '.agents' '.agents/**' '.claude' '.claude/**' \
    '.opencode' '.opencode/**' 'opencode.json' 'opencode.jsonc' \
    > "$WORK_ROOT/excluded-paths"
git update-index --force-remove -z --stdin < "$WORK_ROOT/excluded-paths"
SNAPSHOT_TREE=$(git write-tree)

set +e
git grep -I -l '^version https://git-lfs.github.com/spec/v1$' "$SNAPSHOT_TREE" -- \
    > "$WORK_ROOT/lfs-pointers"
LFS_STATUS=$?
set -e
case "$LFS_STATUS" in
    0)
        echo "error: repositories with Git LFS pointers are not supported" >&2
        exit 1
        ;;
    1) ;;
    *)
        echo "error: could not inspect the committed tree for Git LFS pointers" >&2
        exit 1
        ;;
esac

unset GIT_WORK_TREE GIT_INDEX_FILE
GIT_ATTR_NOSYSTEM=1 git -c core.attributesFile=/dev/null \
    archive --format=tar --output="$WORK_ROOT/snapshot.tar" "$SNAPSHOT_TREE"
tar -xf "$WORK_ROOT/snapshot.tar" -C "$WORKSPACE"
unset GIT_DIR

find "$WORKSPACE" -type l -exec sh -c '
    set -eu
    for LINK do
        DESTINATION=$(readlink "$LINK")
        rm -f -- "$LINK"
        printf "symlink target: %s\n" "$DESTINATION" > "$LINK"
    done
' sh {} +

cp -R "$SCRIPT_DIR/vulnhunt" "$SAFE_CONFIG/skills/vulnhunt"
cp "$SCRIPT_DIR/opencode/agents/vulnhunt-orchestrator.md" "$SAFE_CONFIG/agents/"
cp "$SCRIPT_DIR/opencode/agents/vulnhunt-worker.md" "$SAFE_CONFIG/agents/"
cp "$SCRIPT_DIR/opencode/commands/vulnhunt.md" "$SAFE_CONFIG/commands/"

REPOSITORY_URL=$(git -C "$SOURCE_ROOT" remote get-url origin 2>/dev/null || basename "$SOURCE_ROOT")
case "$REPOSITORY_URL" in
    git@github.com:*) REPOSITORY_URL="https://github.com/${REPOSITORY_URL#git@github.com:}" ;;
esac
case "$REPOSITORY_URL" in
    *://*)
        URL_SCHEME=${REPOSITORY_URL%%://*}
        URL_LOCATION=${REPOSITORY_URL#*://}
        URL_LOCATION=${URL_LOCATION%%\#*}
        URL_LOCATION=${URL_LOCATION%%\?*}
        URL_LOCATION=${URL_LOCATION##*@}
        REPOSITORY_URL="$URL_SCHEME://$URL_LOCATION"
        ;;
esac
REPOSITORY_URL=${REPOSITORY_URL%.git}
case "$REPOSITORY_URL" in
    *[!A-Za-z0-9._~:/-]*) REPOSITORY_URL=unknown ;;
esac
BRANCH=$(git -C "$SOURCE_ROOT" branch --show-current)
SHORT_SHA=$(git -C "$SOURCE_ROOT" rev-parse --short HEAD)
[ -n "$BRANCH" ] || BRANCH=unknown
REPO_NAME=$(printf '%s' "$(basename "$SOURCE_ROOT")" | tr -c 'A-Za-z0-9._-' '_')
RESULT_NAME="${REPO_NAME}_VULNHUNT_RESULTS_$(date -u +%Y-%m-%d-%H%M%S)"
mkdir "$WORKSPACE/$RESULT_NAME"

PROMPT="Load the vulnhunt skill and follow it exactly. Perform an explicitly authorized static, no-Bash security review of this repository.

Pre-resolved scan metadata:
- VULNHUNT_DIR: $WORKSPACE/$RESULT_NAME
- VULNHUNT_BRANCH: $BRANCH [$SHORT_SHA]
- Repository URL: $REPOSITORY_URL"

RUN_HELP=$($OPENCODE_BIN run --help 2>&1)
set -- run
case "$RUN_HELP" in *--standalone*) set -- "$@" --standalone ;; esac
case "$RUN_HELP" in *--pure*) set -- "$@" --pure ;; esac
set -- "$@" --auto --agent vulnhunt-orchestrator "$PROMPT"

echo "Scanning committed snapshot $SHORT_SHA in isolated workspace: $WORKSPACE"
set +e
(
    cd "$WORKSPACE"
    HOME="$WORK_ROOT/home" \
    XDG_CONFIG_HOME="$WORK_ROOT/xdg" \
    OPENCODE_CONFIG_DIR="$SAFE_CONFIG" \
    OPENCODE_CONFIG_CONTENT="$(cat "$SCRIPT_DIR/opencode/opencode.vulnhunt.json")" \
    OPENCODE_DISABLE_AUTOUPDATE=true \
    OPENCODE_DISABLE_CLAUDE_CODE=1 \
    OPENCODE_DISABLE_EXTERNAL_SKILLS=1 \
    OPENCODE_DISABLE_PROJECT_CONFIG=true \
    OPENCODE_DISABLE_DEFAULT_PLUGINS=true \
    RIPGREP_CONFIG_PATH="$RIPGREP_CONFIG" \
    "$OPENCODE_BIN" "$@"
)
STATUS=$?
set -e

if [ "$STATUS" -ne 0 ]; then
    echo "error: scan failed; workspace preserved at $WORKSPACE" >&2
    exit "$STATUS"
fi

PHASE1_OUTPUT="$WORKSPACE/$RESULT_NAME/phase1_output.md"
IFS= read -r PARTITION_HEADER < "$PHASE1_OUTPUT" || PARTITION_HEADER=
case "$PARTITION_HEADER" in
    "PARTITION_COUNT: "*) PARTITION_COUNT=${PARTITION_HEADER#PARTITION_COUNT: } ;;
    *)
        echo "error: phase1_output.md must start with PARTITION_COUNT: N" >&2
        echo "error: scan incomplete; workspace preserved at $WORKSPACE" >&2
        exit 1
        ;;
esac
case "$PARTITION_COUNT" in
    ''|*[!0-9]*)
        echo "error: phase1_output.md has an invalid partition count" >&2
        echo "error: scan incomplete; workspace preserved at $WORKSPACE" >&2
        exit 1
        ;;
esac

MISSING_OUTPUT=0
ACTUAL_PARTITIONS=0
for PARTITION in "$WORKSPACE/$RESULT_NAME"/partitions/sg-*_data.md; do
    [ -f "$PARTITION" ] || continue
    ACTUAL_PARTITIONS=$((ACTUAL_PARTITIONS + 1))
    PARTITION_ID=${PARTITION##*/sg-}
    PARTITION_ID=${PARTITION_ID%_data.md}
    IFS= read -r REACHABILITY < "$PARTITION" || REACHABILITY=
    case "$REACHABILITY" in
        "REACHABILITY: DEV-ONLY") continue ;;
        "REACHABILITY: PRODUCTION") ;;
        *)
            echo "error: invalid partition reachability: ${PARTITION##*/}" >&2
            MISSING_OUTPUT=1
            continue
            ;;
    esac
    for CLASS in inj nav log; do
        RESULT="$WORKSPACE/$RESULT_NAME/results/sg-${PARTITION_ID}_${CLASS}_results.md"
        if [ ! -s "$RESULT" ]; then
            echo "error: missing scan result: ${RESULT##*/}" >&2
            MISSING_OUTPUT=1
        fi
    done
done
if [ "$ACTUAL_PARTITIONS" -ne "$PARTITION_COUNT" ]; then
    echo "error: expected $PARTITION_COUNT partition files, found $ACTUAL_PARTITIONS" >&2
    MISSING_OUTPUT=1
fi
if [ ! -s "$WORKSPACE/$RESULT_NAME/results/sink_driven_results.md" ]; then
    echo "error: missing scan result: sink_driven_results.md" >&2
    MISSING_OUTPUT=1
fi
for REQUIRED_OUTPUT in phase2b_output.md phase3_output.md phase3d_output.md README.md; do
    if [ ! -s "$WORKSPACE/$RESULT_NAME/$REQUIRED_OUTPUT" ]; then
        echo "error: missing scan output: $REQUIRED_OUTPUT" >&2
        MISSING_OUTPUT=1
    fi
done
if [ "$MISSING_OUTPUT" -ne 0 ]; then
    echo "error: scan incomplete; workspace preserved at $WORKSPACE" >&2
    exit 1
fi

echo "Report: $WORKSPACE/$RESULT_NAME/README.md"
