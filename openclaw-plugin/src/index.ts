import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';

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
  private config: AMEMConfig;

  constructor(config: AMEMConfig) {
    this.config = config;
    this.startBridge();
  }

  private startBridge() {
    // Find Python bridge
    const bridgePath = this.findBridgePath();
    if (!bridgePath) {
      throw new Error('AMEM Python bridge not found. Please install AMEM: curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash');
    }

    // Spawn Python bridge process
    this.bridgeProcess = spawn('python3', [bridgePath], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

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
      const msg = data.toString().trim();
      if (msg && !msg.includes('Embeddings')) {
        console.error('[AMEM]', msg);
      }
    });

    this.bridgeProcess.on('error', (err: Error) => {
      console.error('[AMEM] Bridge process error:', err);
    });
  }

  private findBridgePath(): string | null {
    // Check common locations
    const home = process.env.HOME || '/root';
    const paths = [
      join(home, '.openclaw', 'workspace', 'memory_system', 'bridge.py'),
      join(home, '.openclaw', 'workspace', 'memory-system', 'native', 'bridge.py'),
      join(__dirname, '..', '..', 'memory_system', 'bridge.py'),
      join(__dirname, '..', '..', 'native', 'bridge.py'),
    ];

    for (const path of paths) {
      if (existsSync(path)) {
        return path;
      }
    }
    return null;
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
    try {
      const result = await this.call('recall', { query, k });
      return {
        content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
      };
    } catch (e: any) {
      return {
        content: [{ type: 'text', text: `Error: ${e.message}` }]
      };
    }
  }

  async store(content: string, permanent: boolean = false): Promise<ToolResult> {
    try {
      const result = await this.call('remember', { content, permanent });
      return {
        content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
      };
    } catch (e: any) {
      return {
        content: [{ type: 'text', text: `Error: ${e.message}` }]
      };
    }
  }

  async graphQuery(entity: string): Promise<ToolResult> {
    try {
      const result = await this.call('graph_query', { entity });
      return {
        content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
      };
    } catch (e: any) {
      return {
        content: [{ type: 'text', text: `Error: ${e.message}` }]
      };
    }
  }

  async ask(question: string): Promise<ToolResult> {
    try {
      const result = await this.call('ask', { question });
      return {
        content: [{ type: 'text', text: result.answer || 'No answer found' }]
      };
    } catch (e: any) {
      return {
        content: [{ type: 'text', text: `Error: ${e.message}` }]
      };
    }
  }

  destroy() {
    if (this.bridgeProcess) {
      this.bridgeProcess.kill();
    }
  }
}

export default function register(api: any) {
  const config: AMEMConfig = api.config || {};
  
  // Check if AMEM is installed
  const home = process.env.HOME || '/root';
  const bridgePath = join(home, '.openclaw', 'workspace', 'memory_system', 'bridge.py');
  
  if (!existsSync(bridgePath)) {
    api.logger.warn('AMEM not found. Install with: curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash');
    return;
  }

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

  api.logger.info('AMEM plugin loaded successfully');
}