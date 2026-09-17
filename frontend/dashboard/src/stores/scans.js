import { ref } from 'vue'
import { defineStore } from 'pinia'
import scansApi from '@/api/scans'

export const useScansStore = defineStore('scans', () => {
  const list = ref([])
  const detail = ref(null)

  async function fetchList() {
    list.value = (await scansApi.list()).data
  }
  async function fetchDetail(id) {
    detail.value = (await scansApi.get(id)).data
    return detail.value
  }
  async function create(target, mode) {
    const scan = (await scansApi.create({ target, mode })).data
    await fetchList()
    return scan
  }

  return { list, detail, fetchList, fetchDetail, create }
})
