<script setup>
import { ref, reactive } from 'vue'
import { Search, Refresh, Calendar, MagicStick, Picture } from '@element-plus/icons-vue'

const keyword = ref('')
const filters = reactive({
  timeRange: [],
  size: [0, 200],
  fileType: '',
  camera: '',
  lens: '',
  iso: '',
  aperture: '',
  shutter: '',
  timeDimension: 'shoot',
})

const quickRanges = ['今天', '最近三天', '最近一周', '最近一月']

const results = ref([
  { id: 1, title: '可爱猫猫', date: '2025-12-01', size: '266 KB', cover: 'https://picsum.photos/seed/cat20/720/480', tags: ['萌宠', '高清'] },
  { id: 2, title: '春日花海', date: '2025-11-28', size: '647 KB', cover: 'https://picsum.photos/seed/flower88/720/480', tags: ['花朵', '阳光'] },
  { id: 3, title: '夜景街道', date: '2025-11-27', size: '1.2 MB', cover: 'https://picsum.photos/seed/night77/720/480', tags: ['夜景', '城市'] },
  { id: 4, title: '山脉云海', date: '2025-11-25', size: '994 KB', cover: 'https://picsum.photos/seed/mountain33/720/480', tags: ['风景', '云雾'] },
  { id: 5, title: '午后咖啡', date: '2025-11-24', size: '520 KB', cover: 'https://picsum.photos/seed/coffee9/720/480', tags: ['生活', '食物'] },
  { id: 6, title: '户外露营', date: '2025-11-20', size: '1.0 MB', cover: 'https://picsum.photos/seed/camp2/720/480', tags: ['旅行', '自然'] },
])

const onSearch = () => {
  // TODO: 接入真实搜索接口
}

const onReset = () => {
  keyword.value = ''
  filters.timeRange = []
  filters.size = [0, 200]
  filters.fileType = ''
  filters.camera = ''
  filters.lens = ''
  filters.iso = ''
  filters.aperture = ''
  filters.shutter = ''
}

const applyQuick = (label) => {
  // TODO: 可根据 label 预填时间范围
}
</script>

<template>
  <div class="search-page">
    <div class="header">
      <div>
        <h2>搜索引擎 · 全局检索</h2>
        <p class="sub">名称/标签/EXIF/时间/文件属性多维组合筛选，快速命中想要的图片</p>
      </div>
      <div class="mode">
        <el-icon><MagicStick /></el-icon>
        <span>网格模式</span>
        <el-switch v-model="filters.timeDimension" active-value="shoot" inactive-value="upload" />
      </div>
    </div>

    <div class="search-bar card">
      <el-input
        v-model="keyword"
        size="large"
        placeholder="输入图片名称、文件名或关键词（回车搜索）"
        :prefix-icon="Search"
      />
      <div class="search-actions">
        <el-button type="primary" :icon="Search" size="large" @click="onSearch">搜索</el-button>
        <el-button :icon="Refresh" size="large" @click="onReset">清空条件</el-button>
      </div>
    </div>

    <div class="card filter-card">
      <div class="card-title">
        <span>高级筛选</span>
        <span class="count">符合条件的图片示例</span>
      </div>

      <div class="filter-grid">
        <el-form label-position="top">
          <div class="row">
            <el-form-item label="拍摄/上传时间">
              <el-date-picker
                v-model="filters.timeRange"
                type="daterange"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                unlink-panels
                :prefix-icon="Calendar"
                style="width: 100%;"
              />
              <div class="quick-range">
                <el-check-tag
                  v-for="tag in quickRanges"
                  :key="tag"
                  checked
                  @click="applyQuick(tag)"
                >
                  {{ tag }}
                </el-check-tag>
              </div>
            </el-form-item>

            <el-form-item label="图片格式">
              <el-select v-model="filters.fileType" placeholder="选择需要的文件格式" clearable>
                <el-option label="JPG" value="jpg" />
                <el-option label="PNG" value="png" />
                <el-option label="WEBP" value="webp" />
                <el-option label="HEIC" value="heic" />
              </el-select>
            </el-form-item>
          </div>

          <div class="row">
            <el-form-item label="EXIF 维度">
              <div class="exif-grid">
                <el-input v-model="filters.camera" placeholder="相机型号" clearable />
                <el-input v-model="filters.lens" placeholder="镜头型号" clearable />
                <el-input v-model="filters.iso" placeholder="ISO (如 100)" clearable />
                <el-input v-model="filters.aperture" placeholder="光圈 (如 f/1.8)" clearable />
                <el-input v-model="filters.shutter" placeholder="快门 (如 1/125s)" clearable />
              </div>
            </el-form-item>
          </div>

          <div class="row">
            <el-form-item label="文件大小 (MB)">
              <el-slider v-model="filters.size" :max="200" range :show-tooltip="true" />
            </el-form-item>
          </div>
        </el-form>
      </div>
    </div>

    <div class="card result-card">
      <div class="card-title space">
        <div class="title-left">
          <el-icon><Picture /></el-icon>
          <span>搜索结果示例</span>
        </div>
        <div class="tag-row">
          <el-tag type="success" effect="plain">热门</el-tag>
          <el-tag type="warning" effect="plain">高清</el-tag>
          <el-tag type="info" effect="plain">最近上传</el-tag>
        </div>
      </div>

      <div class="result-grid">
        <div v-for="item in results" :key="item.id" class="result-item">
          <div class="thumb" :style="{ backgroundImage: `url(${item.cover})` }"></div>
          <div class="info">
            <div class="title">{{ item.title }}</div>
            <div class="meta">{{ item.date }} · {{ item.size }}</div>
            <div class="tags">
              <el-tag v-for="tag in item.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-page {
  --primary: var(--app-primary);
  --primary-strong: var(--app-primary-strong);
  --soft: var(--app-primary-soft);
  --accent: var(--app-accent);
  --border: var(--app-border);
  --text: var(--app-text);
  --muted: var(--app-muted);
  color: var(--text);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
}

.header h2 {
  margin: 0;
  color: var(--primary-strong);
}

.sub {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 14px;
}

.mode {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
}

.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 12px 26px rgba(75, 140, 255, 0.08);
}

.search-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-actions {
  display: flex;
  gap: 10px;
}

.filter-card .card-title,
.result-card .card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 700;
  color: var(--primary-strong);
}

.count {
  color: var(--muted);
  font-size: 13px;
}

.filter-grid {
  background: #f8fbff;
  border: 1px dashed var(--border);
  border-radius: 14px;
  padding: 12px;
}

.row {
  display: flex;
  flex-direction: column;
}

.row + .row {
  margin-top: 12px;
}

.quick-range {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.exif-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.result-card .space {
  margin-bottom: 10px;
}

.title-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-row {
  display: flex;
  gap: 8px;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.result-item {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(75, 140, 255, 0.08);
}

.thumb {
  background-size: cover;
  background-position: center;
  aspect-ratio: 4 / 3;
}

.info {
  padding: 10px 12px 12px;
}

.title {
  font-weight: 700;
  color: var(--text);
}

.meta {
  color: var(--muted);
  font-size: 13px;
  margin: 4px 0;
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

@media (max-width: 960px) {
  .search-bar {
    flex-direction: column;
  }

  .search-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .exif-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .exif-grid {
    grid-template-columns: 1fr;
  }
}
</style>
