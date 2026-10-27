/**
 * W3C WebMCP (Web Model Context Protocol) Integration
 * Spec draft: https://webmachinelearning.github.io/webmcp/
 *
 * Exposes browser-native model tools on document.modelContext (with fallback to navigator.modelContext)
 * for in-browser AI agents (ChatGPT Agent, Claude in-browser, Gemini) querying the candidate's CV.
 */

export interface WebMCPToolAnnotation {
  readOnlyHint?: boolean;
  untrustedContentHint?: boolean;
}

export interface WebMCPToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
    additionalProperties?: boolean;
  };
  annotations?: WebMCPToolAnnotation;
  execute: (input: any) => Promise<any>;
}

export interface WebMCPContext {
  registerTool: (tool: WebMCPToolDefinition) => void;
  unregisterTool?: (name: string) => void;
  getTools?: () => WebMCPToolDefinition[];
}

/**
 * Safely resolves the active ModelContext from document or navigator.
 */
export function getModelContext(): WebMCPContext | null {
  if (typeof window === "undefined") return null;

  const doc = document as any;
  const nav = navigator as any;

  if (doc?.modelContext && typeof doc.modelContext.registerTool === "function") {
    return doc.modelContext;
  }
  if (nav?.modelContext && typeof nav.modelContext.registerTool === "function") {
    return nav.modelContext;
  }

  return null;
}

/**
 * Registers CV Assistant tools with the browser's modelContext.
 * Gracefully degrades if WebMCP is unsupported in the current browser environment.
 */
export function registerWebMCPTools(token: string, apiBase: string = ""): boolean {
  if (typeof window === "undefined" || !token) return false;

  const basePath = apiBase || "";

  const candidateLabel = process.env.NEXT_PUBLIC_CANDIDATE_NAME || "the candidate";

  // 1. Primary Tool: ask_cv
  const askCvTool: WebMCPToolDefinition = {
    name: "ask_cv",
    description:
      `Ask factual questions about ${candidateLabel}'s professional experience, roles, skills, projects and qualifications. Use this tool when answering questions about whether they have worked with a technology, regulation, industry, role or type of transformation.`,
    inputSchema: {
      type: "object",
      properties: {
        question: {
          type: "string",
          description: `A factual question about ${candidateLabel}'s professional background.`
        }
      },
      required: ["question"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      untrustedContentHint: false
    },
    async execute(input: { question: string }) {
      if (!input || typeof input.question !== "string" || !input.question.trim()) {
        throw new Error("Invalid input: 'question' string parameter is required.");
      }

      if (input.question.length > 2500) {
        throw new Error("Invalid input: question exceeds maximum length of 2500 characters.");
      }

      const res = await fetch(`${basePath}/a/${token}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Access-Method": "webmcp"
        },
        body: JSON.stringify({
          question: input.question.trim(),
          access_method: "webmcp",
          tool: "ask_cv"
        })
      });

      if (!res.ok) {
        let errMessage = `CV assistant request failed with HTTP ${res.status}`;
        try {
          const errData = await res.json();
          if (errData?.detail) errMessage = errData.detail;
        } catch {
          // ignore json parse error
        }
        throw new Error(errMessage);
      }

      const data = await res.json();
      return {
        answer: data.answer,
        confidence: data.confidence,
        evidence: data.evidence || [],
        source: "cv-assistant",
        request_id: data.request_id
      };
    }
  };

  // 2. Secondary Tool: get_cv_summary
  const getSummaryTool: WebMCPToolDefinition = {
    name: "get_cv_summary",
    description:
      `Retrieve a concise executive summary and key competence areas of ${candidateLabel}'s professional profile.`,
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      untrustedContentHint: false
    },
    async execute() {
      const res = await fetch(`${basePath}/a/${token}/profile.json`, {
        headers: {
          "X-Access-Method": "webmcp"
        }
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch CV profile summary: ${res.status}`);
      }
      const pdata = await res.json();
      return {
        name: pdata.name,
        headline: pdata.headline,
        summary: pdata.description,
        capabilities: pdata.capabilities,
        suggested_questions: pdata.suggested_questions || [],
        source: "cv-assistant"
      };
    }
  };

  // 3. Secondary Tool: get_experience
  const getExperienceTool: WebMCPToolDefinition = {
    name: "get_experience",
    description:
      `Ask about ${candidateLabel}'s factual track record in a specific topic (e.g. 'DORA', 'Fintech', 'ISO 27001', 'Cloud Architecture', 'M&A').`,
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: "Domain, framework, technology, or regulation to query."
        }
      },
      required: ["topic"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      untrustedContentHint: false
    },
    async execute(input: { topic: string }) {
      if (!input?.topic || typeof input.topic !== "string") {
        throw new Error("Invalid input: 'topic' string parameter is required.");
      }
      return askCvTool.execute({
        question: `What factual experience and track record does ${candidateLabel} have with ${input.topic.trim()}?`
      });
    }
  };

  const tools = [askCvTool, getSummaryTool, getExperienceTool];

  // Store registered tools on window for inspection, diagnostics, and polyfill support
  try {
    (window as any).__webmcp_registered_tools = tools;
  } catch {
    // ignore
  }

  // Attempt registration on W3C standard document.modelContext or navigator.modelContext
  const mc = getModelContext();
  if (mc && typeof mc.registerTool === "function") {
    try {
      tools.forEach((t) => mc.registerTool(t));
      return true;
    } catch (e) {
      console.warn("Notice: WebMCP tool registration failed:", e);
      return false;
    }
  }

  return false;
}
