const { spawn } = require('child_process');
const path = require('path');

class MemoryPlugin {
  constructor(config) {
    this.config = config;
    this.bridge = null;
    this.requestId = 0;
    this.pendingRequests = new Map();
  }

  async onAgentInit(agent) {
    // Start Python bridge process
    const bridgePath = path.join(__dirname, 'bridge.py');
    this.bridge = spawn('python3', [bridgePath]);
    
    // Send config
    this.bridge.stdin.write(JSON.stringify(this.config) + '\n');
    
    // Handle responses
    this.bridge.stdout.on('data', (data) => {
      const lines = data.toString().split('\n').filter(l => l.trim());
      for (const line of lines) {
        try {
          const response = JSON.parse(line);
          const reqId = response._requestId;
          if (reqId && this.pendingRequests.has(reqId)) {
            const { resolve, reject } = this.pendingRequests.get(reqId);
            this.pendingRequests.delete(reqId);
            if (response.success) {
              resolve(response);
            } else {
              reject(new Error(response.error));
            }
          }
        } catch (e) {
          console.error('[MemoryPlugin] Invalid response:', line);
        }
      }
    });

    // Attach memory API to agent
    agent.memory = {
      remember: (content, permanent = false) => 
        this.call('remember', { content, permanent }),
      recall: (query, k = 5) => 
        this.call('recall', { query, k }),
      context: (query, maxTokens = 1500) => 
        this.call('context', { query, max_tokens: maxTokens }),
      graph: {
        query: (entity) => this.call('graph_query', { entity })
      },
      extract: (text) => this.call('extract', { text }),
      stats: () => this.call('stats', {})
    };

    console.log('[MemoryPlugin] Initialized for agent:', this.config.agentId);
  }

  async call(method, params) {
    return new Promise((resolve, reject) => {
      const reqId = ++this.requestId;
      this.pendingRequests.set(reqId, { resolve, reject });
      
      const request = {
        _requestId: reqId,
        method,
        params
      };
      
      this.bridge.stdin.write(JSON.stringify(request) + '\n');
      
      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingRequests.has(reqId)) {
          this.pendingRequests.delete(reqId);
          reject(new Error('Memory plugin request timeout'));
        }
      }, 30000);
    });
  }

  async onPrompt(agent, prompt) {
    // Inject relevant memories into prompt context
    try {
      const context = await agent.memory.context(prompt, 1000);
      if (context && context.context) {
        return {
          system: `## Relevant Context from Memory\n${context.context}\n\n`,
          user: prompt
        };
      }
    } catch (e) {
      console.error('[MemoryPlugin] Failed to inject context:', e);
    }
    return prompt;
  }

  async onResponse(agent, response) {
    // Auto-extract from conversation if enabled
    if (this.config.autoExtract) {
      try {
        // Get last user message from session
        const messages = agent.session?.messages || [];
        const lastUserMsg = messages.filter(m => m.role === 'user').pop();
        
        if (lastUserMsg) {
          await this.call('process_conversation', {
            user_msg: lastUserMsg.content,
            assistant_msg: response
          });
        }
      } catch (e) {
        console.error('[MemoryPlugin] Failed to extract:', e);
      }
    }
    return response;
  }

  registerTools() {
    return {
      memory_search: {
        description: 'Search agent memory for relevant information',
        parameters: {
          query: { type: 'string', description: 'Search query' },
          k: { type: 'number', description: 'Number of results', default: 5 }
        },
        handler: async ({ query, k }) => {
          return this.call('recall', { query, k });
        }
      },
      memory_store: {
        description: 'Store information in agent memory',
        parameters: {
          content: { type: 'string', description: 'Content to remember' },
          permanent: { type: 'boolean', description: 'Store in long-term memory', default: false }
        },
        handler: async ({ content, permanent }) => {
          return this.call('remember', { content, permanent });
        }
      },
      memory_graph_query: {
        description: 'Query entity relationships in memory graph',
        parameters: {
          entity: { type: 'string', description: 'Entity name to query' }
        },
        handler: async ({ entity }) => {
          return this.call('graph_query', { entity });
        }
      }
    };
  }

  async destroy() {
    if (this.bridge) {
      this.bridge.kill();
    }
  }
}

module.exports = MemoryPlugin;