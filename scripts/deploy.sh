#!/usr/bin/env bash
# --------------------------------------------------------------------------
# Three-phase deploy script for Hermes-Agent on Amazon Bedrock AgentCore.
#
# Usage:
#   ./scripts/deploy.sh           # Run all phases
#   ./scripts/deploy.sh phase1    # CDK foundation stacks only
#   ./scripts/deploy.sh phase2    # AgentCore Toolkit (build + deploy runtime)
#   ./scripts/deploy.sh phase3    # CDK dependent stacks only
#   ./scripts/deploy.sh cdk-only  # Phase 1 + Phase 3 (skip runtime build)
# --------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PHASE="${1:-all}"
PROJECT_NAME="hermes-agentcore"
RUNTIME_NAME="hermes_agent"
HERMES_AGENT_VERSION="${HERMES_AGENT_VERSION:-0.15.2}"
AGENTCORE_CONFIG_BACKUP=""
CDK_BOOTSTRAP_QUALIFIER="$(python - <<'PY'
import json
from pathlib import Path

config = json.loads(Path("cdk.json").read_text())
print(config.get("context", {}).get("bootstrap_qualifier", "hmsagt001"))
PY
)"
CDK_BOOTSTRAP_STACK_NAME="$(python - <<'PY'
import json
from pathlib import Path

config = json.loads(Path("cdk.json").read_text())
print(config.get("context", {}).get("bootstrap_stack_name", "CDKToolkitHermes"))
PY
)"

load_env() {
    local env_file=""
    if [ -f "$PROJECT_DIR/.env" ]; then
        env_file="$PROJECT_DIR/.env"
    elif [ -f "$PROJECT_DIR/../.env" ]; then
        env_file="$PROJECT_DIR/../.env"
    fi

    if [ -n "$env_file" ]; then
        info "Loading environment from $env_file"
        set -a
        # shellcheck disable=SC1090
        source "$env_file"
        set +a
    fi
}

restore_agentcore_config() {
    if [ -n "$AGENTCORE_CONFIG_BACKUP" ] && [ -f "$AGENTCORE_CONFIG_BACKUP" ]; then
        mv "$AGENTCORE_CONFIG_BACKUP" "$PROJECT_DIR/agentcore/agentcore.json"
        AGENTCORE_CONFIG_BACKUP=""
    fi
    rm -rf "$PROJECT_DIR/agentcore/cdk/cdk.out"
}

prepare_agentcore_env() {
    if [ -z "${LITELLM_BASE_URL:-}" ]; then
        error "LITELLM_BASE_URL is required for Phase 2. Set it in .env."
        exit 1
    fi
    if [ -z "${LITELLM_API_KEY:-}" ]; then
        error "LITELLM_API_KEY is required for Phase 2. Set it in .env."
        exit 1
    fi

    export HERMES_PROVIDER="${HERMES_PROVIDER:-openai}"
    export HERMES_BASE_URL="${HERMES_BASE_URL:-$LITELLM_BASE_URL}"
    export OPENAI_API_KEY="${OPENAI_API_KEY:-$LITELLM_API_KEY}"
    export LITELLM_MODEL="${LITELLM_MODEL:-${HERMES_MODEL:-${MODEL_NAME:-gpt-4o-mini}}}"
    export HERMES_MODEL="${HERMES_MODEL:-$LITELLM_MODEL}"
    export WARMUP_MODEL="${WARMUP_MODEL:-$LITELLM_MODEL}"

    AGENTCORE_CONFIG_BACKUP="$(mktemp)"
    cp "$PROJECT_DIR/agentcore/agentcore.json" "$AGENTCORE_CONFIG_BACKUP"
    trap restore_agentcore_config EXIT

    python - <<'PY'
import json
import os
from pathlib import Path

path = Path("agentcore/agentcore.json")
config = json.loads(path.read_text())
config["runtimes"][0]["envVars"] = [
    {"name": "HERMES_PROVIDER", "value": os.environ["HERMES_PROVIDER"]},
    {"name": "LITELLM_BASE_URL", "value": os.environ["LITELLM_BASE_URL"]},
    {"name": "LITELLM_API_KEY", "value": os.environ["LITELLM_API_KEY"]},
    {"name": "HERMES_BASE_URL", "value": os.environ["HERMES_BASE_URL"]},
    {"name": "OPENAI_API_KEY", "value": os.environ["OPENAI_API_KEY"]},
    {"name": "LITELLM_MODEL", "value": os.environ["LITELLM_MODEL"]},
    {"name": "HERMES_MODEL", "value": os.environ["HERMES_MODEL"]},
    {"name": "WARMUP_MODEL", "value": os.environ["WARMUP_MODEL"]},
]
path.write_text(json.dumps(config, indent=2) + "\n")
PY
    info "Injected LiteLLM runtime envVars into agentcore/agentcore.json for this deployment."
}

ensure_hermes_agent_source() {
    if [ -d "$PROJECT_DIR/app/hermes/hermes-agent" ]; then
        return
    fi

    if [ -d "$HOME/hermes-agent" ]; then
        return
    fi

    info "hermes-agent not found at $HOME/hermes-agent — cloning …"
    if git clone https://github.com/NousResearch/hermes-agent.git "$HOME/hermes-agent"; then
        return
    fi

    warn "GitHub clone failed. Falling back to PyPI source distribution hermes-agent==$HERMES_AGENT_VERSION."
    TMP_SRC="$(mktemp -d)"
    python -m pip download \
        --no-deps \
        --no-binary=:all: \
        --dest "$TMP_SRC" \
        "hermes-agent==$HERMES_AGENT_VERSION"

    HERMES_SDIST="$(find "$TMP_SRC" -maxdepth 1 \( -name 'hermes_agent-*.tar.gz' -o -name 'hermes-agent-*.tar.gz' \) | head -n 1)"
    if [ -z "$HERMES_SDIST" ]; then
        error "Could not find downloaded hermes-agent source archive in $TMP_SRC"
        exit 1
    fi

    HERMES_SDIST="$HERMES_SDIST" HOME="$HOME" python - <<'PY'
import os
import shutil
import tarfile
from pathlib import Path

archive = Path(os.environ["HERMES_SDIST"])
dest = Path(os.environ["HOME"]) / "hermes-agent"
tmp = archive.parent / "extract"
tmp.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive) as tar:
    tar.extractall(tmp)
roots = [path for path in tmp.iterdir() if path.is_dir()]
if not roots:
    raise SystemExit("source archive did not contain a directory")
if dest.exists():
    shutil.rmtree(dest)
shutil.move(str(roots[0]), dest)
PY
    rm -rf "$TMP_SRC"
    info "Created $HOME/hermes-agent from PyPI source distribution."
}

# Activate virtual environment if present.
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Use local npx cdk if global cdk is not available.
if command -v cdk &>/dev/null; then
    CDK="cdk"
else
    CDK="npx cdk"
fi

# Colours.
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --------------------------------------------------------------------------
# Phase 1: CDK foundation stacks
# --------------------------------------------------------------------------
phase1() {
    info "=== Phase 1: CDK Foundation Stacks ==="
    load_env

    # Ensure this project uses its own CDK bootstrap resources. The default
    # bootstrap bucket in this account may be shared by other experiments.
    if ! aws cloudformation describe-stacks --stack-name "$CDK_BOOTSTRAP_STACK_NAME" &>/dev/null; then
        info "Bootstrapping CDK stack $CDK_BOOTSTRAP_STACK_NAME (qualifier=$CDK_BOOTSTRAP_QUALIFIER) …"
        $CDK bootstrap \
            --qualifier "$CDK_BOOTSTRAP_QUALIFIER" \
            --toolkit-stack-name "$CDK_BOOTSTRAP_STACK_NAME" \
            --bootstrap-kms-key-id AWS_MANAGED_KEY
    fi

    $CDK deploy \
        "${PROJECT_NAME}-vpc" \
        "${PROJECT_NAME}-security" \
        "${PROJECT_NAME}-agentcore" \
        "${PROJECT_NAME}-observability" \
        --require-approval never

    info "Phase 1 complete."
}

# --------------------------------------------------------------------------
# Phase 2: AgentCore Starter Toolkit
# --------------------------------------------------------------------------
phase2() {
    info "=== Phase 2: AgentCore Runtime (build + deploy) ==="
    load_env
    prepare_agentcore_env

    # Check toolkit is installed.
    if ! command -v agentcore &>/dev/null; then
        info "Installing @aws/agentcore CLI …"
        npm install -g @aws/agentcore
    fi

    # Ensure aws-targets.json exists (agentcore CDK requires it).
    if [ ! -f "$PROJECT_DIR/agentcore/aws-targets.json" ]; then
        info "Generating agentcore/aws-targets.json from current AWS credentials …"
        _ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        _REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")
        cat > "$PROJECT_DIR/agentcore/aws-targets.json" <<TARGETS
[
  {
    "name": "default",
    "description": "Default deployment target",
    "account": "$_ACCOUNT",
    "region": "$_REGION"
  }
]
TARGETS
        info "Created aws-targets.json (account=$_ACCOUNT, region=$_REGION)"
    fi

    # Copy hermes-agent source into the app/hermes/ Docker build context.
    if [ ! -d "$PROJECT_DIR/app/hermes/hermes-agent" ]; then
        ensure_hermes_agent_source
        info "Copying hermes-agent source into app/hermes/ for Docker build …"
        rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
            "$HOME/hermes-agent/" "$PROJECT_DIR/app/hermes/hermes-agent/"
    fi

    # Copy bridge/ into app/hermes/ so Dockerfile can access it.
    info "Syncing bridge/ into app/hermes/bridge/ …"
    rsync -a --delete --exclude='__pycache__' --exclude='Dockerfile' \
        "$PROJECT_DIR/bridge/" "$PROJECT_DIR/app/hermes/bridge/"

    # Build and deploy via agentcore CLI.
    info "Deploying to AgentCore …"
    agentcore deploy --yes --verbose

    # Extract runtime IDs and write back to cdk.json.
    info "Extracting runtime IDs …"
    # Strip ANSI escape sequences (agentcore CLI may emit cursor control codes).
    STATUS_JSON=$(agentcore status --json 2>/dev/null | sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' || echo "{}")
    RUNTIME_ARN=$(STATUS_JSON="$STATUS_JSON" python - <<'PY'
import json
import os

data = json.loads(os.environ.get("STATUS_JSON") or "{}")
candidates = [
    data.get("resources", [{}])[0].get("identifier") if data.get("resources") else "",
    data.get("runtimes", [{}])[0].get("agentRuntimeArn") if data.get("runtimes") else "",
    data.get("runtimes", [{}])[0].get("runtimeArn") if data.get("runtimes") else "",
    data.get("agentRuntimeArn"),
    data.get("runtimeArn"),
]
print(next((value for value in candidates if value), ""))
PY
)
    # Extract qualifier from the runtime ARN tail (e.g. "hermes_hermes-55EPNeG2QF")
    QUALIFIER=$(STATUS_JSON="$STATUS_JSON" python - <<'PY' | sed 's|.*/||'
import json
import os

data = json.loads(os.environ.get("STATUS_JSON") or "{}")
candidates = [
    data.get("resources", [{}])[0].get("identifier") if data.get("resources") else "",
    data.get("runtimes", [{}])[0].get("agentRuntimeId") if data.get("runtimes") else "",
    data.get("runtimes", [{}])[0].get("qualifier") if data.get("runtimes") else "",
    data.get("qualifier"),
    data.get("endpointId"),
]
print(next((value for value in candidates if value), ""))
PY
)

    if [ -n "$RUNTIME_ARN" ]; then
        info "Runtime ARN:  $RUNTIME_ARN"
        info "Qualifier:    $QUALIFIER"

        # Update cdk.json with runtime IDs.
        RUNTIME_ARN="$RUNTIME_ARN" QUALIFIER="$QUALIFIER" python - <<'PY'
import json
import os
from pathlib import Path

path = Path("cdk.json")
config = json.loads(path.read_text())
config.setdefault("context", {})
config["context"]["agentcore_runtime_arn"] = os.environ["RUNTIME_ARN"]
config["context"]["agentcore_qualifier"] = os.environ["QUALIFIER"]
path.write_text(json.dumps(config, indent=2) + "\n")
PY

        info "cdk.json updated with runtime IDs."
    else
        warn "Could not extract runtime IDs automatically."
        warn "Run 'agentcore status --json' and set agentcore_runtime_arn / agentcore_qualifier in cdk.json manually."
    fi

    info "Phase 2 complete."
    restore_agentcore_config
    trap - EXIT
}

# --------------------------------------------------------------------------
# Phase 3: CDK dependent stacks
# --------------------------------------------------------------------------
phase3() {
    info "=== Phase 3: CDK Dependent Stacks ==="
    load_env

    # Verify runtime IDs are set.
    RUNTIME_ARN=$(python - <<'PY'
import json
from pathlib import Path

config = json.loads(Path("cdk.json").read_text())
print(config.get("context", {}).get("agentcore_runtime_arn", ""))
PY
)
    if [ -z "$RUNTIME_ARN" ]; then
        warn "agentcore_runtime_arn not set in cdk.json — Lambda will not be able to invoke AgentCore."
        warn "Run Phase 2 first, or set the values manually."
    fi

    $CDK deploy \
        "${PROJECT_NAME}-router" \
        "${PROJECT_NAME}-cron" \
        "${PROJECT_NAME}-token-monitoring" \
        --require-approval never

    # Print API URL.
    API_URL=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-router" \
        --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
        --output text 2>/dev/null || echo "")

    if [ -n "$API_URL" ]; then
        info "API Gateway URL: $API_URL"
        info "Webhook endpoints:"
        info "  Telegram: ${API_URL}webhook/telegram"
        info "  Slack:    ${API_URL}webhook/slack"
        info "  Discord:  ${API_URL}webhook/discord"
    fi

    info "Phase 3 complete."
}

# --------------------------------------------------------------------------
# Phase 4: ECS Gateway for WeChat + Feishu (optional)
# --------------------------------------------------------------------------
phase4() {
    info "=== Phase 4: ECS Gateway (WeChat + Feishu) ==="
    load_env

    # Verify runtime ARN is set.
    RUNTIME_ARN=$(python - <<'PY'
import json
from pathlib import Path

config = json.loads(Path("cdk.json").read_text())
print(config.get("context", {}).get("agentcore_runtime_arn", ""))
PY
)
    if [ -z "$RUNTIME_ARN" ]; then
        error "agentcore_runtime_arn not set in cdk.json. Run Phase 2 first."
        exit 1
    fi

    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    AWS_REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")
    ECR_REPO="${PROJECT_NAME}-gateway"
    ECR_URI="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

    # ── Step 1: Ensure ECR repo exists (create before CDK to push image first) ──
    if ! aws ecr describe-repositories --repository-names "$ECR_REPO" &>/dev/null; then
        info "Creating ECR repository: $ECR_REPO"
        aws ecr create-repository \
            --repository-name "$ECR_REPO" \
            --image-scanning-configuration scanOnPush=true \
            --no-cli-pager >/dev/null
    fi

    # ── Step 2: Copy hermes-agent source into build context ──
    if [ ! -d "$PROJECT_DIR/gateway/hermes-agent" ]; then
        if [ ! -d "$HOME/hermes-agent" ]; then
            info "hermes-agent not found at $HOME/hermes-agent — cloning …"
            git clone https://github.com/NousResearch/hermes-agent.git "$HOME/hermes-agent"
        fi
        info "Copying hermes-agent source into gateway/ for Docker build …"
        rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
            "$HOME/hermes-agent/" "$PROJECT_DIR/gateway/hermes-agent/"
    fi

    # ── Step 3: Build and push container image ──
    info "ECR login …"
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

    info "Building gateway container image …"
    docker build \
        --platform linux/amd64 \
        -t "${ECR_URI}:latest" \
        -f "$PROJECT_DIR/gateway/Dockerfile" \
        "$PROJECT_DIR/gateway/"

    info "Pushing to ECR …"
    docker push "${ECR_URI}:latest"

    # ── Step 4: CDK deploy (image is already in ECR, Service can start) ──
    info "Deploying CDK gateway stack …"
    $CDK deploy "${PROJECT_NAME}-gateway" --require-approval never

    # ── Step 5: Force new deployment to pick up the latest image ──
    info "Triggering ECS deployment …"
    aws ecs update-service \
        --cluster "${PROJECT_NAME}-gateway" \
        --service "${PROJECT_NAME}-gateway" \
        --force-new-deployment \
        --no-cli-pager >/dev/null

    info "Phase 4 complete."
    info "ECS Gateway cluster: ${PROJECT_NAME}-gateway"
    info "ECR image: ${ECR_URI}:latest"
    info ""
    info "To configure WeChat/Feishu, set secrets in Secrets Manager:"
    info "  aws secretsmanager put-secret-value --secret-id hermes/weixin/token --secret-string 'YOUR_TOKEN'"
    info "  aws secretsmanager put-secret-value --secret-id hermes/feishu/app-id --secret-string 'YOUR_APP_ID'"
    info "  aws secretsmanager put-secret-value --secret-id hermes/feishu/app-secret --secret-string 'YOUR_SECRET'"
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
case "$PHASE" in
    all)
        phase1
        phase2
        phase3
        ;;
    phase1)
        phase1
        ;;
    phase2)
        phase2
        ;;
    phase3)
        phase3
        ;;
    phase4)
        phase4
        ;;
    cdk-only)
        phase1
        phase3
        ;;
    *)
        error "Usage: $0 [all|phase1|phase2|phase3|phase4|cdk-only]"
        exit 1
        ;;
esac

info "=== Deploy complete ==="
