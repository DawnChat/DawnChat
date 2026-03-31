import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import WebPublishDialog from '@/features/plugin/components/WebPublishDialog.vue'

describe('WebPublishDialog', () => {
  it('展示本地与线上版本，并阻止不大于线上版本的提交', async () => {
    const wrapper = mount(WebPublishDialog, {
      props: {
        visible: true,
        pluginName: 'Hello Site',
        pluginVersion: '1.0.0',
        pluginDescription: 'demo',
        loading: false,
        status: {
          plugin_id: 'com.dawnchat.hello-site',
          local_version: '1.0.0',
          manifest_version: '1.0.0',
          package_version: '1.0.0',
          version_mismatch: false,
          remote_latest_version: '1.1.0',
          remote_release_status: 'published',
          current_status: 'published',
          current_slug: 'hello-site',
          visibility: 'private',
          runtime_url: 'https://sites.dawnchat.com/my-sites/hello-site',
          last_published_at: '2026-03-07T00:00:00Z',
          active_task: null,
          metadata: {},
          remote_error: null,
        },
      },
    })

    expect(wrapper.text()).toContain('本地源码版本: 1.0.0')
    expect(wrapper.text()).toContain('线上最新版本: 1.1.0')
    expect(wrapper.text()).toContain('发布版本必须大于线上最新版本 1.1.0')
    expect(wrapper.get('.btn-primary').attributes('disabled')).toBeDefined()

    const versionInput = wrapper.findAll('input')[2]
    await versionInput.setValue('1.1.1')

    expect(wrapper.text()).toContain('版本校验通过，将发布一个高于 1.1.0 的新版本')
    expect(wrapper.get('.btn-primary').attributes('disabled')).toBeUndefined()

    await wrapper.get('.btn-primary').trigger('click')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      slug: 'hello-site',
      title: 'Hello Site',
      initial_visibility: 'private',
      version: '1.1.1',
    })
  })

  it('展示任务进度与成功结果', () => {
    const wrapper = mount(WebPublishDialog, {
      props: {
        visible: true,
        pluginName: 'Hello Site',
        pluginVersion: '1.0.0',
        pluginDescription: 'demo',
        loading: true,
        status: {
          plugin_id: 'com.dawnchat.hello-site',
          local_version: '1.1.1',
          manifest_version: '1.1.1',
          package_version: '1.1.1',
          version_mismatch: false,
          remote_latest_version: '1.1.0',
          remote_release_status: 'published',
          current_status: 'building',
          current_slug: 'hello-site',
          visibility: 'private',
          runtime_url: 'https://sites.dawnchat.com/my-sites/hello-site',
          last_published_at: '2026-03-07T00:00:00Z',
          active_task: null,
          metadata: {},
          remote_error: null,
        },
        task: {
          id: 'task-1',
          plugin_id: 'com.dawnchat.hello-site',
          status: 'running',
          stage: 'uploading',
          progress: 72,
          message: '正在上传网页资源（2/3）',
          created_at: '2026-03-07T00:00:00Z',
          updated_at: '2026-03-07T00:00:05Z',
          error: null,
          result: null,
        },
        result: {
          plugin_id: 'com.dawnchat.hello-site',
          web_app: {
            id: 'web-app-1',
            plugin_id: 'com.dawnchat.hello-site',
            slug: 'hello-site',
            title: 'Hello Site',
            description: 'demo',
            framework: 'vue',
            visibility: 'private',
            status: 'published',
          },
          release: {
            id: 'release-1',
            web_app_id: 'web-app-1',
            version: '1.1.1',
            status: 'published',
            published_at: '2026-03-07T00:00:10Z',
          },
          runtime_url: 'https://sites.dawnchat.com/my-sites/hello-site',
          artifact_count: 3,
        },
      },
    })

    expect(wrapper.text()).toContain('当前阶段: 上传资源')
    expect(wrapper.text()).toContain('72%')
    expect(wrapper.text()).toContain('发布成功')
    expect(wrapper.text()).toContain('已发布版本: 1.1.1')
  })
})
