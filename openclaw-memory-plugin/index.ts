import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

interface AMEMConfig {
  agentId: string;
  embeddingProvider: string;
  autoExtract: boolean;
  graphMemory: boolean;
}

interface ToolParams {
  [key: string]: any;
}

interface ToolResult {
  content: Array<{ type: string; text: string }>;
}

class AMEMBridge {
  private bridgeProcess: any;
  private requestId = 0;
  private pendingRequests = new Map<number, { resolve: (value: any) => void; reject: (reason: any) => void }>();

  constructor(private config: AMEMConfig) {
    this.startBridge();
  }

  private startBridge() {
    // Spawn Python bridge process
    const bridgePath = join(__dirname, 'bridge.py');
    this.bridgeProcess = spawn('python3', [bridgePath]);

    // Send config
    this.bridgeProcess.stdin.write(JSON.stringify(this.config) + '\n');

    // Handle responses
    this.bridgeProcess.stdout.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n').filter(l => l.trim());
      for (const line of lines) {
        try {
          const response = JSON.parse(line);
          const reqId = response._requestId;
          if (reqId && this.pendingRequests.has(reqId)) {
            const { resolve, reject } = this.pendingRequests.get(reqId)!;
            this.pendingRequests.delete(reqId);
            if (response.success) {
              resolve(response);
            } else {
              reject(new Error(response.error));
            }
          }
        } catch (e) {
          console.error('[AMEM] Invalid response:', line);
        }
      }
    });

    this.bridgeProcess.stderr.on('data', (data: Buffer) => {
      console.error('[AMEM Python]', data.toString());
    });
  }

  private async call(method: string, params: ToolParams): Promise<any> {
    return new Promise((resolve, reject) => {
      const reqId = ++this.requestId;
      this.pendingRequests.set(reqId, { resolve, reject });

      const request = {
        _requestId: reqId,
        method,
        params
      };

      this.bridgeProcess.stdin.write(JSON.stringify(request) + '\n');

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingRequests.has(reqId)) {
          this.pendingRequests.delete(reqId);
          reject(new Error('AMEM request timeout'));
        }
      }, 30000);
    });
  }

  async search(query: string, k: number = 5): Promise<ToolResult> {
    const result = await this.call('recall', { query, k });
    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
    };
  }

  async store(content: string, permanent: boolean = false): Promise<ToolResult> {
    const result = await this.call('remember', { content, permanent });
    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
    };
  }

  async graphQuery(entity: string): Promise<ToolResult> {
    const result = await this.call('graph_query', { entity });
    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
    };
  }

  async ask(question: string): Promise<ToolResult> {
    const result = await this.call('ask', { question });
    return {
      content: [{ type: 'text', text: result.answer || 'No answer found' }]
    };
  }

  destroy() {
    if (this.bridgeProcess) {
      this.bridgeProcess.kill();
    }
  }
}

export default function register(api: any) {
  const config: AMEMConfig = api.config;
  const bridge = new AMEMBridge(config);

  // Register memory tools
  api.registerTool({
    name: 'amem_search',
    description: 'Search AMEM memory for relevant information',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
        k: { type: 'number', description: 'Number of results', default: 5 }
      },
      required: ['query']
    },
    async execute(_id: string, params: ToolParams): Promise<ToolResult> {
      return bridge.search(params.query, params.k);
    }
  });

  api.registerTool({
    name: 'amem_store',
    description: 'Store information in AMEM memory',
    parameters: {
      type: 'object',
      properties: {
        content: { type: 'string', description: 'Content to remember' },
        permanent: { type: 'boolean', description: 'Store in long-term memory', default: false }
      },
      required: ['content']
    },
    async execute(_id: string, params: ToolParams): Promise<ToolResult> {
      return bridge.store(params.content, params.permanent);
    }
  });

  api.registerTool({
    name: 'amem_graph_query',
    description: 'Query entity relationships in AMEM graph memory',
    parameters: {
      type: 'object',
      properties: {
        entity: { type: 'string', description: 'Entity name to query' }
      },
      required: ['entity']
    },
    async execute(_id: string, params: ToolParams): Promise<ToolResult> {
      return bridge.graphQuery(params.entity);
    }
  });

  api.registerTool({
    name: 'amem_ask',
    description: 'Ask a question using AMEM graph and semantic memory',
    parameters: {
      type: 'object',
      properties: {
        question: { type: 'string', description: 'Question to ask' }
      },
      required: ['question']
    },
    async execute(_id: string, params: ToolParams): Promise<ToolResult> {
      return bridge.ask(params.question);
    }
  });

  // Cleanup on shutdown
  api.onDestroy(() => {
    bridge.destroy();
  });
}