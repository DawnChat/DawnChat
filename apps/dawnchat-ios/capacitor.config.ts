import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.dawnchat.dev.ios',
  appName: 'DawnChatDev',
  webDir: 'www',
  // 【新增】：允许 Capacitor 拦截并注入原生 SDK 给局域网 IP
  server: {
    allowNavigation: ["*"]
  },
  // 【新增】：开启原生网络劫持，解决跨域问题
  plugins: {
    CapacitorHttp: {
      enabled: true
    }
  }
};

export default config;
