#!/bin/sh
set -eu

if [ "$#" -gt 1 ]; then
    echo "usage: $0 [repository]" >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
TARGET=${1:-.}
OPENCODE_BIN=${OPENCODE_BIN:-opencode}
TRUSTED_OPENCODE_CONFIG=${OPENCODE_CONFIG:-}

case "$OPENCODE_BIN" in
    */*) ;;
    *) OPENCODE_BIN=$(command -v "$OPENCODE_BIN" 2>/dev/null || true) ;;
esac
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin
export PATH

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
    GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS \
    GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM TAR_OPTIONS
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_SYSTEM=/dev/null
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_NO_LAZY_FETCH=1
export GIT_OPTIONAL_LOCKS=0
export GIT_TERMINAL_PROMPT=0

command -v git >/dev/null 2>&1 || { echo "error: git is required" >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "error: tar is required" >&2; exit 1; }
command -v readlink >/dev/null 2>&1 || { echo "error: readlink is required" >&2; exit 1; }
command -v "$OPENCODE_BIN" >/dev/null 2>&1 || {
    echo "error: OpenCode not found: $OPENCODE_BIN" >&2
    exit 1
}

SOURCE_ROOT=$(git -c core.fsmonitor=false -C "$TARGET" rev-parse --show-toplevel 2>/dev/null) || {
    echo "error: repository must be a Git checkout" >&2
    exit 1
}
if [ -n "$(git -c core.fsmonitor=false -C "$SOURCE_ROOT" status --porcelain --untracked-files=all)" ]; then
    echo "error: repository must be clean; the isolated scan uses the committed HEAD" >&2
    exit 1
fi

WORK_ROOT_RAW=$(mktemp -d /tmp/vulnhunter-opencode.XXXXXX)
WORK_ROOT=$(CDPATH='' cd -- "$WORK_ROOT_RAW" && pwd -P)
WORKSPACE="$WORK_ROOT/repo"
SAFE_CONFIG="$WORKSPACE/.opencode"
SNAPSHOT_GIT="$WORK_ROOT/snapshot.git"
SNAPSHOT_INDEX="$WORK_ROOT/index"
SNAPSHOT_WORK="$WORK_ROOT/snapshot-work"
mkdir -p "$WORKSPACE" "$SAFE_CONFIG/agents" "$SAFE_CONFIG/commands" \
    "$SAFE_CONFIG/skills" "$WORK_ROOT/home" "$WORK_ROOT/xdg/config" \
    "$WORK_ROOT/xdg/data" "$WORK_ROOT/xdg/cache" "$WORK_ROOT/xdg/state" \
    "$WORK_ROOT/xdg/runtime" "$WORK_ROOT/tmp" "$SNAPSHOT_WORK"

STATIC_PROFILE=$(cat "$SCRIPT_DIR/opencode/opencode.vulnhunt.json")
run_isolated_opencode() {
    env -i \
        PATH="$PATH" \
        HOME="$WORK_ROOT/home" \
        XDG_CONFIG_HOME="$WORK_ROOT/xdg/config" \
        XDG_DATA_HOME="$WORK_ROOT/xdg/data" \
        XDG_CACHE_HOME="$WORK_ROOT/xdg/cache" \
        XDG_STATE_HOME="$WORK_ROOT/xdg/state" \
        XDG_RUNTIME_DIR="$WORK_ROOT/xdg/runtime" \
        TMPDIR="$WORK_ROOT/tmp" \
        GIT_CONFIG_NOSYSTEM=1 \
        GIT_CONFIG_SYSTEM=/dev/null \
        GIT_CONFIG_GLOBAL=/dev/null \
        GIT_NO_LAZY_FETCH=1 \
        GIT_OPTIONAL_LOCKS=0 \
        GIT_TERMINAL_PROMPT=0 \
        OPENCODE_CONFIG="$TRUSTED_OPENCODE_CONFIG" \
        OPENCODE_CONFIG_DIR="$SAFE_CONFIG" \
        OPENCODE_CONFIG_CONTENT="$STATIC_PROFILE" \
        OPENCODE_PURE=1 \
        OPENCODE_DISABLE_AUTOUPDATE=true \
        OPENCODE_DISABLE_CHANNEL_DB=1 \
        OPENCODE_DISABLE_CLAUDE_CODE=1 \
        OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1 \
        OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 \
        OPENCODE_DISABLE_DEFAULT_PLUGINS=true \
        OPENCODE_DISABLE_EMBEDDED_WEB_UI=1 \
        OPENCODE_DISABLE_EXTERNAL_SKILLS=1 \
        OPENCODE_DISABLE_FFF=1 \
        OPENCODE_DISABLE_FILEWATCHER=1 \
        OPENCODE_FILEWATCHER_DISABLE=1 \
        OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER=1 \
        OPENCODE_DISABLE_LSP_DOWNLOAD=true \
        OPENCODE_DISABLE_MODELS_FETCH=true \
        OPENCODE_DISABLE_PROJECT_CONFIG=true \
        OPENCODE_CONFIG_PROJECT_DISABLE=true \
        OPENCODE_DISABLE_SHARE=1 \
        OPENCODE_DISABLE_TERMINAL_TITLE=1 \
        "$OPENCODE_BIN" "$@"
}

OPENCODE_VERSION=$(
    run_isolated_opencode --version 2>/dev/null \
        | awk 'match($0, /[0-9]+\.[0-9]+\.[0-9]+/) { print substr($0, RSTART, RLENGTH); exit }'
)
case "$OPENCODE_VERSION" in
    '') echo "error: could not determine OpenCode version" >&2; exit 1 ;;
esac
VERSION_MAJOR=${OPENCODE_VERSION%%.*}
VERSION_REST=${OPENCODE_VERSION#*.}
VERSION_MINOR=${VERSION_REST%%.*}
VERSION_PATCH=${VERSION_REST#*.}
if [ "$VERSION_MAJOR" -lt 1 ] || \
    { [ "$VERSION_MAJOR" -eq 1 ] && [ "$VERSION_MINOR" -lt 18 ]; } || \
    { [ "$VERSION_MAJOR" -eq 1 ] && [ "$VERSION_MINOR" -eq 18 ] && [ "$VERSION_PATCH" -lt 31 ]; }; then
    echo "error: OpenCode 1.18.31 or later is required; found $OPENCODE_VERSION" >&2
    exit 1
fi

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
    ':(icase).gitattributes' ':(icase,glob)**/.gitattributes' \
    ':(icase).gitignore' ':(icase,glob)**/.gitignore' \
    ':(icase).ignore' ':(icase,glob)**/.ignore' \
    ':(icase).rgignore' ':(icase,glob)**/.rgignore' \
    ':(icase)AGENTS.md' ':(icase,glob)**/AGENTS.md' \
    ':(icase)CLAUDE.md' ':(icase,glob)**/CLAUDE.md' \
    ':(icase)CONTEXT.md' ':(icase,glob)**/CONTEXT.md' \
    ':(icase).github/copilot-instructions.md' \
    ':(icase).agents' ':(icase).agents/**' ':(icase,glob)**/.agents/**' \
    ':(icase).claude' ':(icase).claude/**' ':(icase,glob)**/.claude/**' \
    ':(icase).opencode' ':(icase).opencode/**' ':(icase,glob)**/.opencode/**' \
    ':(icase)opencode.json' ':(icase)opencode.jsonc' \
    ':(icase,glob)**/opencode.json' ':(icase,glob)**/opencode.jsonc' \
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

git init -q "$WORKSPACE"
for IGNORE_FILE in .gitignore .ignore .rgignore; do
    printf '!**\n' > "$WORKSPACE/$IGNORE_FILE"
done

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
RESULT_ROOT="$WORKSPACE/$RESULT_NAME"
mkdir "$RESULT_ROOT"

chmod -R a-w "$WORKSPACE"
chmod u+w "$RESULT_ROOT"

PROMPT="Load the vulnhunt skill and follow it exactly. Perform an explicitly authorized static, no-Bash security review of this repository.

Pre-resolved scan metadata:
- VULNHUNT_DIR: $RESULT_ROOT
- VULNHUNT_BRANCH: $BRANCH [$SHORT_SHA]
- Repository URL: $REPOSITORY_URL"

RUN_HELP=$(cd "$WORKSPACE" && run_isolated_opencode run --help 2>&1)
set -- run
case "$RUN_HELP" in *--standalone*) set -- "$@" --standalone ;; esac
case "$RUN_HELP" in *--pure*) set -- "$@" --pure ;; esac
set -- "$@" --auto --agent vulnhunt-orchestrator "$PROMPT"

echo "Scanning committed snapshot $SHORT_SHA in isolated workspace: $WORKSPACE"
set +e
(
    cd "$WORKSPACE"
    run_isolated_opencode "$@"
)
STATUS=$?
set -e

if [ "$STATUS" -ne 0 ]; then
    echo "error: scan failed; workspace preserved at $WORKSPACE" >&2
    exit "$STATUS"
fi

PHASE1_OUTPUT="$RESULT_ROOT/phase1_output.md"
if [ ! -f "$PHASE1_OUTPUT" ] || [ -L "$PHASE1_OUTPUT" ] || [ ! -s "$PHASE1_OUTPUT" ]; then
    echo "error: missing scan output: phase1_output.md" >&2
    echo "error: scan incomplete; workspace preserved at $WORKSPACE" >&2
    exit 1
fi
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
for PARTITION in "$RESULT_ROOT"/partitions/sg-*_data.md; do
    [ -e "$PARTITION" ] || continue
    if [ ! -f "$PARTITION" ] || [ -L "$PARTITION" ] || [ ! -s "$PARTITION" ]; then
        echo "error: invalid partition artifact: ${PARTITION##*/}" >&2
        MISSING_OUTPUT=1
        continue
    fi
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
        RESULT="$RESULT_ROOT/results/sg-${PARTITION_ID}_${CLASS}_results.md"
        if [ ! -f "$RESULT" ] || [ -L "$RESULT" ] || [ ! -s "$RESULT" ]; then
            echo "error: missing scan result: ${RESULT##*/}" >&2
            MISSING_OUTPUT=1
        fi
    done
done
if [ "$ACTUAL_PARTITIONS" -ne "$PARTITION_COUNT" ]; then
    echo "error: expected $PARTITION_COUNT partition files, found $ACTUAL_PARTITIONS" >&2
    MISSING_OUTPUT=1
fi
if [ ! -f "$RESULT_ROOT/results/sink_driven_results.md" ] || \
    [ -L "$RESULT_ROOT/results/sink_driven_results.md" ] || \
    [ ! -s "$RESULT_ROOT/results/sink_driven_results.md" ]; then
    echo "error: missing scan result: sink_driven_results.md" >&2
    MISSING_OUTPUT=1
fi
for REQUIRED_OUTPUT in phase2b_output.md README.md findings.manifest; do
    if [ ! -f "$RESULT_ROOT/$REQUIRED_OUTPUT" ] || \
        [ -L "$RESULT_ROOT/$REQUIRED_OUTPUT" ] || \
        [ ! -s "$RESULT_ROOT/$REQUIRED_OUTPUT" ]; then
        echo "error: missing scan output: $REQUIRED_OUTPUT" >&2
        MISSING_OUTPUT=1
    fi
done
if [ "$MISSING_OUTPUT" -ne 0 ]; then
    echo "error: scan incomplete; workspace preserved at $WORKSPACE" >&2
    exit 1
fi

PHASE2B_OUTPUT="$RESULT_ROOT/phase2b_output.md"
IFS= read -r CONFIRMED_HEADER < "$PHASE2B_OUTPUT" || CONFIRMED_HEADER=
case "$CONFIRMED_HEADER" in
    "CONFIRMED_COUNT: "*) CONFIRMED_COUNT=${CONFIRMED_HEADER#CONFIRMED_COUNT: } ;;
    *)
        echo "error: phase2b_output.md must start with CONFIRMED_COUNT: N" >&2
        exit 1
        ;;
esac
case "$CONFIRMED_COUNT" in
    ''|*[!0-9]*) echo "error: phase2b_output.md has an invalid confirmed count" >&2; exit 1 ;;
esac

if [ "$CONFIRMED_COUNT" -gt 0 ]; then
    for REQUIRED_OUTPUT in phase3_output.md phase3d_output.md; do
        if [ ! -f "$RESULT_ROOT/$REQUIRED_OUTPUT" ] || \
            [ -L "$RESULT_ROOT/$REQUIRED_OUTPUT" ] || \
            [ ! -s "$RESULT_ROOT/$REQUIRED_OUTPUT" ]; then
            echo "error: missing scan output: $REQUIRED_OUTPUT" >&2
            MISSING_OUTPUT=1
        fi
    done
fi

README="$RESULT_ROOT/README.md"
IFS= read -r README_HEADER < "$README" || README_HEADER=
if [ "$README_HEADER" != "# VulnHunter Security Audit Report" ]; then
    echo "error: README.md has an invalid report header" >&2
    MISSING_OUTPUT=1
fi

MANIFEST="$RESULT_ROOT/findings.manifest"
MANIFEST_COUNT=
ACTUAL_FINDINGS=0
SEEN_FINDINGS=
while IFS= read -r MANIFEST_LINE || [ -n "$MANIFEST_LINE" ]; do
    if [ -z "$MANIFEST_COUNT" ]; then
        case "$MANIFEST_LINE" in
            "FINDING_COUNT: "*) MANIFEST_COUNT=${MANIFEST_LINE#FINDING_COUNT: } ;;
            *) echo "error: findings.manifest must start with FINDING_COUNT: N" >&2; MISSING_OUTPUT=1 ;;
        esac
        case "$MANIFEST_COUNT" in
            ''|*[!0-9]*) echo "error: findings.manifest has an invalid finding count" >&2; MISSING_OUTPUT=1 ;;
        esac
        continue
    fi
    [ -n "$MANIFEST_LINE" ] || continue
    FINDING_ID=${MANIFEST_LINE%%|*}
    MANIFEST_REST=${MANIFEST_LINE#*|}
    POC_PATH=${MANIFEST_REST%%|*}
    TEST_PATH=${MANIFEST_REST#*|}
    if [ "$MANIFEST_REST" = "$MANIFEST_LINE" ] || [ "$TEST_PATH" = "$MANIFEST_REST" ]; then
        echo "error: invalid findings.manifest entry: $MANIFEST_LINE" >&2
        MISSING_OUTPUT=1
        continue
    fi
    case "$TEST_PATH" in
        *'|'*) echo "error: invalid findings.manifest entry: $MANIFEST_LINE" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    case "$FINDING_ID" in
        VULN-[0-9][0-9][0-9]|VULN-PLATFORM-AUTHN|VULN-PLATFORM-AUTHZ) ;;
        *) echo "error: invalid finding id: $FINDING_ID" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    case "$POC_PATH" in
        poc/"$FINDING_ID"_*.md) ;;
        *) echo "error: invalid PoC path for $FINDING_ID" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    case "${POC_PATH#poc/}" in
        ''|*[!A-Za-z0-9._-]*) echo "error: invalid PoC path for $FINDING_ID" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    case "$TEST_PATH" in
        exploit_tests/*) ;;
        *) echo "error: invalid exploit-test path for $FINDING_ID" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    case "${TEST_PATH#exploit_tests/}" in
        ''|*[!A-Za-z0-9._-]*) echo "error: invalid exploit-test path for $FINDING_ID" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    case "
$SEEN_FINDINGS" in
        *"
$FINDING_ID
"*) echo "error: duplicate finding id: $FINDING_ID" >&2; MISSING_OUTPUT=1; continue ;;
    esac
    SEEN_FINDINGS="$SEEN_FINDINGS$FINDING_ID
"
    for ARTIFACT in "$POC_PATH" "$TEST_PATH"; do
        if [ ! -f "$RESULT_ROOT/$ARTIFACT" ] || [ -L "$RESULT_ROOT/$ARTIFACT" ] || [ ! -s "$RESULT_ROOT/$ARTIFACT" ]; then
            echo "error: missing finding artifact: $ARTIFACT" >&2
            MISSING_OUTPUT=1
        fi
        if ! grep -F "($ARTIFACT)" "$README" >/dev/null 2>&1; then
            echo "error: README.md does not link finding artifact: $ARTIFACT" >&2
            MISSING_OUTPUT=1
        fi
    done
    if ! grep -F "$FINDING_ID" "$README" >/dev/null 2>&1; then
        echo "error: README.md does not list finding: $FINDING_ID" >&2
        MISSING_OUTPUT=1
    fi
    ACTUAL_FINDINGS=$((ACTUAL_FINDINGS + 1))
done < "$MANIFEST"

if [ -z "$MANIFEST_COUNT" ]; then
    echo "error: findings.manifest is empty" >&2
    MISSING_OUTPUT=1
elif [ "$ACTUAL_FINDINGS" -ne "$MANIFEST_COUNT" ]; then
    echo "error: expected $MANIFEST_COUNT manifest entries, found $ACTUAL_FINDINGS" >&2
    MISSING_OUTPUT=1
fi
if [ "$CONFIRMED_COUNT" -eq 0 ] && [ "${MANIFEST_COUNT:-1}" -ne 0 ]; then
    echo "error: a clean Phase 2b result cannot report findings" >&2
    MISSING_OUTPUT=1
fi
grep -Eo 'VULN-([0-9]{3}|PLATFORM-(AUTHN|AUTHZ))' "$README" \
    | sort -u > "$WORK_ROOT/readme-findings"
grep -E 'VULN-[0-9]{3}.*SUBSUMED-BY: VULN-PLATFORM-(AUTHN|AUTHZ)' "$README" \
    | grep -Eo 'VULN-[0-9]{3}' \
    | sort -u > "$WORK_ROOT/subsumed-findings"
while IFS= read -r README_FINDING; do
    [ -n "$README_FINDING" ] || continue
    case "
$SEEN_FINDINGS" in
        *"
$README_FINDING
"*) ;;
        *)
            if ! grep -Fx "$README_FINDING" "$WORK_ROOT/subsumed-findings" >/dev/null 2>&1; then
                echo "error: README finding missing from manifest: $README_FINDING" >&2
                MISSING_OUTPUT=1
            fi
            ;;
    esac
done < "$WORK_ROOT/readme-findings"
if [ "$MISSING_OUTPUT" -ne 0 ]; then
    echo "error: scan incomplete; workspace preserved at $WORKSPACE" >&2
    exit 1
fi

echo "Report: $README"
