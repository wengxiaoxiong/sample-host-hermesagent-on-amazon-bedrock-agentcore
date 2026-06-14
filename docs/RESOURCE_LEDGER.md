# Resource Ledger

This ledger tracks resources expected from Phase 1 and Phase 2 only. Fill in
actual ARNs, names, and deletion results during execution.

## Phase 1

| Resource | Expected name | Owner | Delete path | Status |
| --- | --- | --- | --- | --- |
| CloudFormation stack | `hermes-agentcore-vpc` | CDK | `cdk destroy hermes-agentcore-vpc` after dependents | Created |
| CloudFormation stack | `hermes-agentcore-security` | CDK | `cdk destroy hermes-agentcore-security` after dependents | Created |
| CloudFormation stack | `hermes-agentcore-agentcore` | CDK | `cdk destroy hermes-agentcore-agentcore` after runtime deletion | Created |
| CloudFormation stack | `hermes-agentcore-observability` | CDK | `cdk destroy hermes-agentcore-observability` | Created |
| S3 bucket | `hermes-agentcore-user-files-873478945193-us-east-1` | CDK retained | Empty versions and delete bucket | Created |
| KMS alias/key | `alias/hermes-agentcore` | CDK retained | Schedule key deletion, minimum 7 days | Planned |

## Bootstrap Resources

| Resource | Actual name | Owner | Delete path | Status |
| --- | --- | --- | --- | --- |
| CloudFormation stack | `CDKToolkit` | CDK bootstrap | Usually shared; do not delete as Hermes cleanup unless confirmed unused | Created |
| S3 bucket | `cdk-hnb659fds-assets-873478945193-us-east-1` | CDK bootstrap | Usually shared; do not delete as Hermes cleanup unless confirmed unused | Exists |
| KMS key | `82b4cfcd-1b01-4248-abb6-04e727cd8e40` | CDK bootstrap bucket encryption | Pending deletion; cancel deletion or replace bootstrap encryption before Phase 1 can proceed | Blocking |
| CloudFormation stack | `CDKToolkitHermes` | Hermes isolated CDK bootstrap | `scripts/teardown.sh` after all project stacks are gone | Created |
| S3 bucket | `cdk-hmsagt001-assets-873478945193-us-east-1` | Hermes isolated CDK bootstrap | Emptied by `scripts/teardown.sh` before bootstrap stack deletion | Created |
| ECR repository | `cdk-hmsagt001-container-assets-873478945193-us-east-1` | Hermes isolated CDK bootstrap | Deleted with `CDKToolkitHermes` stack | Created |

## Phase 2

| Resource | Expected name | Owner | Delete path | Status |
| --- | --- | --- | --- | --- |
| CloudFormation stack | `AgentCore-hermes-default` | AgentCore CLI | `aws cloudformation delete-stack --stack-name AgentCore-hermes-default` | Created |
| AgentCore runtime | `hermes_hermes-5ddzSXBy8T` | AgentCore CLI | Deleted with AgentCore stack | Created |
| ECR repository | `hermes/hermes` | AgentCore CLI | Deleted with AgentCore stack; verify no repository remains | Created |
| CodeBuild project | `AgentCore-hermes-default-container-builder` | AgentCore CLI | Deleted with AgentCore stack | Created |
| Runtime execution role | `AgentCore-hermes-default-ApplicationAgentHermesRunt-if52C9YxJTzb` | AgentCore CLI | Deleted with AgentCore stack | Created |
| Container build Lambda | `AgentCore-hermes-default-ApplicationAgentHermesCon-ICVkSOZ7Cut3` | AgentCore CLI | Deleted with AgentCore stack | Created |
| ECR KMS key | `abca3b48-311c-4324-a9e2-6a20463fcc40` | AgentCore CLI | Deleted or scheduled with AgentCore stack deletion | Created |

## Explicitly Not Expected

These resources should not be created for the Phase 1/2 LiteLLM run:

- `hermes-agentcore-guardrails`
- Bedrock Guardrail resources
- Bedrock Runtime VPC endpoint
- Phase 3 stacks: `hermes-agentcore-router`, `hermes-agentcore-cron`,
  `hermes-agentcore-token-monitoring`
- Phase 4 stack: `hermes-agentcore-gateway`

## Actual Resources

### 2026-06-14 Phase 2

| Resource | Actual identifier | Status |
| --- | --- | --- |
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:873478945193:runtime/hermes_hermes-5ddzSXBy8T` | Ready |
| Runtime ID | `hermes_hermes-5ddzSXBy8T` | Ready |
| Runtime image | `873478945193.dkr.ecr.us-east-1.amazonaws.com/hermes/hermes:15d90911302772d7084dcee34e897bee3caed40952a1f8d5a03527516050d7d2` | Deployed |
| Runtime invoke check | `agentcore invoke --runtime hermes --target default --json --prompt ...` | Passed |
