# Integration Smoke Notes

## Runtime Restart Real Preview Smoke

- Test file: `tests/integration/test_runtime_restart_real_preview_smoke.py`
- Purpose: verify real preview lifecycle flow `start_dev_session -> dawnchat.ui.runtime.restart -> operations polling -> completed`
- Target plugin: `com.dawnchat.desktop-ai-assistant`

## How To Run

- Default mode (safe): test is skipped unless explicitly enabled
  - `./dev.sh --pytest-file tests/integration/test_runtime_restart_real_preview_smoke.py`
- Real mode:
  - `DAWNCHAT_RUN_REAL_PLUGIN_SMOKE=1 ./dev.sh --pytest-file tests/integration/test_runtime_restart_real_preview_smoke.py`

## Expected Result

- Without env var: `SKIPPED` is expected.
- With env var:
  - test should start a real preview session
  - assert `dawnchat.ui.runtime.info` contains `python_sidecar.state=running` and sidecar endpoint port
  - verify python MCP proxy `tools/list` includes `assistant.python.echo`
  - verify python MCP proxy `tools/call` can invoke `assistant.python.echo`
  - invoke MCP `dawnchat.ui.runtime.restart`
  - receive `task_id` and poll lifecycle operation until `completed`
  - re-check python sidecar runtime + MCP availability after restart
  - stop preview session in `finally` cleanup

## Troubleshooting

- Plugin not found:
  - ensure `desktop-ai-assistant` exists in current plugin registry and can be loaded.
- Timeout during polling:
  - inspect plugin lifecycle task payload via `/api/plugins/operations/{task_id}`.
  - inspect plugin preview/runtime logs before rerun.
- Python MCP proxy call failed:
  - verify `runtime.info` has `python_sidecar.state=running`.
  - verify sidecar endpoint route `/api/opencode/mcp/plugin/{plugin_id}/python` is registered.
  - inspect sidecar startup logs under plugin preview log session.
- Preview start failure:
  - verify Bun sidecar path and local dependency installation status.
