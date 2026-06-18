/**
 * 版本管理服务
 * 提供版本号显示和更新检测功能
 */
import packageJson from '../../package.json'

export interface VersionInfo {
  current: string
  latest?: string
  hasUpdate: boolean
  releaseUrl?: string
  releaseNotes?: string
  checkTime?: Date
}

// 缓存版本信息，避免频繁请求
let cachedVersionInfo: VersionInfo | null = null
let lastCheckTime: number = 0
const CHECK_INTERVAL = 1000 * 60 * 60 // 1小时缓存

/**
 * 获取当前版本号
 */
export function getCurrentVersion(): string {
  return packageJson.version || '0.0.0'
}

/**
 * 比较版本号
 * @returns 当 v1 > v2 返回 1；v1 < v2 返回 -1；相等返回 0
 */
export function compareVersions(v1: string, v2: string): number {
  const parts1 = v1.replace(/^v/, '').split('.').map(Number)
  const parts2 = v2.replace(/^v/, '').split('.').map(Number)
  
  for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
    const p1 = parts1[i] || 0
    const p2 = parts2[i] || 0
    if (p1 > p2) return 1
    if (p1 < p2) return -1
  }
  return 0
}

/**
 * 检查本地版本元数据
 */
export async function checkLatestVersion(): Promise<VersionInfo> {
  const now = Date.now()
  
  // 使用缓存
  if (cachedVersionInfo && (now - lastCheckTime) < CHECK_INTERVAL) {
    return cachedVersionInfo
  }
  
  const current = getCurrentVersion()
  const versionInfo: VersionInfo = {
    current,
    hasUpdate: false
  }
  
  try {
    const response = await fetch('/version-meta.json', {
      headers: { 'Accept': 'application/json' }
    })
    
    if (!response.ok) {
      console.warn('无法获取本地版本元数据:', response.status)
      return versionInfo
    }
    
    const meta = await response.json()
    const latestVersion = String(meta.latest || current).replace(/^v/, '')
    
    versionInfo.latest = latestVersion
    versionInfo.hasUpdate = compareVersions(latestVersion, current) > 0
    versionInfo.releaseUrl = meta.releaseUrl || ''
    versionInfo.releaseNotes = meta.releaseNotes || ''
    versionInfo.checkTime = new Date()
    
    // 更新缓存
    cachedVersionInfo = versionInfo
    lastCheckTime = now
    
  } catch (error) {
    console.warn('检查本地版本元数据失败:', error)
  }
  
  return versionInfo
}

/**
 * 格式化版本号显示
 */
export function formatVersion(version: string): string {
  if (!version || version === '0.0.0') {
    return 'dev'
  }
  return `v${version.replace(/^v/, '')}`
}
