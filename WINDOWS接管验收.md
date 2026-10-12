# Windows 接管验收（2026-10-13）

本机负责 Xunpan 和 ataous 夜间任务。旧 Mac 已停用；本轮没有安装或启用任何定时任务，没有发送询盘、调用遨虾搜索、推网站、部署、推 GitHub 或合并 main。代码在本地 windows-port 分支。

## 文件和路径

- 普通交接包：E:\CodexP\_交接\Xunpan_迁移交接_20261012，SHA256SUMS 的 4,026 项全部一致。
- 主程序：E:\CodexP\Xunpan，基于 main@4c76409。
- 夜间站点专用副本：E:\CodexP\06_VibeCoding\ataous\ataous-site-night；既有 E:\CodexP\06_VibeCoding\ataous-site 未修改。
- C:\Users\张\ClaudeP → E:\CodexP 目录联接已建立。
- 三个程序模块已放到 04_工具；夜间供应商证据和未跟踪日志已复制，2,622 个目标文件 SHA-256 与交接源一致。
- 运行缓存已复制，Mac state.json 已删除。watch_state.json、last_send.txt 与交接源哈希一致。
- 三个凭据文件由用户本人解密到用户目录，均存在；未打印、复制到仓库或提交任何凭据。Cloudflare OAuth 登录状态也在仓库外。

## 适配内容

| 文件 | 改动 |
|---|---|
| tools/lib/base.py、tools/lib/port.py | Windows msvcrt 跨进程锁；外部动作默认关闭；北京时间和至少60秒间隔保留；Codex调用与独立stderr |
| tools/browser/neo_bridge.mjs | 本机 BrowserOS neo MCP 连接；保留job.json→脚本.out.json；标签归属和暂停状态 |
| tools/browser/send_neo.mjs | neo快照引用、整段插入文本、收件人/内容/未误发核对、发后必须仅多1条；不用Enter/Shift+Enter |
| tools/补资料/每日.py | Python每日入口；默认显示计划；自动运行需另获授权；BZ0097未核实前不自动补发 |
| tools/夜间/夜间.py | Python夜间入口；搜索/审图/核SKU/保护核对/检查分步；发布需独立--publish及授权 |
| tools/拉记录.py | npx.cmd；UTF-8；临时分片放temp并自动清理 |
| tools/export_review_result.py | --dry纯只读试算；不默认提交推送；本地导出及推送单独授权 |
| tools/run.py、tools/push_review_feed.py、tools/夜间/找货源.py | 发送、复核推送、付费搜索增加关闭状态检查；发送断线不自动重试 |
| tools/build_review_feed.py、tools/cmp.py、tools/review_triage.py | 默认读夜间网站副本，避免缺少平时副本 |
| tools/*.py、tools/核SKU/*.py、tools/补资料/*.py、tools/夜间/找货源.py | 文本文件与文本子进程显式UTF-8，避免Windows中文乱码 |
| tools/windows_pending_chats.json | 从交接03文档第3节生成的39家读取范围；不包含聊天正文 |
| .gitignore | 排除.env、Python缓存、批次运行日志 |
| tests/test_windows_port.py、tests/send_neo.test.mjs | Windows锁、授权门、默认入口和发送核对的离线测试 |

Mac原zsh入口与ego浏览器源码保留。Python入口是Windows新入口，并未注册到任务计划程序。

## 验收

| 项目 | 实际结果 |
|---|---|
| 交接校验、完整阅读 | 00～06、MACMINI主控说明、README第五节已读；校验通过 |
| 环境 | Node 24.14.0、Python 3.12.5、Pillow 11.3.0、Codex CLI 0.146.0；Git全局三项配置已设置 |
| 仓库身份与权限 | 两个新仓库已设仓库级提交身份；GitHub只读API确认两个仓库push权限均为true，未实际推送 |
| Codex AI | 复用ChatGPT登录；exec --ignore-user-config空任务实际返回OK；桌面配置未改；未调用Anthropic API |
| neo接口 | 空白页job→probe.out.json测试通过；1688首页呈现登录后的经营档案、采购车、订单入口 |
| 网站复核接口 | export_review_result.py --dry：9022条；仅列预计变化，未写批次文件或推送 |
| 遨虾 | 本地签名生成成功，只输出布尔值；没有发搜索或扣积分 |
| Cloudflare | 用户在neo完成OAuth；whoami确认包含f451a19a目标账户；16个R2分片成功读取，共720款 |
| 当前建队列试算 | 基于刚读回的720款：待核对334、缺资料277、待跑51、重跑6；预计新排3、改不用发4、待发合计348。--dry没有修改队列 |
| 批次保护 | 原队列60/102/479条与交接一致；git diff -- batches为空；未把试算数当成已写队列 |
| Windows离线测试 | Python 6项、Node 5项通过；含跨进程竞争锁和发送错误路径。发送测试使用模拟页面，没有联系真实商家 |
| 网站副本 | npm test：117项通过；npm run check：dry-run成功，未上线；副本无跟踪文件修改 |
| 自动任务 | Windows任务计划程序未发现Xunpan/ataous询盘任务；默认授权automatic=false |
| chat.py实机 | 用户授权BZ0024；首次返回验证/风控，用户说继续后仍同样返回，均立即停。没有成功取得新聊天内容、没有发送、没有推网站。已改进隐藏iframe误判逻辑，但尚未恢复后复验 |
| 飞书通知 | 未发送。用户限定本轮无副作用验收，通知是外部消息，不以交接文档测试要求越过该限制 |

## 未完成的验收和决定

1. 1688聊天读取仍待验收：浏览器暂停状态在用户目录.cache/xunpan/neo_paused.json。用户处理页面并明确继续后，只恢复指定聊天验收，不启用自动任务。当前仅批准BZ0024；39家未处理回复与BZ0097断点均保留。
2. 所有真实发送、图片上传、付费搜索、报价回写、Git推送、线上发布均未实测，不能视为完整生产流程已验收。
3. 飞书测试须用户明确批准发一条通知后再做；凭据存在不等于通知已送达。
4. gh CLI未安装；Git凭证和仓库权限已验证。夜间若后续发布，没有gh会如实报告构建未确认；恢复发布前需安装gh或改用现有GitHub连接器核验具体SHA。
5. Codex桌面常开并不自动启动任务。本机已验证codex exec可供Python入口调用；任务调度、恢复自动运行、分支推送和合并main仍等用户批准。
6. npm ci显示锁定依赖有4项high告警；本轮未升级或强制修复依赖，以保持网站版本一致。

外部动作开关保存在仓库外.cache/xunpan/windows_permissions.json，默认关闭。本轮只放行了BZ0024的读取名单；程序或AI不得自行放宽开关。完整上线前还需按上述待验收项分步检查。

Codex调用方式依据官方文档：https://developers.openai.com/codex/noninteractive 。
