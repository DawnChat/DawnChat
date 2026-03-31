# dev.sh 模块化说明

本目录用于承载 `dev.sh` 的内部实现模块，`dev.sh` 仍是唯一对外入口。

## 目标

- 保持 `./dev.sh` 命令与参数行为不变
- 降低单文件复杂度，按职责拆分实现
- 支持后续增量重构与回归验证

## 模块职责

- `common.sh`
  - 颜色常量、日志输出、通用小工具（如 `mask_url`）
- `args.sh`
  - 参数解析与参数默认值处理（如 `parse_dev_args`、`apply_dev_arg_defaults`）
- `runtime.sh`
  - dev runtime 目录选择、PBS 准备、bun/uv/opencode 准备与解析
- `deps.sh`
  - 前端依赖安装、PBS Python 依赖安装、Python 选择、环境变量设置
- `sync.sh`
  - 后端源码同步、SDK 同步、内置模板同步、`--sync` 主流程
- `tests.sh`
  - pytest / vitest / e2e / e2e-mock / test-all 的测试编排
- `services.sh`
  - 端口清理、进程清理、后端与前端启动、退出信号清理

## 加载顺序

`dev.sh` 中按以下顺序 `source`：

1. `common.sh`
2. `args.sh`
3. `runtime.sh`
4. `deps.sh`
5. `sync.sh`
6. `tests.sh`
7. `services.sh`

该顺序用于保证函数依赖可用，调整顺序前需先检查调用关系。

## 维护约定

- 不要改变 `dev.sh` 对外参数与默认行为
- 新增函数优先放入对应职责模块，不再回填到 `dev.sh`
- 跨模块共享能力放在 `common.sh`
- 模块内函数命名保持语义化，避免重复职责

## 回归建议

修改模块后，至少执行以下命令：

```bash
bash -n dev.sh
bash -n scripts/dev/*.sh
./dev.sh --help
./dev.sh --sync
./dev.sh --pytest-file tests/integration/test_runtime_restart_real_preview_smoke.py -- -q
```

## 本地登录桥联调检查

可在已启动本地前端和 DawnChatWeb 后执行：

```bash
./dev.sh --with-web-auth --check-web-auth-flow
```

该检查会验证：
- 本地回调地址 `http://localhost:5173/auth/callback` 可访问
- 本地登录桥地址 `http://localhost:5174/desktop-auth/bridge` 可访问
- 桥接 query 参数可被页面正确接收（200 响应）
