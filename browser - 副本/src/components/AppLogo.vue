<template>
  <div class="logo-wrap">
    <!-- 简洁图标：占位方块+图片小图标，你后续可换成 svg 文件 -->
    <div class="icon">
      <span class="dot"></span>
      <span class="mountain"></span>
    </div>
    <div class="title">图片管理网站</div>
  </div>
</template>

<style scoped>
.logo-wrap { display:flex; flex-direction:column; align-items:center; gap:10px; }
.icon {
  width:72px; height:72px; border-radius:20px;
  background: #eaf2ff; display:grid; place-items:center;
  box-shadow: 0 6px 18px rgba(22, 93, 255, 0.08) inset;
}
.icon .dot {
  width:10px; height:10px; border-radius:50%; background:#3b82f6;
  position:absolute; transform: translate(-10px,-14px);
}
.icon .mountain {
  width:28px; height:18px; border-left:12px solid transparent; border-right:12px solid transparent;
  border-bottom:18px solid #3b82f6; transform: translateY(6px);
}
.title { font-size:20px; font-weight:700; color:#2b2f36; letter-spacing: 1px; }
</style>
