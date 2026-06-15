# Operations Log

Use this file as the collaboration log for real deployment and cleanup actions.
Do not paste secret values.

## 2026-06-14 Preparation

- Scope confirmed: Phase 1 and Phase 2 only.
- Model inference target: OpenAI-compatible API via LiteLLM variables in
  parent `.env`.
- Bedrock model inference and Bedrock Guardrails are out of scope.
- Phase 3 and Phase 4 are explicitly deferred.
- Code changes prepared locally; no AWS deployment commands were run.
- Created local `.venv` for validation dependencies; `.venv` is ignored by git.
- Generated local `agentcore/aws-targets.json` from `.env` AWS credentials for
  `agentcore validate`; the file is ignored by git.
- Validation performed:
  - `bash -n scripts/deploy.sh scripts/teardown.sh` passed.
  - `agentcore validate` returned `Valid`.
  - `PATH="$PWD/.venv/bin:$PATH" npx cdk synth` succeeded; synthesized stack
    list excludes `hermes-agentcore-guardrails`.
  - `.venv/bin/python -m pytest -q` passed with 25 tests.
- CDK synth emitted existing warnings about deprecated CDK APIs, Node 20
  deprecation, cross-stack reference defaults, and ECS circuit breaker guidance.
  These warnings did not block synth.

## Execution Template

```text
Date:
Operator:
AWS account:
AWS region:
Git commit or working tree note:

Command:
Result:
Evidence:
Follow-up:
```

## Deployment Entries

Add new entries below when commands are actually run.

## 2026-06-14 Phase 1 Attempt

Date: 2026-06-14 20:52-20:55 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Command:

```bash
./scripts/deploy.sh phase1
```

Result:

- CDK bootstrap completed for `aws://873478945193/us-east-1`.
- Phase 1 stack deployment did not start successfully because CDK could not
  publish synthesized templates to the bootstrap asset bucket.

Evidence:

- CDK bootstrap stack: `CDKToolkit` is `CREATE_COMPLETE`.
- Bootstrap asset bucket: `cdk-hnb659fds-assets-873478945193-us-east-1`.
- Bucket default encryption points to KMS key
  `arn:aws:kms:us-east-1:873478945193:key/82b4cfcd-1b01-4248-abb6-04e727cd8e40`.
- KMS key state is `PendingDeletion`; deletion date is
  `2026-07-12T15:22:36.174000+08:00`.
- `aws cloudformation list-stacks` showed no completed `hermes-agentcore-*`
  stacks and no `AgentCore-hermes-default` stack after the failed attempt.

Follow-up:

- Do not run Phase 2 until Phase 1 succeeds.
- Remediation chosen: do not cancel deletion for the existing default bootstrap
  KMS key. Instead, configure this project to use an isolated CDK bootstrap
  stack named `CDKToolkitHermes` with qualifier `hmsagt001` and AWS-managed
  bootstrap bucket encryption.

## 2026-06-14 Phase 1 Completion

Date: 2026-06-14 21:00-21:15 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Commands:

```bash
./scripts/deploy.sh phase1
cdk deploy hermes-agentcore-agentcore --exclusively --require-approval never
```

Result:

- Created isolated CDK bootstrap stack `CDKToolkitHermes`.
- Deployed Phase 1 stacks.
- The first `cdk deploy` process stalled after publishing the
  `hermes-agentcore-agentcore` template; it was interrupted after confirming no
  `hermes-agentcore-agentcore` stack had started.
- Re-ran the remaining stack with `--exclusively`, which completed.

Evidence:

- `CDKToolkitHermes`: `CREATE_COMPLETE`
- `hermes-agentcore-vpc`: `CREATE_COMPLETE`
- `hermes-agentcore-security`: `CREATE_COMPLETE`
- `hermes-agentcore-observability`: `CREATE_COMPLETE`
- `hermes-agentcore-agentcore`: `CREATE_COMPLETE`
- Outputs:
  - VPC ID: `vpc-02f2a66cd38d0e3bc`
  - AgentCore security group: `sg-0bf755b6b8684a2ef`
  - User files bucket: `hermes-agentcore-user-files-873478945193-us-east-1`
  - Execution role: `arn:aws:iam::873478945193:role/hermes-agentcore-execution-role`

Follow-up:

- Proceed to Phase 2 runtime deployment.

## 2026-06-14 Phase 2 First Attempt

Date: 2026-06-14 21:16-21:20 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Command:

```bash
./scripts/deploy.sh phase2
```

Result:

- Phase 2 did not reach `agentcore deploy`.
- Runtime envVars were temporarily injected and then restored by the script
  trap; `agentcore/agentcore.json` has no local diff.
- Failure happened while preparing the Docker build context:
  `git clone https://github.com/NousResearch/hermes-agent.git` could not
  connect to `github.com:443`.

Follow-up:

- Added a fallback path to `scripts/deploy.sh`: if GitHub clone fails, download
  `hermes-agent` source distribution from PyPI (`HERMES_AGENT_VERSION`, default
  `0.15.2`) and use it as `~/hermes-agent`.

## 2026-06-14 Phase 2 Remediation

Date: 2026-06-14 21:20-21:35 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Commands:

```bash
npm install
npm run build
agentcore validate
CDK_OUTDIR=cdk.out node dist/bin/cdk.js
```

Result:

- Installed AgentCore CDK subproject dependencies in `agentcore/cdk`.
- Updated `agentcore/cdk/package.json` so `aws-cdk-lib` satisfies
  `@aws/agentcore-cdk` peer dependency requirements.
- Patched the AgentCore CDK subproject to synthesize with the isolated
  `hmsagt001` bootstrap qualifier instead of the account default
  `hnb659fds`.
- Added a CDK aspect to remove default Bedrock model invocation permissions
  from the AgentCore runtime role policy.
- Updated Phase 2 cleanup so temporary `agentcore/cdk/cdk.out` output is
  deleted when `agentcore/agentcore.json` is restored; this prevents temporary
  model API secrets from remaining in generated CDK artifacts.

Evidence:

- `npm run build` passed in `agentcore/cdk`.
- `agentcore validate` returned `Valid`.
- Fresh AgentCore CDK assembly references
  `cdk-hmsagt001-assets-873478945193-us-east-1` and
  `/cdk-bootstrap/hmsagt001/version`.
- Fresh deployable templates contain no `bedrock:CountTokens`,
  `bedrock:InvokeModel`, or `bedrock:InvokeModelWithResponseStream` actions.
- `agentcore/agentcore.json` has no local diff after temporary env injection
  rollback checks.

Follow-up:

- Re-run `./scripts/deploy.sh phase2`.

## 2026-06-14 Phase 2 First Invoke and Fix

Date: 2026-06-14 21:36-21:40 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Commands:

```bash
agentcore status --json
agentcore invoke --runtime hermes --target default --json --prompt '你好，请用一句话说明你是谁。'
agentcore logs --runtime hermes --since 20m --query 'Provider'
.venv/bin/python -m pytest -q
```

Result:

- Phase 2 stack deployment completed and runtime status was `READY`.
- First runtime invoke reached the container but returned an application error:
  Hermes reported provider `openai` had no API key.
- Deployed CloudFormation template was checked without printing secret values;
  runtime `EnvironmentVariables` included the expected keys, including
  `OPENAI_API_KEY` and `LITELLM_API_KEY`.
- Root cause: `app/hermes/main.py` passed `base_url` but not `api_key` to
  `AIAgent`, so Hermes used its provider resolver path instead of explicit
  OpenAI-compatible credentials.
- Fix: pass `api_key=api_key` when constructing `AIAgent`.
- Added root `pytest.ini` so copied third-party `app/hermes/hermes-agent` source
  and `agentcore/cdk/node_modules` are not collected by project pytest.

Evidence:

- `agentcore status --json` reported runtime `hermes` deployment state
  `deployed` and detail `READY`.
- `AgentCore-hermes-default` CloudFormation stack is `CREATE_COMPLETE`.
- Actual runtime IAM role policy contains no `bedrock:CountTokens`,
  `bedrock:InvokeModel`, or `bedrock:InvokeModelWithResponseStream`.
- `.venv/bin/python -m pytest -q` passed with 25 tests after adding
  `pytest.ini`.

Follow-up:

- Re-run `./scripts/deploy.sh phase2` to publish the `api_key` fix, then invoke
  the runtime again.

## 2026-06-14 Phase 2 Verified

Date: 2026-06-14 21:41-21:46 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Commands:

```bash
./scripts/deploy.sh phase2
agentcore status --json
agentcore invoke --runtime hermes --target default --json --prompt '你好，请用一句话说明你是谁。'
agentcore logs --runtime hermes --since 3m --query 'Agent error'
aws iam get-role-policy --role-name AgentCore-hermes-default-ApplicationAgentHermesRunt-if52C9YxJTzb --policy-name ApplicationAgentHermesRuntimeExecutionRoleDefaultPolicy761A8EC5
```

Result:

- Re-deployed Phase 2 with explicit `api_key` passed into `AIAgent`.
- CloudFormation stack `AgentCore-hermes-default` updated successfully.
- Runtime remained `READY`.
- Invoke succeeded and returned a Chinese response from Hermes Agent.
- No new `Agent error` lines were found in the post-fix 3-minute log window.
- Temporary `agentcore/agentcore.json` env injection was restored and
  `agentcore/cdk/cdk.out` was cleaned after deploy.

Evidence:

- Runtime ARN:
  `arn:aws:bedrock-agentcore:us-east-1:873478945193:runtime/hermes_hermes-5ddzSXBy8T`
- Runtime ID: `hermes_hermes-5ddzSXBy8T`
- Invoke response:
  `你好，我是Hermes Agent，一个智能人工助手，旨在为用户提供知识、任务执行和信息分析等服务。`
- Runtime execution role policy contains AgentCore, logs, xray, ECR, and KMS
  permissions, and no Bedrock model invocation actions.
- `.venv/bin/python -m pytest -q` passed with 25 tests.

Follow-up:

- Phase 1 and Phase 2 are verified.
- Phase 3 and Phase 4 remain deferred.

## 2026-06-14 Cleanup Dry Run

Date: 2026-06-14 21:47 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git commit or working tree note: local uncommitted Phase 1/2 LiteLLM changes

Command:

```bash
./scripts/teardown.sh --dry-run
```

Result:

- No resources were modified.
- `scripts/teardown.sh` now loads `.env` from the project directory or parent
  directory before detecting AWS account and region.
- Dry run correctly reported Phase 3 and Phase 4 stacks as absent.
- Dry run reported the deployed Phase 2 stack, Phase 1 stacks, and isolated
  bootstrap stack as cleanup targets.

Evidence:

- Account: `873478945193`
- Region: `us-east-1`
- Cleanup targets shown:
  - `AgentCore-hermes-default`
  - `hermes-agentcore-observability`
  - `hermes-agentcore-agentcore`
  - `hermes-agentcore-security`
  - `hermes-agentcore-vpc`
  - `CDKToolkitHermes`
- ECR cleanup targets shown:
  - `hermes/hermes`
  - `cdk-hmsagt001-container-assets-873478945193-us-east-1`
- Additional retained resources shown:
  - `hermes-agentcore-user-files-873478945193-us-east-1`
  - `cdk-hmsagt001-assets-873478945193-us-east-1`
  - `hermes-agentcore-identity`
  - `alias/hermes-agentcore`
  - `hermes-agentcore-users`

Follow-up:

- Actual deletion remains a separate approval boundary. Run
  `./scripts/teardown.sh` for interactive cleanup or
  `./scripts/teardown.sh --force` only after explicit approval.

## 2026-06-15 Workspace Restore/Save Verified

Date: 2026-06-15 11:32-11:59 CST
Operator: Codex
AWS account: `873478945193`
AWS region: `us-east-1`
Git branch: `codex/phase12-litellm-agentcore`

Commands:

```bash
.venv/bin/python -m pytest -q
bash -n scripts/deploy.sh scripts/teardown.sh
git diff --check
npm run build
./scripts/deploy.sh phase2
aws bedrock-agentcore invoke-agent-runtime --region us-east-1 --agent-runtime-arn arn:aws:bedrock-agentcore:us-east-1:873478945193:runtime/hermes_hermes-5ddzSXBy8T ...
agentcore logs --runtime hermes --since 5m --query 'Workspace restore complete'
agentcore logs --runtime hermes --since 2m --query 'Workspace save complete'
aws iam get-role-policy --role-name AgentCore-hermes-default-ApplicationAgentHermesRunt-if52C9YxJTzb --policy-name ApplicationAgentHermesRuntimeExecutionRoleDefaultPolicy761A8EC5
```

Result:

- Added per-user workspace namespace derivation to `app/hermes/main.py`.
- Runtime now restores workspace from S3 before agent creation, starts periodic
  save, and saves again after each invocation and on SIGTERM.
- The runtime refuses to serve a different namespace in an already-initialized
  container to avoid cross-user workspace mixing.
- `scripts/deploy.sh` now injects `S3_BUCKET`, `WORKSPACE_PATH`, and
  `WORKSPACE_SYNC_INTERVAL` into AgentCore runtime env vars for Phase 2.
- AgentCore runtime role policy now includes S3 object permissions for
  `hermes-agentcore-user-files-873478945193-us-east-1` and KMS permissions for
  the bucket encryption key.
- `WorkspaceSync.save()` writes both `.workspace_namespace` and
  `workspace_namespace.txt` as explicit verification markers.

Evidence:

- Initial live save attempts reached the runtime but failed on S3 permissions:
  first `s3:ListBucket`, then `kms:GenerateDataKey` for the bucket KMS key.
- After IAM/KMS policy fixes, a new user invoke returned `data: "ok"`.
- S3 contained the expected per-user objects:
  - `.workspace_namespace`
  - `workspace_namespace.txt`
  - `SOUL.md`
  - `auth.lock`
  - `.skills_prompt_snapshot.json`
- Restore was verified by pre-seeding
  `workspace-restore-user-20260615035803/.hermes/restore_probe.txt`; runtime
  logs reported `Workspace restore complete (1 files)` and then
  `Workspace save complete (6 files ...)`.
- Latest short-window log query showed no new `Upload failed` lines.
- Local validation passed with 30 pytest tests, deploy/teardown shell syntax,
  whitespace check, and CDK TypeScript build.
- Feishu progress document created:
  `https://tezign.feishu.cn/docx/MqfLdKd82o3MdExUmntcEj9hnBg`

Follow-up:

- Current isolation is enforced at code level by stable user namespace and
  same-container namespace refusal. IAM still grants the runtime role access to
  the whole workspace bucket; stronger hard isolation would require scoped
  session credentials or per-user prefix policies.
