export interface InspectorPosition {
  line: number
  column: number
}

export interface InspectorRange {
  start: InspectorPosition
  end?: InspectorPosition
}

export interface InspectorSelectPayload {
  type: 'DAWNCHAT_INSPECTOR_SELECT'
  pluginId: string
  file: string
  fileRelative?: string
  range: InspectorRange
  selector?: string
  textSnippet?: string
  htmlSnippet?: string
  ts: number
}
