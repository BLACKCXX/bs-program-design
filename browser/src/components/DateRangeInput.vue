<script setup>
import { computed, ref, watch } from 'vue'
import { Calendar } from '@element-plus/icons-vue'

const props = defineProps({
  start: { type: String, default: '' },
  end: { type: String, default: '' },
  size: { type: String, default: 'default' },
  disabled: { type: Boolean, default: false },
  placeholderStart: { type: String, default: '开始日期' },
  placeholderEnd: { type: String, default: '结束日期' },
})

const emit = defineEmits(['update:start', 'update:end', 'change'])

const startVal = ref(props.start || '')
const endVal = ref(props.end || '')

watch(
  () => props.start,
  (v) => {
    startVal.value = v || ''
  }
)
watch(
  () => props.end,
  (v) => {
    endVal.value = v || ''
  }
)

const toDate = (val) => {
  if (!val) return null
  const d = new Date(val)
  return Number.isNaN(d.getTime()) ? null : d
}

const syncEndAfterStart = () => {
  const s = toDate(startVal.value)
  const e = toDate(endVal.value)
  if (s && e && e < s) {
    endVal.value = startVal.value
    emit('update:end', endVal.value)
  }
}

const onStartChange = (val) => {
  startVal.value = val || ''
  emit('update:start', startVal.value)
  syncEndAfterStart()
  emit('change', { start: startVal.value, end: endVal.value })
}

const onEndChange = (val) => {
  const next = val || ''
  const s = toDate(startVal.value)
  const e = toDate(next)
  if (s && e && e < s) {
    endVal.value = startVal.value
  } else {
    endVal.value = next
  }
  emit('update:end', endVal.value)
  emit('change', { start: startVal.value, end: endVal.value })
}

const disableStart = (date) => {
  const e = toDate(endVal.value)
  if (!e) return false
  return date.getTime() > e.setHours(23, 59, 59, 999)
}

const disableEnd = (date) => {
  const s = toDate(startVal.value)
  if (!s) return false
  return date.getTime() < s.setHours(0, 0, 0, 0)
}

const pickerSize = computed(() => props.size || 'default')
</script>

<template>
  <div class="date-range-input">
    <el-date-picker
      v-model="startVal"
      class="date-field"
      type="date"
      :size="pickerSize"
      :disabled="disabled"
      :placeholder="placeholderStart"
      format="YYYY-MM-DD"
      value-format="YYYY-MM-DD"
      :disabled-date="disableStart"
      :prefix-icon="Calendar"
      clearable
      @change="onStartChange"
    />
    <span class="separator">至</span>
    <el-date-picker
      v-model="endVal"
      class="date-field"
      type="date"
      :size="pickerSize"
      :disabled="disabled"
      :placeholder="placeholderEnd"
      format="YYYY-MM-DD"
      value-format="YYYY-MM-DD"
      :disabled-date="disableEnd"
      :prefix-icon="Calendar"
      clearable
      @change="onEndChange"
    />
  </div>
</template>

<style scoped>
.date-range-input {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.date-field {
  flex: 1;
}
.separator {
  color: #6b7280;
  font-size: 13px;
  white-space: nowrap;
}
</style>
