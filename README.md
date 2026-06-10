# Windows 微信群聊自动截图取证工具

这是一个半自动截图工具：人工打开并确认目标微信群，脚本只负责连续截图、向上滚动、去重、编号、生成清单和 SHA256 哈希。它不会读取微信数据库、不会破解或绕过权限、不会删除或修改聊天记录。

## 重要提醒

- 截图只是可读副本。请保留原始电脑、手机、微信账号、群聊记录和登录环境，后续诉讼提交前让律师确认是否需要公证或司法鉴定。
- 运行前先手动保存辅助证据：微信账号登录页、目标群信息页、关键对方联系人/群成员身份页。
- 脚本不会自动识别聊天日期。请先把聊天窗口放在要截取的最新位置；看到最早起始日期时，按 `Ctrl+Alt+S` 停止。
- 尽量在取证电脑上停止微信自动清理、不要删消息、不要切换账号、不要修改群名备注。

## 安装

1. 在 Windows 10/11 电脑安装 Python 3.10 或更新版本。
2. 把本文件夹复制到取证电脑。
3. 双击 `SETUP-WINDOWS.bat` 安装依赖。

## 项目结构

- `capture_wechat_group.py`：主程序，负责窗口截图、滚动、去重、清单和哈希。
- `verify_hashes.py`：复验输出目录里的 `sha256sums.txt`。
- `SETUP-WINDOWS.bat`：Windows 一键创建虚拟环境并安装依赖。
- `RUN-WINDOWS.bat`：正式采集入口。
- `RUN-SAMPLE-30.bat`：最多保留 30 张截图的样本入口。
- `RUN-SCROLL-TEST.bat`：只测试一次滚动和重叠估算。
- `RUN-DIAGNOSTICS.bat`：只测试截图后端，排查黑屏。
- `VERIFY-WINDOWS.bat`：Windows 复验哈希入口。
- `requirements.txt` / `pyproject.toml`：依赖和项目元数据。

## 先跑样本

先用非敏感聊天窗口测试：

1. 打开微信桌面版，并打开一个测试群聊。
2. 双击 `RUN-SAMPLE-30.bat`。
3. 按提示输入群名、起始日期、结束日期。
4. 确认脚本选中的窗口无误后，输入 `CAPTURE`。
5. 检查输出目录中的 `captures/`、`manifest.csv`、`run.json`、`sha256sums.txt`。

样本应满足：

- 截图不是黑屏。
- 相邻截图有可见重叠，通常约 15%-25%。
- 文件编号连续。
- `manifest.csv` 中保存截图数量与 `captures/` 里的 PNG 数量一致。

## 如果测试截图是黑屏

先双击 `RUN-DIAGNOSTICS.bat`。它不会滚动，只会对当前微信窗口分别用 4 种截图方式各截一张，结果在输出目录的 `diagnostics/` 里：

- `imagegrab.png`
- `pyautogui.png`
- `mss-full.png`
- `mss-window.png`
- `diagnostics.json`

如果其中某一张是正常的，就用对应方式固定运行，例如：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --end-date 2026-06-10 --capture-method imagegrab
```

从 1.1.0 版开始，默认 `--capture-method auto` 会按 `imagegrab`、`pyautogui`、`mss-full`、`mss-window` 的顺序自动尝试，并保留第一张不是黑屏的结果。

如果 4 张全黑，按这个顺序排查：

1. 确认微信窗口没有最小化，且没有被其他窗口挡住。
2. 把微信移到主显示器，先不要跨屏或放在副屏。
3. 保持 Windows 桌面解锁且可见；不要在断开的远程桌面会话里运行。
4. 在微信设置中关闭硬件加速，然后重启微信再试。
5. 右键命令行或批处理，用管理员身份运行。
6. 仍然全黑时，改用系统截图工具或手机/录屏做补充取证，并咨询律师是否做公证或司法鉴定。

## 正式运行

1. 打开微信桌面版，进入目标微信群。
2. 将聊天窗口放在要截取的最新位置，通常是结束日期或当前最新消息。不要先滚到起始日期。
3. 双击 `RUN-WINDOWS.bat`。
4. 输入：
   - `Group name or identifying text`：群名或能识别窗口的文字。
   - `Start date`：最早要截到的日期，例如 `2026-03-01`。
   - `End date`：结束日期；留空默认运行当天。
   - `Output directory`：证据保存目录；留空自动生成。
   - `Max screenshots`：正式全量可留空或填 `0`。
5. 脚本显示选中的窗口后，确认无误输入 `CAPTURE`。
6. 看到聊天内容滚动到起始日期附近时，按 `Ctrl+Alt+S` 停止。

## 如果没有看到群聊滚动

先确认你不是在运行 `RUN-DIAGNOSTICS.bat`，诊断截图模式本来就不会滚动。

正式截图应从最新消息开始，脚本每截一张后向上滚到更早的消息。不要手动先滚到起始日期，否则会从旧消息开始继续往更旧的位置截，容易漏掉中间和最新内容。

从 1.4.0 版开始，默认滚动模式是 `adaptive`。脚本会小步滚动、截图测量移动幅度，直到相邻截图大约保留 35% 重叠。这个模式比固定滚轮数或 PageUp 更适合不同显示器、DPI 和微信窗口大小。

从 1.5.0 版开始，如果 `RUN-SCROLL-TEST.bat` 已经测出合适步数，正式跑几万条消息时可以使用固定快滚。这样每张图只截一次，不再每一步都截图测量。

例如日志里显示 `step=8` 达到目标，就正式运行：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例工作群" --start-date 2026-03-01 --end-date 2026-06-10 --target-overlap 0.35 --adaptive-fixed-steps 8 --interval 0.2
```

也可以让正式运行第一张自动校准，后面锁定同一步数：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例工作群" --start-date 2026-03-01 --end-date 2026-06-10 --target-overlap 0.35 --adaptive-lock-after-first --interval 0.2
```

如果正式运行时看不到滚动：

1. 双击 `RUN-SCROLL-TEST.bat`，它只做一次“截图、点击聊天区、滚动、再截图”。
2. 打开输出目录的 `scroll-test/before.png` 和 `scroll-test/after.png`，确认聊天内容是否移动。
3. 如果没移动，把微信最大化并移到主显示器，重新运行。
4. 如果默认自适应模式移动太慢，可以加大每次探测步长：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --scroll-test --scroll-x-ratio 0.75 --scroll-y-ratio 0.60 --adaptive-step-clicks 25
```

5. 如果希望相邻截图重叠更多，把目标重叠提高，例如 50%：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --scroll-test --target-overlap 0.50
```

6. 如果自适应模式误判，才退回固定滚轮：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --scroll-test --scroll-mode wheel --scroll-clicks 30 --scroll-bursts 2
```

7. 如果固定滚轮仍太慢，再试 PageUp；PageUp 容易跳太多，正式取证前务必先跑 `--scroll-test`：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --scroll-test --scroll-mode pageup --pageup-presses 1 --scroll-bursts 1
```

如果滚动方向反了，把滚轮值改成负数测试：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --scroll-test --scroll-clicks -30
```

命令行运行示例：

```powershell
.venv\Scripts\python capture_wechat_group.py --group-name "示例结算群" --start-date 2026-03-01 --end-date 2026-06-10 --output-dir D:\wechat-evidence\sample --target-overlap 0.35
```

## 输出文件

- `captures/000001.png` 等：主截图文件。
- `duplicates/`：判定为重复或几乎未变化的截图尝试，保留用于审计。
- `diagnostics/`：仅在运行 `RUN-DIAGNOSTICS.bat` 或 `--diagnose-capture` 时生成。
- `scroll-test/`：仅在运行 `RUN-SCROLL-TEST.bat` 或 `--scroll-test` 时生成。
- `manifest.csv`：每次截图的时间、文件名、窗口坐标、SHA256、是否重复、是否疑似黑屏。
- `run.json`：本次运行参数、机器信息、依赖版本、停止原因。
- `capture.log`：运行日志。
- `sha256sums.txt`：输出目录内证据文件的 SHA256 清单。

## 复验哈希

在同一工具目录双击 `VERIFY-WINDOWS.bat`，输入证据输出目录。也可以命令行运行：

```powershell
.venv\Scripts\python verify_hashes.py D:\wechat-evidence\moha
```

显示 `OK` 表示清单中的文件未被改动。

## 常见问题

- 如果脚本选错窗口：退出后重新打开目标群窗口，并让该窗口保持在最前，再运行。
- 如果没有滚动到聊天区：调整参数 `--scroll-x-ratio` 和 `--scroll-y-ratio`，默认鼠标停在窗口右侧聊天内容区域。
- 如果截图黑屏：确认微信窗口没有最小化、没有被其他窗口遮挡，必要时用管理员身份运行命令行。
- 如果 `Ctrl+Alt+S` 不生效：点击命令行窗口按 `Ctrl+C` 停止；或先确认依赖 `keyboard` 已安装。
- 如果截图变化很少就停止：增加 `--stable-limit`，例如 `--stable-limit 20`；如果确实滚动到最早消息，停止是正常的。

## 诉讼材料建议

这个工具解决的是快速保存和整理问题，不替代律师、公证或司法鉴定流程。提交前建议至少保留：

- 原始设备和账号可现场展示。
- 原始输出目录的完整副本。
- `manifest.csv`、`run.json`、`sha256sums.txt`。
- 运行当天的操作者、设备、账号、群聊身份说明。
- 与结算争议直接相关的截图页码或文件编号索引。
