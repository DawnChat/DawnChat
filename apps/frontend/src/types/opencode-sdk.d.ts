declare module '@opencode-ai/sdk' {
  export function createOpencodeClient(config: {
    baseUrl: string
    throwOnError?: boolean
  }): any
}

declare module '@opencode-ai/sdk/client' {
  export function createOpencodeClient(config: {
    baseUrl: string
    throwOnError?: boolean
  }): any
}
