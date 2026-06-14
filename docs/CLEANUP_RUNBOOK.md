# Cleanup Runbook

This runbook describes safe deletion after a Phase 1/2-only deployment.

## Safety Rules

- Start with dry run.
- Confirm AWS account and region before deletion.
- Keep S3 deletion as an explicit boundary because it is permanent.
- Do not use broad name matching for ECR or Secrets Manager cleanup.
- Record actual deletion results in `docs/RESOURCE_LEDGER.md`.

## Dry Run

```bash
cd /Users/xiaoxiongweng/Documents/tezign/atypica/atypica-hermes/sample-host-hermesagent-on-amazon-bedrock-agentcore
./scripts/teardown.sh --dry-run
```

Check the printed account, region, stack list, and retained resources before
continuing.

## Interactive Cleanup

```bash
./scripts/teardown.sh
```

The script destroys resources in reverse dependency order:

1. Phase 4 gateway, if it exists.
2. Phase 3 stacks, if they exist.
3. Phase 2 AgentCore runtime stack.
4. Phase 1 CDK stacks.
5. Isolated CDK bootstrap stack `CDKToolkitHermes`.
6. Retained resources such as S3, DynamoDB, KMS, Cognito, Secrets Manager, and
   CloudWatch logs.

For a Phase 1/2-only run, Phase 3 and Phase 4 should be skipped or already
absent.

The isolated CDK bootstrap stack `CDKToolkitHermes` is project-scoped and is
destroyed after the Phase 1 stacks. The script empties the isolated bootstrap
asset bucket and container asset ECR repository before deleting the bootstrap
stack.

For the 2026-06-14 Phase 2 run, the AgentCore stack owns the runtime
`hermes_hermes-5ddzSXBy8T`, ECR repository `hermes/hermes`, CodeBuild project
`AgentCore-hermes-default-container-builder`, and runtime execution role
`AgentCore-hermes-default-ApplicationAgentHermesRunt-if52C9YxJTzb`.

## Manual Verification

After cleanup:

```bash
aws cloudformation describe-stacks --stack-name hermes-agentcore-vpc
aws cloudformation describe-stacks --stack-name hermes-agentcore-agentcore
aws cloudformation describe-stacks --stack-name AgentCore-hermes-default
aws cloudformation describe-stacks --stack-name CDKToolkitHermes
aws ecr describe-repositories --repository-names hermes/hermes
aws ecr describe-repositories --repository-names cdk-hmsagt001-container-assets-<account>-<region>
aws s3api head-bucket --bucket hermes-agentcore-user-files-<account>-<region>
aws s3api head-bucket --bucket cdk-hmsagt001-assets-<account>-<region>
```

Expected: stack and bucket lookups fail because resources are gone. KMS key
deletion is scheduled, not immediate; record the scheduled deletion date in the
resource ledger.
