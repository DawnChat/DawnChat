import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AppUpdateDialog from '@/features/update/components/AppUpdateDialog.vue'

describe('AppUpdateDialog', () => {
  it('建议更新显示稍后与下载按钮', () => {
    const wrapper = mount(AppUpdateDialog, {
      attachTo: document.body,
      props: {
        visible: true,
        mode: 'recommended',
        latestVersion: '2.1.0'
      }
    })

    expect(document.body.textContent || '').toContain('发现新版本')
    expect(document.body.querySelector('.dialog-btn-cancel')).toBeTruthy()
    expect(document.body.querySelector('.dialog-btn-confirm')?.textContent || '').toContain('去下载')
    wrapper.unmount()
  })

  it('强制更新只显示下载按钮', () => {
    const wrapper = mount(AppUpdateDialog, {
      attachTo: document.body,
      props: {
        visible: true,
        mode: 'forced',
        latestVersion: '2.1.0'
      }
    })

    expect(document.body.textContent || '').toContain('必须更新后继续使用')
    expect(document.body.querySelector('.dialog-btn-cancel')).toBeFalsy()
    expect(document.body.querySelector('.dialog-btn-confirm')?.textContent || '').toContain('去下载')
    wrapper.unmount()
  })
})
