export interface IwpBuildPromptPayload {
  pluginId: string
  iwpRoot: string
  changedFilePath: string
  changeHint?: string
}

export const createIwpBuildPrompt = (payload: IwpBuildPromptPayload): string => {
  const pluginId = String(payload.pluginId || '').trim()
  const iwpRoot = String(payload.iwpRoot || 'InstructWare.iw').trim()
  const changedFilePath = String(payload.changedFilePath || '').trim()
  const changeHint = String(payload.changeHint || '').trim()
  const lines = [
    `请在插件工作区 ${pluginId} 执行一次 IWP Build 流程。`,
    `本次重点检查的 Markdown 文件: ${changedFilePath || '(未指定)'}`,
    `IWP 根目录: ${iwpRoot}`,
    '',
    '严格执行以下步骤：',
    '1) 先读取 .iwp-lint.yaml，确认 iwp_root/code_roots/compiled_dir 与 preset。',
    '2) 先执行 session diff 判断本地 Markdown 是否存在有效变更。',
    '3) 如果没有有效变更，直接返回 no-op 结论并说明原因，不做代码改动。',
    '4) 如果有变更，按 Stage2 -> Stage3 -> Stage4 执行：',
    '   - Stage2: 只实现 _ir 代码与测试，不修改 @iwp.link。',
    '   - Stage3: 仅在改动邻域补齐/更新 @iwp.link。',
    '   - Stage4: 输出 reverse review 结果（JSON 结论可简述）。',
    '5) 如遇 node 映射不明确，必须列出 unresolved 项，不要猜测 node_id。',
    '',
    '输出要求：',
    '- 简要结论（success/no-op/fail）',
    '- 关键改动文件清单（Markdown 与 _ir）',
    '- 若失败，给出阻塞点与下一步建议',
  ]
  if (changeHint) {
    lines.push('', `补充上下文: ${changeHint}`)
  }
  return lines.join('\n')
}
