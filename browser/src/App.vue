<template>
  <router-view />
</template>

<style>
/* 全局基础样式与字体渲染优化 */
html, body, #app { height: 100%; }
body { margin:0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, 'Noto Sans', 'Noto Sans CJK SC', sans-serif;
       -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
a { color: inherit; }

:root {
  --app-primary: #4b8cff;
  --app-primary-strong: #3b82f6;
  --app-primary-soft: #e5f0ff;
  --app-accent: #0ea5e9;
  --app-bg: #f4f7fb;
  --app-text: #111827;
  --app-muted: #6b7280;
  --app-border: #e5e7eb;
  --el-color-primary: var(--app-primary);
  --el-color-primary-light-3: #7fa8ff;
  --el-color-primary-light-5: #aac4ff;
  --el-color-primary-light-7: #d5e1ff;
  --el-color-primary-light-9: var(--app-primary-soft);
}

body {
  background: var(--app-bg);
  color: var(--app-text);
}
</style>
