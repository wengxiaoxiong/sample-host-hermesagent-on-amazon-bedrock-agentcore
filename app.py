#!/usr/bin/env python3
"""CDK app entry point for Hermes-Agent on Amazon Bedrock AgentCore.

Instantiates all stacks in dependency order.  Stacks are split into
**Phase 1** (foundation — no runtime IDs needed) and **Phase 3** (dependent
— need runtime IDs from the AgentCore Starter Toolkit).

Phase 2 (``agentcore deploy``) runs outside CDK.
"""

from __future__ import annotations

import aws_cdk as cdk

from stacks.vpc_stack import HermesVpcStack
from stacks.security_stack import HermesSecurityStack
from stacks.agentcore_stack import HermesAgentCoreStack
from stacks.observability_stack import HermesObservabilityStack
from stacks.router_stack import HermesRouterStack
from stacks.cron_stack import HermesCronStack
from stacks.token_monitoring_stack import HermesTokenMonitoringStack
from stacks.gateway_stack import HermesGatewayStack

app = cdk.App()

project = app.node.try_get_context("project_name") or "hermes-agentcore"
bootstrap_qualifier = app.node.try_get_context("bootstrap_qualifier") or "hmsagt001"


def stack_props() -> dict:
    return {
        "synthesizer": cdk.DefaultStackSynthesizer(
            qualifier=bootstrap_qualifier,
        ),
    }

# Optional: read AgentCore runtime IDs injected by Phase 2.
agentcore_runtime_arn = app.node.try_get_context("agentcore_runtime_arn") or ""
agentcore_qualifier = app.node.try_get_context("agentcore_qualifier") or ""
alarm_email = app.node.try_get_context("alarm_email") or ""

# --------------------------------------------------------------------------
# Phase 1 stacks (no runtime IDs required)
# --------------------------------------------------------------------------

vpc_stack = HermesVpcStack(app, f"{project}-vpc", **stack_props())

security_stack = HermesSecurityStack(app, f"{project}-security", **stack_props())

agentcore_stack = HermesAgentCoreStack(
    app,
    f"{project}-agentcore",
    vpc=vpc_stack.vpc,
    kms_key_arn=security_stack.kms_key.key_arn,
    **stack_props(),
)
agentcore_stack.add_dependency(vpc_stack)
agentcore_stack.add_dependency(security_stack)

observability_stack = HermesObservabilityStack(
    app,
    f"{project}-observability",
    alarm_email=alarm_email,
    **stack_props(),
)

# --------------------------------------------------------------------------
# Phase 3 stacks (need runtime IDs from Phase 2)
# --------------------------------------------------------------------------

router_stack = HermesRouterStack(
    app,
    f"{project}-router",
    execution_role_arn=agentcore_stack.execution_role.role_arn,
    bucket_name=agentcore_stack.bucket.bucket_name,
    agentcore_runtime_arn=agentcore_runtime_arn,
    agentcore_qualifier=agentcore_qualifier,
    **stack_props(),
)
router_stack.add_dependency(agentcore_stack)

cron_stack = HermesCronStack(
    app,
    f"{project}-cron",
    agentcore_runtime_arn=agentcore_runtime_arn,
    agentcore_qualifier=agentcore_qualifier,
    **stack_props(),
)

token_monitoring_stack = HermesTokenMonitoringStack(
    app,
    f"{project}-token-monitoring",
    alarm_topic_arn=observability_stack.alarm_topic.topic_arn,
    **stack_props(),
)
token_monitoring_stack.add_dependency(observability_stack)

# --------------------------------------------------------------------------
# Phase 4 stack (optional — ECS Gateway for WeChat + Feishu)
# --------------------------------------------------------------------------

gateway_stack = HermesGatewayStack(
    app,
    f"{project}-gateway",
    vpc=vpc_stack.vpc,
    agentcore_runtime_arn=agentcore_runtime_arn,
    agentcore_qualifier=agentcore_qualifier,
    **stack_props(),
)
gateway_stack.add_dependency(vpc_stack)

app.synth()
