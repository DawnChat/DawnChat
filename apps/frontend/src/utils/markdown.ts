/**
 * 轻量级 Markdown 渲染器
 * 
 * 支持的语法：
 * - 标题 (# ~ ######)
 * - 粗体、斜体、删除线
 * - 代码块和行内代码
 * - 有序/无序列表
 * - 链接
 * - 引用块
 * - 水平分割线
 * - 换行
 * 
 * 不支持（避免过度复杂）：
 * - 表格
 * - 嵌套列表
 * - 图片（安全考虑）
 */

/**
 * 将 Markdown 文本渲染为 HTML
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  
  // 保护代码块，避免内容被其他规则处理
  const codeBlocks: string[] = []
  let processed = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const index = codeBlocks.length
    const escapedCode = escapeHtml(code.trim())
    const langClass = lang ? ` class="language-${lang}"` : ''
    codeBlocks.push(`<pre><code${langClass}>${escapedCode}</code></pre>`)
    return `___CODE_BLOCK_${index}___`
  })
  
  // 保护行内代码
  const inlineCodes: string[] = []
  processed = processed.replace(/`([^`]+)`/g, (_, code) => {
    const index = inlineCodes.length
    inlineCodes.push(`<code>${escapeHtml(code)}</code>`)
    return `___INLINE_CODE_${index}___`
  })
  
  // 分行处理
  const lines = processed.split('\n')
  const result: string[] = []
  let inBlockquote = false
  let inList = false
  let listType: 'ul' | 'ol' = 'ul'
  
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i]
    
    // 检查是否需要关闭列表
    const isListItem = /^(\s*[-*]\s|^\s*\d+\.\s)/.test(line)
    if (inList && !isListItem && line.trim() !== '') {
      result.push(`</${listType}>`)
      inList = false
    }
    
    // 检查是否需要关闭引用块
    const isBlockquote = line.startsWith('>')
    if (inBlockquote && !isBlockquote && line.trim() !== '') {
      result.push('</blockquote>')
      inBlockquote = false
    }
    
    // 水平分割线
    if (/^[-*_]{3,}\s*$/.test(line)) {
      result.push('<hr>')
      continue
    }
    
    // 标题
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const content = processInline(headingMatch[2])
      result.push(`<h${level}>${content}</h${level}>`)
      continue
    }
    
    // 引用块
    if (isBlockquote) {
      if (!inBlockquote) {
        result.push('<blockquote>')
        inBlockquote = true
      }
      const content = processInline(line.replace(/^>\s?/, ''))
      result.push(`<p>${content}</p>`)
      continue
    }
    
    // 无序列表
    const ulMatch = line.match(/^\s*[-*]\s+(.+)$/)
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) result.push(`</${listType}>`)
        result.push('<ul>')
        inList = true
        listType = 'ul'
      }
      result.push(`<li>${processInline(ulMatch[1])}</li>`)
      continue
    }
    
    // 有序列表
    const olMatch = line.match(/^\s*\d+\.\s+(.+)$/)
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) result.push(`</${listType}>`)
        result.push('<ol>')
        inList = true
        listType = 'ol'
      }
      result.push(`<li>${processInline(olMatch[1])}</li>`)
      continue
    }
    
    // 空行
    if (line.trim() === '') {
      // 关闭之前的块
      if (inList) {
        result.push(`</${listType}>`)
        inList = false
      }
      if (inBlockquote) {
        result.push('</blockquote>')
        inBlockquote = false
      }
      continue
    }
    
    // 普通段落
    result.push(`<p>${processInline(line)}</p>`)
  }
  
  // 关闭未关闭的块
  if (inList) result.push(`</${listType}>`)
  if (inBlockquote) result.push('</blockquote>')
  
  // 组合结果
  let html = result.join('\n')
  
  // 恢复代码块
  codeBlocks.forEach((block, index) => {
    html = html.replace(`___CODE_BLOCK_${index}___`, block)
  })
  
  // 恢复行内代码
  inlineCodes.forEach((code, index) => {
    html = html.replace(`___INLINE_CODE_${index}___`, code)
  })
  
  return html
}

/**
 * 处理行内格式
 */
function processInline(text: string): string {
  let result = escapeHtml(text)
  
  // 粗体 **text** 或 __text__
  result = result.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  result = result.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  
  // 斜体 *text* 或 _text_
  result = result.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  result = result.replace(/_([^_]+)_/g, '<em>$1</em>')
  
  // 删除线 ~~text~~
  result = result.replace(/~~([^~]+)~~/g, '<del>$1</del>')
  
  // 链接 [text](url)
  result = result.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  )
  
  return result
}

/**
 * HTML 转义
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/**
 * 简单渲染（用于不需要完整解析的场景）
 */
export function renderSimpleMarkdown(text: string): string {
  if (!text) return ''
  
  return text
    // 转义 HTML
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 代码块
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    // 行内代码
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // 粗体
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    // 斜体
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // 链接
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    // 换行
    .replace(/\n/g, '<br>')
}

