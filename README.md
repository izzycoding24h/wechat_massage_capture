# Windows 微信聊天自动截图取证工具

这是一个半自动截图工具：人工打开并确认目标微信单聊或群聊窗口，脚本只负责连续截图、向上滚动、去重、编号、生成清单和 SHA256 哈希。它不会读取微信数据库、不会破解或绕过权限、不会删除或修改聊天记录。

## 重要提醒

- 截图只是可读副本。请保留原始电脑、手机、微信账号、群聊记录和登录环境，后续诉讼提交前让律师确认是否需要公证或司法鉴定。
- 运行前先手动保存辅助证据：微信账号登录页、目标聊天信息页、关键对方联系人/群成员身份页。
- 脚本不会自动识别聊天日期。请先把聊天窗口单独弹出，并放在要截取的最新位置；看到最早起始日期时，按 `Ctrl+Alt+S` 停止。
- 尽量在取证电脑上停止微信自动清理、不要删消息、不要切换账号、不要修改聊天备注。

## 普通用户安装

普通用户不需要安装 Python，也不需要运行 `SETUP-WINDOWS.bat`。请在一台网络正常的构建电脑上先完成打包，然后把安装包发给用户。

推荐分发文件：

```text
installer-output\WechatMessageCaptureSetup-1.5.0.exe
```

这个安装包会包含 Python 运行时和项目依赖，用户只需要双击安装并启动 `微信截图取证工具`。

如果暂时不做安装包，也可以把下面整个目录压缩发给用户：

```text
dist\WechatMessageCapture\
```

用户解压后双击：

```text
WechatMessageCapture.exe
```

## 源码安装

1. 在 Windows 10/11 电脑安装 Python 3.10 或更新版本。
2. 把本文件夹复制到取证电脑。
3. 双击 `SETUP-WINDOWS.bat` 安装依赖。

## 推荐：桌面应用

源码运行桌面版：

1. 双击 `SETUP-WINDOWS.bat` 安装依赖。
2. 双击 `RUN-DESKTOP.bat` 打开桌面应用。
3. 先阅读 `首页`，确认工具用途、三步流程和停止规则。
4. 在微信聊天列表中双击目标单聊或群聊，让聊天窗口单独弹出。这个步骤很重要，如果只在微信主窗口左侧聊天列表中打开，程序可能无法正确捕捉和滚动。
5. 在 `第一步 准备` 页面输入聊天窗口名、起止日期和总保存位置。
6. 在 `第二步 测试校准` 页面调整 `重叠比例`、`固定步数`、`每步滚轮力度`、`截图间隔（单位：秒）`，先运行测试校准。
7. 确认 before/after 两张图之间有足够重复聊天内容后，点击 `保存当前配置`。界面里的移动百分比只是图像估算参考，微信聊天里的空白、头像和固定区域可能让它偏低。
8. 在 `第三步 正式采集` 页面确认 `至少保留磁盘空间（GB）`，默认保留 `10 GB`，然后点击 `开始正式采集`。

不同显示器宽高、DPI、微信窗口大小都会影响滚动幅度。正式采集前必须先做测试校准，否则可能出现相邻截图重叠不足、内容遗漏或截图效果不好。

正式采集时微信窗口会反复置前、点击和滚动，所以不要依赖鼠标切回桌面应用停止。主停止方式是全局快捷键：

```text
Ctrl+Alt+S
```

看到聊天内容滚动到起始日期附近时，按 `Ctrl+Alt+S` 停止。界面里的 `辅助停止` 按钮只是兜底。

按下 `Ctrl+Alt+S` 后不会瞬间停在当前画面，程序会完成当前轮截图或滚动动作，然后写入运行记录后结束。
桌面应用收到快捷键后，会在界面顶部提示“正在结束中”。

正式采集会持续检查保存位置所在磁盘的剩余空间。低于 `至少保留磁盘空间（GB）` 时会自动结束，已经保存的截图仍保留在本次运行文件夹中。测试校准后显示的“约 X MB/张”和“还能保存约 N 张”只是参考，单张截图大小会随聊天内容、图片、表情和窗口大小变化。

桌面版默认值：

- `结束日期`：运行当天。
- `起始日期`：运行当天往前推 3 个自然月，例如 `2026-06-10` 默认 `2026-03-10`。
- `重叠比例`：`35%`。
- `固定步数`：`8`。
- `每步滚轮力度`：`100`。
- `截图间隔（单位：秒）`：`0.2`。
- `至少保留磁盘空间（GB）`：`10`。

Windows 打包，在构建电脑上执行一次即可：

1. 在 Windows 上运行 `build_windows.ps1`，生成 `dist\WechatMessageCapture\WechatMessageCapture.exe`。脚本默认使用清华 PyPI 镜像，避免 PySide6 下载过慢。
2. 安装 Inno Setup。
3. 打开 `installer\WechatMessageCapture.iss` 并编译，生成安装包。

如果下载依然很慢，可以换镜像：

```powershell
.\build_windows.ps1 -PipIndexUrl https://mirrors.aliyun.com/pypi/simple/
```

如果你明确想使用官方 PyPI：

```powershell
.\build_windows.ps1 -NoMirror
```

`PySide6` 依赖较大，尤其是 `pyside6_addons`。这只需要在构建电脑下载一次；打包后的安装包会包含 Python 运行时和依赖，普通用户不需要下载。

## 项目结构

- `capture_wechat_group.py`：主程序，负责窗口截图、滚动、去重、清单和哈希。
- `capture_core.py`：桌面版和 CLI 共用的采集核心服务。
- `desktop_app.py`：PySide6 桌面应用入口。
- `verify_hashes.py`：命令行兼容工具，用于高级复验 `运行记录/sha256sums.txt`。
- `SETUP-WINDOWS.bat`：Windows 一键创建虚拟环境并安装依赖。
- `RUN-DESKTOP.bat`：源码环境下启动桌面应用。
- `RUN-WINDOWS.bat`：正式采集入口。
- `RUN-SAMPLE-30.bat`：最多保留 30 张截图的样本入口。
- `RUN-SCROLL-TEST.bat`：只测试一次滚动和重叠估算。
- `RUN-DIAGNOSTICS.bat`：只测试截图后端，排查黑屏。
- `VERIFY-WINDOWS.bat`：Windows 命令行兼容复验入口，不属于桌面应用主流程。
- `build_windows.ps1`：PyInstaller 打包脚本。
- `installer/WechatMessageCapture.iss`：Inno Setup 安装包脚本。
- `requirements.txt` / `pyproject.toml`：依赖和项目元数据。

## 先跑样本

先用非敏感聊天窗口测试：

1. 打开微信桌面版，并打开一个测试群聊。
2. 双击 `RUN-SAMPLE-30.bat`。
3. 按提示输入聊天窗口名、起始日期、结束日期。
4. 确认脚本选中的窗口无误后，输入 `CAPTURE`。
5. 检查本次运行文件夹中的 `截图/` 和 `运行记录/`。

样本应满足：

- 截图不是黑屏。
- 相邻截图有可见重叠，通常约 15%-25%。
- 截图文件编号连续。
- `运行记录/manifest.csv` 中保存截图数量与 `截图/` 里的 PNG 数量一致。

## 如果测试截图是黑屏

先双击 `RUN-DIAGNOSTICS.bat`。它不会滚动，只会对当前微信窗口分别用 4 种截图方式各截一张，结果在本次运行文件夹的 `诊断图片/` 子目录里，诊断图片文件名形如 `诊断图片_20260610_2130_imagegrab.png`：

- `诊断图片_YYYYMMDD_HHMM_imagegrab.png`
- `诊断图片_YYYYMMDD_HHMM_pyautogui.png`
- `诊断图片_YYYYMMDD_HHMM_mss-full.png`
- `诊断图片_YYYYMMDD_HHMM_mss-window.png`
- `运行记录/diagnostics.json`

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

1. 打开微信桌面版，找到目标单聊或群聊。
2. 在微信聊天列表中双击目标单聊或群聊，让聊天窗口单独弹出。不要只停留在微信主窗口的聊天列表视图。
3. 将聊天窗口放在要截取的最新位置，通常是结束日期或当前最新消息。不要先滚到起始日期。
4. 双击 `RUN-WINDOWS.bat`。
5. 输入：
   - `Group name or identifying text`：聊天窗口名，或能识别这个单独聊天窗口标题的文字。
   - `Start date`：最早要截到的日期，例如 `2026-03-01`。
   - `End date`：结束日期；留空默认运行当天。
   - `Output directory`：证据保存目录；留空自动生成。
   - `Max screenshots`：正式全量可留空或填 `0`。
6. 脚本显示选中的窗口后，确认无误输入 `CAPTURE`。
7. 看到聊天内容滚动到起始日期附近时，按 `Ctrl+Alt+S` 停止。

## 如果没有看到聊天内容滚动

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
2. 打开本次运行文件夹的 `测试校准图片/before.png` 和 `测试校准图片/after.png`，确认聊天内容是否移动。
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

用户选择的是“总保存位置”。每次运行都会在里面自动新建一个文件夹，例如：

```text
正式采集_20260610_234612
测试校准_20260610_233700
截图诊断_20260610_224500
```

本次运行文件夹里优先看这些内容：

- `截图/000001.png` 等：正式采集保存的聊天截图。
- `测试校准图片/before.png` 和 `测试校准图片/after.png`：测试校准时生成。
- `诊断图片/诊断图片_YYYYMMDD_HHMM_imagegrab.png` 等：截图诊断时生成。
- `运行记录/`：给后续核对使用的技术记录，普通用户不用打开。

`运行记录/` 里包含：

- `manifest.csv`：每次截图的时间、文件名、窗口坐标、SHA256、是否重复、是否疑似黑屏。
- `run.json`：本次运行参数、机器信息、依赖版本、停止原因。
- `run.json` 也会记录本次设置的最低保留空间、开始时可用空间和结束时可用空间。
- `capture.log`：运行日志。
- `sha256sums.txt`：本次运行文件夹内证据文件的 SHA256 清单。
- `重复截图/`：判定为重复或几乎未变化的截图尝试，仅用于审计。

## 命令行兼容工具

桌面应用主流程不需要手动做哈希检查。采集完成后仍会在 `运行记录/sha256sums.txt` 自动生成哈希清单；高级用户或排查问题时，可以在同一工具目录双击 `VERIFY-WINDOWS.bat`，输入本次运行文件夹。也可以命令行运行：

```powershell
.venv\Scripts\python verify_hashes.py D:\wechat-evidence\moha
```

显示 `OK` 表示清单中的文件未被改动。

## 常见问题

- 如果脚本选错窗口：退出后从微信聊天列表中双击目标单聊或群聊，让它单独弹出，并让该窗口保持在最前，再运行。
- 如果没有滚动到聊天区：调整参数 `--scroll-x-ratio` 和 `--scroll-y-ratio`，默认鼠标停在窗口右侧聊天内容区域。
- 如果截图黑屏：确认微信窗口没有最小化、没有被其他窗口遮挡，必要时用管理员身份运行命令行。
- 如果 `Ctrl+Alt+S` 不生效：点击命令行窗口按 `Ctrl+C` 停止；或先确认依赖 `keyboard` 已安装。
- 如果截图变化很少就停止：增加 `--stable-limit`，例如 `--stable-limit 20`；如果确实滚动到最早消息，停止是正常的。

## 诉讼材料建议

这个工具解决的是快速保存和整理问题，不替代律师、公证或司法鉴定流程。提交前建议至少保留：

- 原始设备和账号可现场展示。
- 本次运行文件夹的完整副本。
- `运行记录/manifest.csv`、`运行记录/run.json`、`运行记录/sha256sums.txt`。
- 运行当天的操作者、设备、账号、群聊身份说明。
- 与结算争议直接相关的截图页码或文件编号索引。
