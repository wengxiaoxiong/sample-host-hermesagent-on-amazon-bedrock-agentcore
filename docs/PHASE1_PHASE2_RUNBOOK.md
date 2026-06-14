# Phase 1/2 Runbook: AgentCore Runtime with LiteLLM

This runbook is the shared working record for bringing Hermes up to Phase 2
only. The runtime is hosted on AgentCore, but model inference must use the
OpenAI-compatible API configured in the repository parent `.env`.

## Scope

- Run Phase 1 foundation resources.
- Run Phase 2 AgentCore runtime deployment.
- Validate runtime invocation through the configured LiteLLM endpoint.
- Do not run Phase 3 or Phase 4 during this pass.
- Do not use Bedrock model inference or Bedrock Guardrails.

## Required `.env`

The deployment script loads `.env` from either the project directory or the
parent repository directory. The current expected source is:

```text
/Users/xiaoxiongweng/Documents/tezign/atypica/atypica-hermes/.env
```

Required keys:

```bash
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
LITELLM_BASE_URL=
LITELLM_API_KEY=
```

Required local tools:

```bash
agentcore
aws
docker
npx
```

Optional keys:

```bash
LITELLM_MODEL=gpt-4o-mini
HERMES_MODEL=gpt-4o-mini
WARMUP_MODEL=gpt-4o-mini
HERMES_PROVIDER=openai
HERMES_AGENT_VERSION=0.15.2
```

If no model is set, `scripts/deploy.sh phase2` injects `gpt-4o-mini` as the
default model name. Change this in `.env` if the LiteLLM endpoint requires a
different model id.

## Current Design Decisions

- Runtime networking stays `PUBLIC` in `agentcore/agentcore.json`, so the
  runtime can call the OpenAI-compatible endpoint directly.
- This project uses an isolated CDK bootstrap stack, `CDKToolkitHermes`, with
  qualifier `hmsagt001`. This avoids the account's default `CDKToolkit` asset
  bucket, which currently points at a KMS key pending deletion.
- Phase 1 no longer creates the Bedrock Guardrails stack.
- Phase 1 no longer creates a Bedrock Runtime VPC endpoint.
- The AgentCore execution role no longer includes `bedrock:InvokeModel`,
  `bedrock:InvokeModelWithResponseStream`, or `bedrock:ApplyGuardrail`.
- Phase 2 removes the Anthropic to AnthropicBedrock monkey-patch.
- The warmup agent uses `litellm.completion` against `LITELLM_BASE_URL`.
- `scripts/deploy.sh phase2` temporarily injects LiteLLM runtime `envVars`
  into `agentcore/agentcore.json`, runs `agentcore deploy`, then restores the
  file so secrets are not left in the worktree.
- If `~/hermes-agent` is absent and GitHub is not reachable, Phase 2 downloads
  the `hermes-agent` source distribution from PyPI and uses that as the Docker
  build source.

## Preflight

From the sample project directory:

```bash
cd /Users/xiaoxiongweng/Documents/tezign/atypica/atypica-hermes/sample-host-hermesagent-on-amazon-bedrock-agentcore
git status --short
agentcore --version
aws sts get-caller-identity
```

Expected:

- `git status --short` only shows intentional local changes.
- `agentcore --version` works.
- `aws sts get-caller-identity` returns the account from `.env`.

## Deploy Phase 1

```bash
./scripts/deploy.sh phase1
```

Expected CloudFormation stacks:

- `CDKToolkitHermes` if the isolated bootstrap stack does not exist yet
- `hermes-agentcore-vpc`
- `hermes-agentcore-security`
- `hermes-agentcore-agentcore`
- `hermes-agentcore-observability`

There should be no `hermes-agentcore-guardrails` stack for this run.

## Deploy Phase 2

```bash
./scripts/deploy.sh phase2
```

The script should print that LiteLLM runtime envVars were injected for this
deployment. After completion, confirm no secret values remain in the tracked
config:

```bash
git diff -- agentcore/agentcore.json
```

Expected: no diff for `agentcore/agentcore.json`.

## Validate Phase 2

Check runtime status:

```bash
agentcore status --json
```

Invoke the deployed runtime:

```bash
agentcore invoke "你好，请用一句话说明你是谁" --stream --runtime hermes
```

Check logs:

```bash
agentcore logs --runtime hermes --since 30m
```

Validation criteria:

- The invoke command returns a model response.
- Logs show the configured LiteLLM/OpenAI-compatible base URL path.
- Logs do not show `AnthropicBedrock` usage.
- Logs do not show `bedrock-runtime` model invocation.
- `cdk.json` contains `agentcore_runtime_arn` and `agentcore_qualifier` after
  Phase 2.

## Stop Point

Stop after Phase 2. Do not run:

```bash
./scripts/deploy.sh phase3
./scripts/deploy.sh phase4
```

Phase 3 should wait until Phase 2 proves that the hosted runtime and the
LiteLLM endpoint are working together.
