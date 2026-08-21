export type ModelBrand =
  | "mango"
  | "gemma"
  | "llama"
  | "qwen"
  | "mistral"
  | "phi"
  | "deepseek"
  | "grok"
  | "yi"
  | "glm"
  | "kimi"
  | "olmo"
  | "granite"
  | "starcoder"
  | "nvidia"
  | "gptoss"
  | "command"
  | "claude"
  | "gemini"
  | "falcon"
  | "vicuna"
  | "wizardlm"
  | "solar"
  | "internlm"
  | "baichuan"
  | "mamba"
  | "rwkv"
  | "dbrx"
  | "jamba"
  | "arctic"
  | "aya"
  | "generic";

const RULES: Array<{ brand: ModelBrand; pattern: RegExp }> = [
  // Prefer mango over base-family brands (e.g. qwen3.8-27b-mango).
  { brand: "mango", pattern: /\bmango\b/ },
  { brand: "gemma", pattern: /\b(code)?gemma/ },
  { brand: "qwen", pattern: /\bqwen|qwq\b/ },
  { brand: "mistral", pattern: /\b(mistral|mixtral|ministral|pixtral|codestral|devstral)\b/ },
  { brand: "phi", pattern: /\bphi\b/ },
  { brand: "deepseek", pattern: /\bdeepseek\b/ },
  { brand: "grok", pattern: /\bgrok\b/ },
  { brand: "llama", pattern: /\b(code|tiny)?llama/ },
  { brand: "yi", pattern: /\byi\b/ },
  { brand: "glm", pattern: /\b(chat)?glm/ },
  { brand: "kimi", pattern: /\b(kimi|moonshot)\b/ },
  { brand: "olmo", pattern: /\bolmo/ },
  { brand: "granite", pattern: /\bgranite\b/ },
  { brand: "starcoder", pattern: /\b(starcoder|starling|starchat)\b/ },
  { brand: "nvidia", pattern: /\b(nemotron|nvidia)\b/ },
  { brand: "gptoss", pattern: /\b(gpt2?|nanogpt|gpt\s?neo|gpt\s?j)\b/ },
  { brand: "command", pattern: /\b(command|cohere|aya)\b/ },
  { brand: "claude", pattern: /\bclaude\b/ },
  { brand: "gemini", pattern: /\bgemini\b/ },
  { brand: "falcon", pattern: /\bfalcon\b/ },
  { brand: "vicuna", pattern: /\bvicuna\b/ },
  { brand: "wizardlm", pattern: /\b(wizard|wizardlm|wizardcoder)\b/ },
  { brand: "solar", pattern: /\bsolar\b/ },
  { brand: "internlm", pattern: /\binternlm\b/ },
  { brand: "baichuan", pattern: /\bbaichuan\b/ },
  { brand: "mamba", pattern: /\bmamba\b/ },
  { brand: "rwkv", pattern: /\brwkv\b/ },
  { brand: "dbrx", pattern: /\b(dbrx|databricks)\b/ },
  { brand: "jamba", pattern: /\bjamba\b/ },
  { brand: "arctic", pattern: /\barctic\b/ },
  { brand: "aya", pattern: /\baya\b/ },
];

export function detectModelBrand(...parts: Array<string | undefined | null>): ModelBrand {
  const blob = parts
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .replace(/[/\\_.-]+/g, " ");
  for (const rule of RULES) {
    if (rule.pattern.test(blob)) return rule.brand;
  }
  return "generic";
}
