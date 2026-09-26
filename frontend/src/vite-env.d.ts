/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端基地址；开发时留空走 Vite 代理。 */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
