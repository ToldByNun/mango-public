import { detectModelBrand, type ModelBrand } from "../lib/modelBrand";
import mangoModelLogo from "../assets/mango-1.0-logo.png";

type Props = {
  name?: string;
  path?: string;
  size?: number;
};

const ICON_BASE = "https://unpkg.com/@lobehub/icons-static-svg@latest/icons";

const LOCAL_ICONS: Partial<Record<ModelBrand, string>> = {
  mango: mangoModelLogo,
};

const BRAND_SLUG: Record<ModelBrand, string | null> = {
  mango: null,
  gemma: "google-color",
  llama: "meta-color",
  qwen: "qwen-color",
  mistral: "mistral-color",
  phi: "microsoft-color",
  deepseek: "deepseek-color",
  grok: "x",
  yi: "yi-color",
  glm: "zhipu-color",
  kimi: "moonshot",
  olmo: "allenai",
  granite: "ibm-color",
  starcoder: "huggingface-color",
  nvidia: "nvidia-color",
  gptoss: "openai",
  command: "cohere-color",
  claude: "anthropic",
  gemini: "google-color",
  falcon: "tii",
  vicuna: "meta-color",
  wizardlm: "microsoft-color",
  solar: "upstage",
  internlm: "internlm",
  baichuan: "baichuan-color",
  mamba: "huggingface-color",
  rwkv: "rwkv",
  dbrx: "databricks-color",
  jamba: "ai21-color",
  arctic: "snowflake",
  aya: "cohere-color",
  generic: null,
};

export function ModelBrandIcon({ name = "", path = "", size = 14 }: Props): JSX.Element {
  const brand = detectModelBrand(name, path);
  const local = LOCAL_ICONS[brand];
  if (local) {
    return (
      <img
        src={local}
        alt={brand}
        width={size}
        height={size}
        style={{ display: "block", borderRadius: 2 }}
      />
    );
  }

  const slug = BRAND_SLUG[brand];
  if (slug) {
    return (
      <img
        src={`${ICON_BASE}/${slug}.svg`}
        alt={brand}
        width={size}
        height={size}
        style={{ display: "block" }}
      />
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M4.2 3.4h7.6v2.2H9.4v6.8H6.6V5.6H4.2V3.4Zm1.8 0v.8h4V3.4h-4Z" />
    </svg>
  );
}
