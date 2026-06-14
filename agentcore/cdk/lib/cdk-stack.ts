import {
  AgentCoreApplication,
  AgentCoreMcp,
  type AgentCoreProjectSpec,
  type AgentCoreMcpSpec,
} from '@aws/agentcore-cdk';
import { Aspects, CfnOutput, Stack, type IAspect, type StackProps } from 'aws-cdk-lib';
import { CfnPolicy } from 'aws-cdk-lib/aws-iam';
import { Construct, type IConstruct } from 'constructs';

export interface AgentCoreStackProps extends StackProps {
  /**
   * The AgentCore project specification containing agents, memories, and credentials.
   */
  spec: AgentCoreProjectSpec;
  /**
   * The MCP specification containing gateways and servers.
   */
  mcpSpec?: AgentCoreMcpSpec;
  /**
   * Credential provider ARNs from deployed state, keyed by credential name.
   */
  credentials?: Record<string, { credentialProviderArn: string; clientSecretArn?: string }>;
}

const BEDROCK_MODEL_ACTIONS = new Set([
  'bedrock:CountTokens',
  'bedrock:InvokeModel',
  'bedrock:InvokeModelWithResponseStream',
]);

class RemoveBedrockModelInvokePolicyAspect implements IAspect {
  public visit(node: IConstruct): void {
    if (!(node instanceof CfnPolicy)) {
      return;
    }

    const document = Stack.of(node).resolve(node.policyDocument) as { Statement?: unknown };
    if (!Array.isArray(document.Statement)) {
      return;
    }

    const filteredStatements = document.Statement.flatMap((statement) => {
      if (!statement || typeof statement !== 'object') {
        return [statement];
      }

      const policyStatement = statement as { Action?: string | string[] };
      const actions = Array.isArray(policyStatement.Action) ? policyStatement.Action : [policyStatement.Action];
      const remainingActions = actions.filter(
        (action): action is string => typeof action === 'string' && !BEDROCK_MODEL_ACTIONS.has(action),
      );

      if (remainingActions.length === actions.length) {
        return [statement];
      }
      if (remainingActions.length === 0) {
        return [];
      }

      policyStatement.Action = remainingActions.length === 1 ? remainingActions[0] : remainingActions;
      return [policyStatement];
    });

    if (filteredStatements.length !== document.Statement.length) {
      node.addPropertyOverride('PolicyDocument.Statement', filteredStatements);
    }
  }
}

/**
 * CDK Stack that deploys AgentCore infrastructure.
 *
 * This is a thin wrapper that instantiates L3 constructs.
 * All resource logic and outputs are contained within the L3 constructs.
 */
export class AgentCoreStack extends Stack {
  /** The AgentCore application containing all agent environments */
  public readonly application: AgentCoreApplication;

  constructor(scope: Construct, id: string, props: AgentCoreStackProps) {
    super(scope, id, props);

    const { spec, mcpSpec, credentials } = props;

    // Create AgentCoreApplication with all agents
    this.application = new AgentCoreApplication(this, 'Application', {
      spec,
    });
    Aspects.of(this).add(new RemoveBedrockModelInvokePolicyAspect());

    // Create AgentCoreMcp if there are gateways configured
    if (mcpSpec?.agentCoreGateways && mcpSpec.agentCoreGateways.length > 0) {
      new AgentCoreMcp(this, 'Mcp', {
        projectName: spec.name,
        mcpSpec,
        agentCoreApplication: this.application,
        credentials,
        projectTags: spec.tags,
      });
    }

    // Stack-level output
    new CfnOutput(this, 'StackNameOutput', {
      description: 'Name of the CloudFormation Stack',
      value: this.stackName,
    });
  }
}
