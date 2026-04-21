安装与快速开始
安装
macOS / bLinux（window： Git Bash / MSYS / WSL 里运行）
curl -fsSL https://codemaker.netease.com/package/codemaker-cli/install | bash
Linux用户如果遇到安装错误 `codemaker_install.sh: line 509: syntax error: unexpected end of file` 需要增加指定LANG再执行
export LANG=zh_CN.UTF-8
curl -fsSL https://codemaker.netease.com/package/codemaker-cli/install | bash
Windows 用户安装方式
PowerShell 中运行：
irm https://codemaker.netease.com/package/codemaker-cli/install.ps1 | iex
CMD 中运行：
powershell -Command "irm https://codemaker.netease.com/package/codemaker-cli/install.ps1 | iex"
oh-my-opencode（omo）安装（mac下，window暂时不稳定）
建议在claude-opus-4-5下输入安装prompt，原本安装过也建议重新执行一遍当前命令

按照以下说明安装和配置 oh-my-opencode:https://codemaker.netease.com/package/codemaker-cli/omo.md
如果原本下载过omo但是提示报错

可以把以下prompt给codemaker执行, 模型可以自行配置 （具体模型可以看1.5 model list）
Verify Setup

The netease-codemaker model list is:['netease-codemaker/claude-opus-4-6', 'netease-codemaker/claude-sonnet-4-5-20250929', 'netease-codemaker/claude-haiku-4-5-20251001', 'netease-codemaker/gpt-5.2-codex-2026-01-14', 'netease-codemaker/gpt-5.2-2025-12-11'，'netease-codemaker/kimi-k2.5']
```bash
cat ~/.config/codemaker/codemaker.json  
```

```bash
cat ~/.config/opencode/oh-my-opencode.json #Configure agent models must based on netease-codemaker
```
Recommended Agent → Model Mapping 
| Agent | Recommended Model | Rationale |
|------|--------------------|-----------|
| Sisyphus | netease-codemaker/claude-opus-4-5-20251101 | Best orchestration + reliability |
| Atlas | netease-codemaker/kimi-k2.5 | Cost‑efficient orchestrator |
| Prometheus | netease-codemaker/claude-opus-4-5-20251101 | Best planning quality |
| Metis | netease-codemaker/claude-opus-4-5-20251101 | Strong gap detection |
| Momus | netease-codemaker/gpt-5.2-2025-12-11 | Strict plan review |
| Oracle | netease-codemaker/gpt-5.2-2025-12-11 | Debugging + architecture reasoning |
| Hephaestus | netease-codemaker/gpt-5.2-codex-2026-01-14 | Best deep coding |
| Librarian | netease-codemaker/kimi-k2.5 | Cheap + good for doc search |
| Explore | netease-codemaker/claude-haiku-4-5-20251001 | Fast + cheapest for grep |
| Multimodal‑Looker | netease-codemaker/claude-haiku-4-5-20251001 | Fallback without Gemini |
| Sisyphus‑Junior | netease-codemaker/kimi-k2.5 | Cheap executor for delegated tasks |
也可以直接手动更新 ~/.config/opencode/oh-my-opencode.json
{
  "$schema": "https://raw.githubusercontent.com/code-yeongyu/oh-my-opencode/master/assets/oh-my-opencode.schema.json",
  "agents": {
    "sisyphus": {
      "model": "netease-codemaker/claude-opus-4-6"
    },
    "oracle": {
      "model": "netease-codemaker/gpt-5.2-2025-12-11"
    },
    "librarian": {
      "model": "netease-codemaker/kimi-k2.5"
    },
    "explore": {
      "model": "netease-codemaker/claude-haiku-4-5-20251001"
    },
    "multimodal-looker": {
      "model": "netease-codemaker/claude-haiku-4-5-20251001"
    },
    "prometheus": {
      "model": "netease-codemaker/claude-opus-4-6"
    },
    "metis": {
      "model": "netease-codemaker/claude-opus-4-6"
    },
    "momus": {
      "model": "netease-codemaker/gpt-5.2-2025-12-11"
    },
    "atlas": {
      "model": "netease-codemaker/kimi-k2.5"
    },
    "hephaestus": {
      "model": "netease-codemaker/gpt-5.2-codex-2026-01-14"
    },
    "sisyphus-junior": {
      "model": "netease-codemaker/kimi-k2.5"
    }
  },
  "categories": {
    "visual-engineering": {
      "model": "netease-codemaker/claude-sonnet-4-5-20250929"
    },
    "ultrabrain": {
      "model": "netease-codemaker/claude-opus-4-6"
    },
    "artistry": {
      "model": "netease-codemaker/claude-opus-4-6"
    },
    "quick": {
      "model": "netease-codemaker/kimi-k2.5"
    },
    "unspecified-low": {
      "model": "netease-codemaker/kimi-k2.5"
    },
    "unspecified-high": {
      "model": "netease-codemaker/claude-sonnet-4-5-20250929"
    },
    "writing": {
      "model": "netease-codemaker/claude-sonnet-4-5-20250929"
    },
    "deep": {
      "model": "netease-codemaker/gpt-5.2-codex-2026-01-14"
    }
  }
}

 复用speckit或openspec
# speckit可以在当前项目下终端执行
specify init . --force --ai opencode --ignore-agent-tools
然后在codemake cli里就有对应命令了


# openspec同理 选择opencode
openspec init




当前支持的model list（持续更新ing）
#claude系列
"claude-sonnet-4-6"
"claude-opus-4-6"
"claude-opus-4-5-20251101"
"claude-sonnet-4-5-20250929"
"claude-haiku-4-5-20251001"

#google系列
"gemini-3.1-pro"  
"gemini-3.1-flash-lite-preview" （新上）
"gemini-3.1-pro-customtools"（已下线）
"Gemini-3.1-Pro-AAA"（新上）

#openai系列
"gpt-5.2-2025-12-11"
"gpt-5.2-codex-2026-01-14"
"gpt-5.3-codex-2026-02-24" 
"gpt-5.4-2026-03-05" 
"gpt-5.4-pro-2026-03-05" 


#国产模型
"qwen3.5-plus"
"qwen3.6-plus"（新上）
"MiniMax-M2.5"
"MiniMax-M2.7"（新上）
"kimi-k2.5"
"glm-5"
"glm-5-turbo"
"glm-5v-turbo"（新上）
"glm-5.1"（新上）
"deepseek-v3.2-latest"
"deepseek-v3.1-latest"

#私有部署模型
"deepseek-v3.2-chat-yd-251201"
"deepseek-v3.2-reasoner-yd-251201"
"deepseek-v3.1-chat-yd-250821"
"deepseek-v3.1-reasoner-yd-250821"
"kimi-k2.5-yd"

log位置：~/.local/share/codemaker/log
验证安装
执行 source ~/.zshrc，或新开一个终端
运行 codemaker --version，显示 0.0.3 或以上即表示安装成功
登录与启动
在终端输入 codemaker 启动
进入后执行 /login 命令，选择 netease-codemaker 登录
登录成功后即可正常使用

更新
运行 codemaker upgrade
windows低版本
win需要在git bash下执行 codemaker upgrade(且需要关闭全部codemaker cli)
是在不行可以试试安装命令升级
irm https://codemaker.netease.com/package/codemaker-cli/install.ps1 | iex
退出
ctrl/command + P 选择 Exit the app
卸载
macOS / Linux（window： Git Bash / MSYS / WSL 里运行）
curl -fsSL https://codemaker.netease.com/package/codemaker-cli/uninstall | bash -s -- --force
Windows 用户卸载方式
PowerShell 中运行：
irm https://codemaker.netease.com/package/codemaker-cli/uninstall.ps1 | iex 
CMD 中运行：
powershell -Command "irm https://codemaker.netease.com/package/codemaker-cli/uninstall.ps1 | iex "

7. windows在tui粘贴图片方式
在对应的配置文件目录 %userProfile%\.config\opencode\tui.json 或者 %userProfile%\.config\codemaker\tui.json
如果是使用WSL的话，则配置文件为~/.config/codemaker/tui.json（钱佳楠同学的配置），可以参考自行调整
{
  "keybinds": {
    "terminal_suspend": "none",
    "input_undo": "ctrl+z,ctrl+-,super+z",
    "input_paste": "alt+v"
  }
}
配置好后重新打开codemaker即可使用alt+v 粘贴图片
8. 关闭自动接受
在codemaker.json配置文件里添加字段
"permission": "deny"
https://opencode.ai/docs/zh-cn/permissions/
使用指引
快捷键与指令
可能按键和系统设置有抢占，可以用命令代替
/ or Ctrl+P 唤起命令

输入与会话
输入 @ 后跟文件名可模糊搜索并附加文件
以 ! 开头可直接运行 shell 命令（例如 !ls -la）
使用 /new 开始新的对话
使用 /sessions 列出并继续之前的对话，会话历史会按工作区隔离，进入不同的工作区，查看到的会话历史不一样
在会话中可使用 /netease_share（后续改名codemaker-share） 指令，执行后将生成浏览器可访问的分享链接及内容（可作为会话查看工具使用）；需注意，每次分享仅同步当前会话已存在的信息，后续会话内容更新不会同步至历史分享链接
使用 /compact 进行上下文总结    
使用 /rename 重命名当前会话
使用/export 将会话导出为 Markdown
Agent模式
按 Tab 在 Build 和 Plan 模式之间切换
Plan：做规划和分析设计的Agent，当希望 LLM 分析代码、建议更改或创建计划而不对代码库进行任何实际修改时选用
Build：主Agent，启用了所有工具，授权完全访问文件操作和系统命令的开发工作的标准Agent
在提示词中使用 @agent-name 调用专门的子代理
按 Ctrl+X Right/Left 在父会话和子会话之间循环切换
编辑、撤销与工具体验
使用 /undo 撤销上一条消息和文件更改
使用 /redo 恢复之前撤销的消息和文件更改
使用 /editor 在外部编辑器中编写消息 但是需要先设置 export EDITOR="vim"
使用 /details 切换工具执行详情的可见性
模型、主题与界面
运行 /models 查看并切换可用的 AI 模型
按 F2 快速切换最近使用的模型
使用 /theme 在多个内置主题之间切换
使用 "theme": "system" 匹配终端的颜色
历史与滚动
使用 PageUp/PageDown 浏览对话历史
按 Ctrl+G 或 Home 跳转到对话开头(mac:fn + <-)
按 Ctrl+Alt+G 或 End 跳转到最新消息 (mac:fn + ->)
启用 tui.scroll_acceleration 获得平滑的 macOS 风格滚动
输入框与中断
按 Shift+Enter 或 Ctrl+J 在提示框中添加换行
输入时按 Ctrl+C 清空输入框
按 Escape 停止 AI 响应
按 Ctrl+Z 暂停终端并返回到 shell
配置与项目化
在项目根目录创建 codemaker.json 用于项目特定设置
将设置放在 \\~/.config/codemaker/codemaker.json 用于全局配置
在配置中添加 \\$schema 可在编辑器中获得自动补全
在配置中设置 model 指定默认模型
通过配置中的 keybinds 部分覆盖任意快捷键
将任意快捷键设置为 none 可完全禁用它
在配置的 mcp 部分配置本地或远程 MCP 服务器
使用 \\{env:VAR_NAME\\} 语法在配置中引用环境变量
使用 \\{[file:path\\](file:path\\)} 在配置值中包含文件内容
在配置中使用 instructions 加载额外的规则文件
扩展：命令、代理、工具与插件
在 .codemaker/command/ 中添加 .md 文件定义可复用的自定义提示
在自定义命令中使用 \\$ARGUMENTS、\\$1、\\$2 用于动态输入
在命令中使用反引号注入 shell 输出（例如 git status）
在 .codemaker/agent/ 中添加 .md 文件创建专门的 AI 角色
为每个代理配置 edit、bash 和 webfetch 工具的权限
使用类似 "git \\*": "allow" 的模式进行细粒度 bash 权限控制
设置 "rm -rf \\*": "deny" 阻止破坏性命令
配置 "git push": "ask" 在推送前要求确认
在 .codemaker/tool/ 中创建 .ts 文件定义新的 LLM 工具
在 .codemaker/plugin/ 中添加 .ts 文件用于事件钩子
运行与排障
使用 codemaker run 进行非交互式脚本运行
使用 codemaker run --continue 恢复上一个会话
使用 codemaker run -f file.ts 通过命令行附加文件
使用 --format json 在脚本中获取机器可读输出
运行 codemaker serve 获取无界面的 CodeMaker Serve API 访问
使用 codemaker run --attach 连接到运行中的服务器
运行 codemaker upgrade 更新到最新版本
运行 codemaker auth list 查看所有已配置的提供商
运行 codemaker agent create 进行引导式代理创建
运行 codemaker debug config 排查配置问题
使用 --print-logs 标志在 stderr 中查看详细日志
提交反馈，进入交互式窗口后，输入/feedback，填入反馈内容，点击提交或者ctrl/cmd+enter
查看帐号余额
/codemaker-quota

修改键盘快捷键
快捷键通过 tui.json（或 tui.jsonc，支持注释）配置。
配置文件位置（优先级从低到高）
优先级路径说明1~/.config/codemaker/tui.json全局用户配置2~/.codemaker/tui.json用户目录配置3<项目>/.codemaker/tui.json项目级配置4<项目>/tui.json项目根目录配置
Windows 下 ~ 即 %USERPROFILE%（如 C:\Users\用户名）。
高优先级的配置会覆盖低优先级。只需写入要修改的键，未指定的键保留默认值。
配置格式
// tui.jsonc — 支持注释
{
  "keybinds": {
    "leader": "ctrl+x",
    "input_submit": "return",
    "input_newline": "shift+return,ctrl+return"
  }
}

修饰键
修饰键写法说明Ctrlctrl 或 controlAltalt、option 或 metamacOS 上对应 OptionShiftshiftSupersupermacOS 对应 Cmd，Windows 对应 Win 键Leader<leader>前缀键，先按 leader 再按后续键
特殊键名
return enter escape esc backspace delete del space tab home end pageup pagedown pgup pgdn up down left right f1~`f12`
组合规则
{
  // 单个快捷键
  "session_new": "ctrl+n",

  // 多个快捷键（逗号分隔，任意一个都能触发）
  "app_exit": "ctrl+c,ctrl+d",

  // 使用 Leader 键（先按 ctrl+x，松开，再按 n）
  "session_new": "<leader>n",

  // 禁用快捷键
  "session_share": "none"
}

默认快捷键一览
默认 Leader 键为 Ctrl+X。下表中 <L> 表示 Leader。
应用 / 全局
功能默认快捷键键名退出应用Ctrl+C / Ctrl+D / <L> Qapp_exit打开外部编辑器<L> Eeditor_open切换主题<L> Ttheme_list切换侧边栏<L> Bsidebar_toggle查看状态<L> Sstatus_view挂起终端Ctrl+Zterminal_suspend
会话管理
功能默认快捷键键名新建会话<L> Nsession_new会话列表<L> Lsession_list会话时间线<L> Gsession_timeline导出会话<L> Xsession_export重命名会话Ctrl+Rsession_rename删除会话Ctrl+Dsession_delete中断会话Escapesession_interrupt压缩会话<L> Csession_compact分叉会话无session_fork分享会话无session_share取消分享无session_unshare
会话导航（分支树）
功能默认快捷键键名第一个子会话<L> Downsession_child_first下一个子会话Rightsession_child_cycle上一个子会话Leftsession_child_cycle_reverse父会话Upsession_parent
消息浏览
功能默认快捷键键名向上翻页PageUp / Ctrl+Alt+Bmessages_page_up向下翻页PageDown / Ctrl+Alt+Fmessages_page_down向上滚动一行Ctrl+Alt+Ymessages_line_up向下滚动一行Ctrl+Alt+Emessages_line_down向上半页Ctrl+Alt+Umessages_half_page_up向下半页Ctrl+Alt+Dmessages_half_page_down跳到顶部Ctrl+G / Homemessages_first跳到底部Ctrl+Alt+G / Endmessages_last复制消息<L> Ymessages_copy撤销消息<L> Umessages_undo重做消息<L> Rmessages_redo折叠/展开代码块<L> Hmessages_toggle_conceal
模型 / Agent
功能默认快捷键键名模型列表<L> Mmodel_list切换最近模型F2model_cycle_recent切换最近模型(反向)Shift+F2model_cycle_recent_reverse切换收藏模型无model_cycle_favoriteProvider 列表Ctrl+Amodel_provider_list收藏/取消收藏模型Ctrl+Fmodel_favorite_toggle切换模型变体Ctrl+Tvariant_cycleAgent 列表<L> Aagent_list下一个 AgentTabagent_cycle上一个 AgentShift+Tabagent_cycle_reverse命令列表Ctrl+Pcommand_list
输入框
功能默认快捷键键名提交Returninput_submit换行Shift+Return / Ctrl+Return / Alt+Return / Ctrl+Jinput_newline清空Ctrl+Cinput_clear粘贴Ctrl+Vinput_paste撤销Ctrl+- / Super+Zinput_undo重做Ctrl+. / Super+Shift+Zinput_redo删除整行Ctrl+Shift+Dinput_delete_line删除到行尾Ctrl+Kinput_delete_to_line_end删除到行首Ctrl+Uinput_delete_to_line_start前进一个词Alt+F / Alt+Right / Ctrl+Rightinput_word_forward后退一个词Alt+B / Alt+Left / Ctrl+Leftinput_word_backward删除后一个词Alt+D / Alt+Delete / Ctrl+Deleteinput_delete_word_forward删除前一个词Ctrl+W / Ctrl+Backspace / Alt+Backspaceinput_delete_word_backward行首Ctrl+Ainput_line_home行尾Ctrl+Einput_line_end缓冲区顶部Homeinput_buffer_home缓冲区底部Endinput_buffer_end
历史记录
功能默认快捷键键名上一条历史Uphistory_previous下一条历史Downhistory_next
配置示例
修改 Leader 键为 Ctrl+Space
{
  "keybinds": {
    "leader": "ctrl+space"
  }
}

Vim 风格滚动
{
  "keybinds": {
    "messages_half_page_up": "ctrl+u",
    "messages_half_page_down": "ctrl+d",
    "messages_first": "g",
    "messages_last": "shift+g"
  }
}

用 Ctrl+Enter 提交，Enter 换行
{
  "keybinds": {
    "input_submit": "ctrl+return",
    "input_newline": "return"
  }
}

注意：部分终端可能不支持 Shift+Return。如果换行无效，请检查终端设置或改用 ctrl+return / alt+return。
禁用危险操作
{
  "keybinds": {
    "session_delete": "none",
    "terminal_suspend": "none"
  }
}

注意事项
修改配置后需要重启 CodeMaker 生效
使用 tui.jsonc 格式可以添加注释
同一个快捷键绑定到多个功能时，后生效的配置优先
<leader> 是两步操作：先按 leader 键（默认 Ctrl+X），松开后再按后续键

Skills 
下载命令：/netease-skillhub-find 
codemaker cli完全兼容opencode生态
skills支持目录.codemaker .opencode .claude .agent 能够自动识别去重
Skills：把文档里的 opencode 替换成 codemaker 即可
https://opencode.ai/docs/skills/

MCP使用与配置
mcp
完整兼容原opencode的MCP生态
https://opencode.ai/docs/mcp-servers/
内置AuthToken占位符自动替换
自动注入token（仅限auth token）

MCP 简单配置案例
cat ~/.config/codemaker/codemaker.json
{
  "$schema": "https://api-code-maker.nie.netease.com/main/config/config.json",
  "permission": "allow",
  "mcp": {
    "redmine-mcp-server": {
      "type": "remote",
      "url": "https://mcp.netease.com/servers/redmine-mcp-server/mcp",
      "headers": {
        "X-Access-Token": "{auth:token}",
        "redmine-host": "dap-v4.pm.netease.com"
      }
    }
  }
}
配置文件位置
作用域路径项目级<项目>/.codemaker/codemaker.json 或 <项目>/codemaker.json全局~/.config/codemaker/codemaker.json
Windows 下 ~ 即 %USERPROFILE%。
本地服务器配置
本地服务器通过子进程启动，使用 stdin/stdout 通信。
{
  "mcp": {
    "my-local-server": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-everything"],
      "environment": {
        "API_KEY": "your-key"
      },
      "enabled": true,
      "timeout": 10000
    }
  }
}

字段类型必填说明type"local"是本地服务器commandstring[]是启动命令和参数environmentobject否环境变量enabledboolean否是否启用，默认 truetimeoutnumber否请求超时（毫秒），默认 5000
远程服务器配置
远程服务器通过 HTTP 连接，支持 StreamableHTTP 和 SSE 协议（自动检测）。
{
  "mcp": {
    "my-remote-server": {
      "type": "remote",
      "url": "https://mcp.example.com/sse",
      "headers": {
        "Authorization": "Bearer your-token"
      },
      "enabled": true,
      "timeout": 10000
    }
  }
}

字段类型必填说明type"remote"是远程服务器urlstring是服务器 URLheadersobject否请求头oauthobject / false否OAuth 配置（见下文），设为 false 禁用 OAuth 自动检测enabledboolean否是否启用，默认 truetimeoutnumber否请求超时（毫秒），默认 5000
占位符
配置中支持三种占位符，在加载时自动替换：
{env:变量名} — 环境变量
引用系统环境变量，变量不存在时替换为空字符串。
{
  "mcp": {
    "my-server": {
      "type": "remote",
      "url": "https://mcp.example.com/sse",
      "headers": {
        "Authorization": "Bearer {env:MY_MCP_TOKEN}",
        "X-Project-ID": "{env:PROJECT_ID}"
      }
    }
  }
}

适用于不想把密钥明文写在配置文件中的场景。使用前需确保环境变量已设置：
# Linux/macOS: 加到 ~/.bashrc 或 ~/.zshrc
export MY_MCP_TOKEN="sk-xxx"

# Windows: 设置系统环境变量
setx MY_MCP_TOKEN "sk-xxx"

{file:路径} — 文件内容
将文件内容作为值注入。支持绝对路径、相对路径（相对于配置文件所在目录）和 ~/ 前缀。
{
  "mcp": {
    "my-server": {
      "type": "remote",
      "url": "https://mcp.example.com/sse",
      "headers": {
        "Authorization": "Bearer {file:~/.secrets/mcp-token.txt}"
      }
    }
  }
}

注意：如果某行被 // 注释，该行中的 {file:...} 不会被替换。
{auth:token} / {auth:user} — 互娱Auth认证
自动注入当前登录的网易 CodeMaker 认证信息。适用于连接网易内部 MCP 服务器。
{
  "mcp": {
    "netease-internal-server": {
      "type": "remote",
      "url": "https://internal-mcp.nie.netease.com/sse",
      "headers": {
        "X-Access-Token": "{auth:token}",
        "X-Auth-User": "{auth:user}"
      }
    }
  }
}

这两个占位符会在每次请求时动态解析为当前有效的认证 token 和用户名，token 过期后会自动续期。
占位符总结
占位符解析时机说明{env:VAR}配置加载时环境变量，静态替换{file:path}配置加载时文件内容，静态替换{auth:token}每次请求时网易认证 token，动态解析{auth:user}每次请求时网易认证用户名，动态解析
MCP Hub
MCP Hub 是网易内部的 MCP 服务器市场，可以浏览和一键安装已发布的 MCP 服务器。
在 TUI 中使用
在对话中直接让 AI 搜索和安装 MCP 服务器：
帮我搜索一下 MCP Hub 上有没有数据库相关的 MCP 服务器

AI 会调用内置的 mcphub 工具搜索、查看详情和安装。
内置指令（在TUI内可使用）
 /netease-mcphub-find
安装流程
AI 在 Hub 中搜索匹配的服务器
展示服务器信息（名称、描述、工具列表）
确认安装后，自动写入 codemaker.jsonc 配置
网易内部服务器的认证头（X-Access-Token、X-Auth-User）会自动替换为 {auth:token} 和 {auth:user} 占位符
Hub 支持的操作
操作说明搜索按关键词、分类、标签搜索详情查看服务器的完整描述和工具列表检测测试服务器连通性和工具发现安装自动转换配置并写入文件
CLI 命令
查看 MCP 服务器状态
codemaker mcp list
状态图标含义：
图标状态说明+connected已连接!needs_auth需要 OAuth 认证-disabled已禁用xfailed连接失败~connecting连接中
添加 MCP 配置
codemaker mcp add

交互式引导，依次选择：
作用域（项目级 / 全局）
服务器名称
类型（本地 / 远程）
类型相关配置（命令/URL/OAuth 等）
完整配置示例
{
  "mcp": {
    // 本地服务器：文件系统工具
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
      "enabled": true
    },

    // 远程服务器：带 API Key
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/sse",
      "headers": {
        "X-API-Key": "{env:CONTEXT7_API_KEY}"
      }
    },

    // 远程服务器：OAuth 认证
    "sentry": {
      "type": "remote",
      "url": "https://mcp.sentry.dev/sse"
    },

    // 网易内部服务器：自动注入认证
    "netease-db": {
      "type": "remote",
      "url": "https://internal-mcp.nie.netease.com/db/sse",
      "headers": {
        "X-Access-Token": "{auth:token}",
        "X-Auth-User": "{auth:user}"
      }
    },

    // 禁用的服务器
    "experimental": {
      "type": "remote",
      "url": "https://beta.example.com/mcp",
      "enabled": false
    }
  }
}

注意事项
MCP 服务器在 CodeMaker 启动时自动连接，修改配置后需重启生效
{env:...} 和 {file:...} 在配置加载时替换，之后不会再更新；{auth:...} 在每次请求时动态解析
远程服务器优先尝试 StreamableHTTP 协议，失败后回退到 SSE
本地服务器退出时会自动清理子进程
服务器提供的工具命名格式为 服务器名_工具名，如 sentry_search_issues


服务器/CICD上直接命令行里使用
可在环境变量里指定认证信息
CODEMAKER_AUTH_USER=xxx
CODEMAKER_AUTH_TOKEN=xxx (auth v2 token)
CODEMAKER_AUTH_KEY=xxx
其中user是必填项，需要与token / key的归属用户一致；token/key 为2选1，两者都能实现自动续签，首次传入后，在同一台机器上，后续可以不用再带上
获取个人 auth token / auth key https://console-auth.nie.netease.com/mymessage/myindex
如果是放在公共机器上运行，建议使用项目auth key
项目AuthKey入口（https://console-auth.nie.netease.com/projects/authkeys）
auth key用户文档（https://g.126.fm/01gFuUN）
申请好AuthKey需要发邮件给CodeMaker申请系统帐号积分（https://g.126.fm/00CsOop）
CODEMAKER_AUTH_USER=xxx CODEMAKER_AUTH_TOKEN=xxx codemaker run "hi" -m "netease-codemaker/kimi-k2.5"
或者
CODEMAKER_AUTH_USER=xxx CODEMAKER_AUTH_KEY=xxx codemaker run "hi" -m "netease-codemaker/kimi-k2.5"
启用Web模式，支持“远程”操作（目前未开放）
通过以下命令，可以打开Web模式，然后在浏览器里打开http://127.0.0.1:4096即可在浏览器上使用CodeMaker-CLI
codemaker web
如果需要在其他地方进行远程访问，可以增加--hostname参数，另外，如果需要在远程访问，强烈建议设置Web访问密码，避免别人随意访问你的代码以及控制你的代码，甚至控制你的机器！！！
OPENCODE_SERVER_USERNAME=codemaker OPENCODE_SERVER_PASSWORD=CMniubi2026 codemaker web --hostname 0.0.0.0 --port 4096 
命令行里直接指定模型
codemaker run -m "netease-codemaker/xxx" "$prompt"

如
codemaker run -m "netease-codemaker/kimi-k2.5" "hi"
模型前缀统一为`netease-codemaker`后面是模型的名字，模型的名字可以参考AIGW文档的模型（使用AIGW传参模型代号），目前已基本覆盖AIGW里支持的主流最新模型
CLI-API模式
使用指令
codemaker serve [--port <number>] [--hostname <string>] [--cors <origin>]
如
codemaker serve --port 8666 --hostname 0.0.0.0
 
可以启用服务器模式
访问地址可以获取接口文档
http://<hostname>:<port>/doc
如
http://127.0.0.1:8666/doc

安全建议，增加访问密码

OPENCODE_SERVER_USERNAME=codemaker OPENCODE_SERVER_PASSWORD=CMniubi2026 codemaker web --hostname 0.0.0.0 --port 8666 
AIGW 模型信息
自定义aigw
可以在（codemaker.json）配置文件中自定义aigw
{
  "$schema": "https://api-code-maker.nie.netease.com/main/config/config.json",
  "provider": {
    "netease-codemaker": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "netease-codemaker",
      "models": {
        "gpt-5": {
          "name": "gpt-5"
        },
        "claude-sonnet-4-5-20250929": {
          "name": "claude-sonnet-4.5"
        },
        "claude-opus-4-5-20251101": {
          "name": "Claude-opus-4.5"
        },
        "qwen3-coder-plus-2025-09-23": {
          "name": "qwen3-coder-plus"
        },
        "kimi-k2-0905-preview": {
          "name": "kimi-k2"
        },
        "deepseek-chat-yd": {
          "name": "deepseek-chat-youdao"
        },
        "deepseek-v3.1-latest": {
          "name": "deepseek-v3.1"
        }
      },
      "options": {
        "baseURL": "xxx/v1",
        "apiKey": "xxx"
      }
    }
  },
  "model": "netease-codemaker/claude-sonnet-4-5-20250929",
  "mode": {
    "build": {
      "model": "netease-codemaker/claude-sonnet-4-5-20250929"
    }
  },
  "snapshot": false,
  "mcp": {},
  "permission": "allow",
  "lsp": {}
}

本地估算tokens消耗
/token-usage 
命令使用文档基本用法codemaker token-usage [options]查看 token 消耗统计，支持按模型、日期、会话维度聚合，费用以人民币 (¥) 显示。
参数说明
参数类型默认值说明--viewmodel / date / sessionmodel聚合维度--sinceYYYY-MM-DD当月1号起始日期--untilYYYY-MM-DD无限制结束日期--sessionstring-按 session ID 或标题关键词过滤--formattable / jsontable输出格式
--------------------------------------------------------------------------------
示例
按模型查看（默认）
codemaker token-usage
输出当月每个模型的 token 用量和费用，含单价列 In¥/1M、Out¥/1M：

按日期查看
codemaker token-usage --view date
按会话查看
codemaker token-usage --view session
指定日期范围
codemaker token-usage --since 2025-03-01 --until 2025-03-15
查看某个会话的用量

按 session ID
codemaker token-usage --session ses_abc123

按标题关键词模糊匹配
codemaker token-usage --session "fix compaction"

使用 --session 时会自动取消默认的当月起始日期限制，展示该会话的全部用量。如果匹配不到会话，会列出最近 10 个会话供参考。
输出 JSON 格式
codemaker token-usage --format json
[
  {
    key: netease-codemaker/claude-sonnet-4-5,
    inputTokens: 1234567,
    outputTokens: 56789,
    reasoningTokens: 0,
    cacheRead: 980000,
    cacheWrite: 200000,
    cost: 31.8654
  }
]
列说明
列名含义Input总输入 token=非缓存输入 + Cache Read + Cache WriteOutput输出 tokenReasoning推理 token（部分模型有）Cache R缓存命中读取的 token（已包含在 Input 中）Cache W缓存创建写入的 token（已包含在 Input 中）Cost(¥)人民币费用=Input × 输入单价 + (Output + Reasoning) × 输出单价In¥/1M每百万输入 token 单价（仅 model 视图）Out¥/1M每百万输出 token 单价（仅 model 视图）

自定义 Agent 配置指南
Agent 是具有特定能力、权限和系统提示的 AI 角色。CodeMaker 内置了几个 Agent，用户也可以创建自定义 Agent 来适配特定场景。
Agent 类型：
类型说明使用方式primary主 Agent，可作为会话入口在 Agent 列表中选择，或通过 Tab 切换subagent子 Agent，由主 Agent 派生在输入框中 @agent名 提及，或由 LLM 自动调用all两者兼可以上两种方式均可
内置 Agent
名称类型说明buildprimary默认主 Agent，通用编码planprimary规划模式，先设计方案再执行generalsubagent通用子 Agent，用于并行执行多个任务exploresubagent代码库快速搜索和探索
创建自定义 Agent
方式一：Markdown 文件（推荐）
在以下任意目录下创建 .md 文件，文件名即为 Agent 名称：
目录作用域.codemaker/agent/当前项目.agent/ 或 .agents/当前项目~/.config/codemaker/agent/全局（所有项目）
Windows 下 ~ 即 %USERPROFILE%。
文件使用 YAML frontmatter + Markdown 正文的格式，frontmatter 定义配置，正文作为系统提示（system prompt）。
示例： .codemaker/agent/reviewer.md
---
description: 代码审查专家，专注于发现潜在问题
mode: subagent
model: netease-codemaker/claude-sonnet-4-5
color: "#E67E22"
---

你是一个严格的代码审查专家。

审查时关注以下方面：
- 逻辑正确性和边界条件
- 安全漏洞（注入、XSS 等）
- 性能问题
- 代码可读性

只输出有实际价值的问题，不要吹毛求疵。

方式二：JSON 配置
在 codemaker.jsonc 中配置：
{
  "agent": {
    "reviewer": {
      "description": "代码审查专家",
      "mode": "subagent",
      "model": "netease-codemaker/claude-sonnet-4-5",
      "color": "#E67E22",
      "prompt": "你是一个严格的代码审查专家..."
    }
  }
}

方式三：CLI 命令
codemaker agent create
# 交互式创建，按提示输入 description、mode 等

或指定参数：
codemaker agent create --path .codemaker/agent --description "代码审查专家" --mode subagent

配置字段
基础字段
字段类型说明descriptionstringAgent 描述，用于 LLM 判断何时调用该 Agentmodestring"primary" / "subagent" / "all"，默认 "all"modelstring指定模型，格式 provider/model-id，如 netease-codemaker/claude-sonnet-4-5colorstringUI 显示颜色，格式 #RRGGBBhiddenboolean是否从 @ 自动补全菜单中隐藏disableboolean禁用此 Agent
模型参数
字段类型说明temperaturenumber温度（0-2），值越高输出越随机top_pnumber核采样参数stepsnumber最大 agentic 迭代次数，防止无限循环
权限控制
通过 permission 字段精细控制 Agent 可使用的工具：
---
permission:
  read: allow      # 允许读取文件
  edit: allow      # 允许编辑文件
  bash: deny       # 禁止执行命令
  glob: allow      # 允许文件搜索
  grep: allow      # 允许内容搜索
  webfetch: deny   # 禁止网络请求
---

可用的权限动作：
allow — 直接允许
deny — 直接拒绝
ask — 每次使用前询问用户
支持的工具名：
read edit bash glob grep list webfetch websearch task codesearch todoread todowrite question plan_enter plan_exit
通配符和文件级权限：
---
permission:
  edit:
    "*.env": deny       # 禁止编辑 .env 文件
    "*.test.ts": allow  # 允许编辑测试文件
    "*": ask            # 其他文件需确认
  bash: deny
---

使用 Agent
在 TUI 中
Tab / Shift+Tab — 切换主 Agent
@agent名 — 在输入框中提及子 Agent
<Leader> A — 打开 Agent 列表
在命令行中
# 指定 Agent 启动
codemaker --agent reviewer

# 列出所有可用 Agent
codemaker agent list

LLM 自动调用
对于 subagent 类型的 Agent，LLM 会根据 description 字段自动判断何时调用。编写清晰的 description 是让 Agent 被正确调用的关键。
配置优先级
多个配置来源按以下顺序合并（高优先级覆盖低优先级）：
项目 codemaker.jsonc 中的 agent 配置
项目目录下的 .codemaker/agent/*.md
全局 ~/.config/codemaker/agent/*.md
内置默认 Agent
同名 Agent 会被合并，后者覆盖前者的同名字段。
完整示例
只读分析 Agent
---
description: 只读代码分析，不修改任何文件
mode: subagent
color: "#3498DB"
permission:
  read: allow
  glob: allow
  grep: allow
  edit: deny
  bash: deny
---

你是一个代码分析专家。你只能读取和搜索代码，不能修改任何文件或执行命令。

分析代码时请关注：
- 架构设计和模块依赖
- 潜在的性能瓶颈
- 代码复杂度

文档写作 Agent
---
description: 撰写和维护项目文档
mode: all
model: netease-codemaker/claude-sonnet-4-5
color: "#38A3EE"
permission:
  read: allow
  edit:
    "docs/**": allow
    "*.md": allow
    "*": deny
  bash: deny
---

你是技术文档写作专家。

要求：
- 使用简洁、准确的中文
- 保留所有技术术语的英文原文
- 代码示例需包含注释

测试专员 Agent
---
description: 编写和运行单元测试
mode: subagent
color: "#2ECC71"
permission:
  read: allow
  edit:
    "test/**": allow
    "*.test.ts": allow
    "*": deny
  bash: allow
  glob: allow
  grep: allow
---

你是测试工程师。你只能修改 test 目录下的文件和 *.test.ts 文件。

编写测试时遵循项目规范：
- 使用 Bun 内置测试框架
- 避免 mock，测试真实实现
- 使用 tmpdir() fixture 创建临时目录

覆盖内置 Agent 配置
// codemaker.jsonc
{
  "agent": {
    // 给内置 build agent 指定模型
    "build": {
      "model": "netease-codemaker/claude-sonnet-4-5",
      "temperature": 0.3
    },
    // 给内置 explore agent 增加权限
    "explore": {
      "permission": {
        "bash": "allow"
      }
    }
  }
}

注意事项
description 是 LLM 决定是否调用子 Agent 的依据，写得越清晰调用越准确
内置 Agent（build、plan）不能被禁用或降级为 subagent
model 格式为 provider/model-id，可通过 codemaker models 查看可用模型
Markdown 文件修改后需要重启 CodeMaker 生效
子目录结构会保留在 Agent 名称中，如 agent/team/reviewer.md 的名称为 team/reviewer

对话权限配置
权限系统控制 AI 的每项操作是否需要用户审批。每条权限规则对应以下三种动作之一：
动作说明allow直接执行，无需审批ask每次执行前弹窗询问用户deny直接拒绝，不执行
配置文件位置
权限在 codemaker.jsonc（或 codemaker.json）的 permission 字段中配置。
作用域路径项目级<项目>/.codemaker/codemaker.json 或 <项目>/codemaker.json全局~/.config/codemaker/codemaker.json
Windows 下 ~ 即 %USERPROFILE%。项目级配置优先于全局配置。
基本配置
全局统一设置
一行字符串即可设置所有权限：
{
  // 所有操作无需审批，直接执行
  "permission": "allow"
}

按工具设置
用对象指定各工具的权限，* 作为未列出工具的默认值：
{
  "permission": {
    "*": "ask",       // 默认所有操作需审批
    "read": "allow",  // 读取文件免审批
    "bash": "allow",  // 执行命令免审批
    "edit": "deny"    // 禁止编辑文件
  }
}

细粒度规则（对象语法）
对于支持对象语法的权限，可以按模式匹配设置不同动作。
模式匹配示例
控制 bash 命令：
{
  "permission": {
    "bash": {
      "*": "ask",         // 默认命令需审批
      "git *": "allow",   // git 命令免审批
      "npm *": "allow",   // npm 命令免审批
      "bun *": "allow",   // bun 命令免审批
      "rm *": "deny"      // 禁止删除命令
    }
  }
}

控制文件编辑范围：
{
  "permission": {
    "edit": {
      "*": "deny",                        // 默认禁止编辑
      "src/**": "allow",                  // 允许编辑 src 目录
      "packages/web/src/content/**": "allow"  // 允许编辑文档
    }
  }
}

通配符
通配符含义*匹配零个或多个任意字符?匹配恰好一个任意字符
特殊行为：模式末尾的  *（空格 + 星号）是可选的。例如 "git *" 同时匹配 git 和 git status --porcelain。
匹配优先级
规则按声明顺序评估，最后匹配的规则生效。因此应将通配 * 放在前面，更具体的规则放在后面：
{
  "permission": {
    "bash": {
      "*": "ask",            // 1. 默认询问
      "git *": "allow",      // 2. git 命令放行
      "git push *": "deny"   // 3. 但禁止 push（覆盖上一条）
    }
  }
}

Home 目录展开
模式中可以使用 ~ 或 $HOME 前缀引用用户主目录：
~/projects/* → /Users/用户名/projects/*
$HOME/projects/* → /Users/用户名/projects/*
这在配置 external_directory 规则时特别有用。
可用权限列表
权限匹配目标对象语法说明read文件路径支持读取文件edit文件路径支持所有文件修改（覆盖 edit、write、patch、multiedit 四个工具）globglob 模式支持文件搜索grep正则表达式支持内容搜索list目录路径支持列出目录文件bash解析后的命令支持执行 shell 命令task子 Agent 类型支持启动子 Agentskill技能名称支持加载技能lsp—支持LSP 查询external_directory目录路径支持访问项目外部路径todoread—不支持读取任务列表todowrite—不支持更新任务列表webfetch—不支持抓取 URLwebsearch—不支持网络搜索codesearch—不支持代码搜索doom_loop—不支持重复相同工具调用检测（连续 3 次相同输入触发）
对象语法列标记为"支持"的权限可以用 { "pattern": "action" } 的对象形式配置；标记为"不支持"的只能设为 "allow" / "ask" / "deny" 字符串。
默认值
未配置时，CodeMaker 使用以下默认值：
权限默认值说明大部分权限allow无需审批直接执行doom_loopask检测到重复调用时询问external_directoryask访问项目外路径时询问read（.env 文件）ask保护敏感环境变量
.env 文件的完整默认规则：
{
  "permission": {
    "read": {
      "*": "allow",
      "*.env": "ask",          // .env 文件需确认
      "*.env.*": "ask",        // .env.local 等变体也需确认
      "*.env.example": "allow" // 示例文件可直接读取
    }
  }
}

"询问"（Ask）机制
当权限为 ask 时，UI 会弹出审批提示，提供三个选项：
选项说明once仅批准本次请求always批准本次及后续匹配同一模式的请求（当前会话有效）reject拒绝本次请求
选择 always 时，系统会根据当前操作生成匹配模式（例如 bash 操作会生成 git status* 这样的前缀模式），后续匹配该模式的操作将自动批准，无需再次确认。
外部目录访问
external_directory 控制 AI 能否访问启动 CodeMaker 时所在项目目录之外的路径。这会影响所有涉及路径的工具（read、edit、list、glob、grep、bash 等）。
允许访问特定外部目录
{
  "permission": {
    "external_directory": {
      "~/projects/shared-lib/**": "allow"
    }
  }
}

允许读取但禁止编辑
被 external_directory 放行的路径会继承工作区的默认权限（大部分为 allow）。如果需要更细粒度的控制，可叠加其他权限规则：
{
  "permission": {
    "external_directory": {
      "~/projects/shared-lib/**": "allow"
    },
    // 允许读取外部目录，但禁止编辑
    "edit": {
      "~/projects/shared-lib/**": "deny"
    }
  }
}

Agent 级权限覆盖
每个 Agent 可以覆盖全局权限。Agent 权限与全局配置合并，Agent 规则优先。
JSON 配置
{
  "permission": {
    "bash": {
      "*": "ask",
      "git *": "allow"
    }
  },
  "agent": {
    "build": {
      "permission": {
        "bash": {
          "*": "ask",
          "git *": "allow",
          "git commit *": "ask",  // build agent 的 commit 需确认
          "git push *": "deny"    // build agent 禁止 push
        }
      }
    }
  }
}

Markdown Agent 文件
---
description: 代码审查，不修改文件
mode: subagent
permission:
  edit: deny
  bash:
    "*": ask
    "git diff *": allow
    "grep *": allow
---

只分析代码并提出建议，不做任何修改。

更多 Agent 配置细节见 Agent 配置指南。
完整配置示例
场景一：全自动模式
适合个人项目、快速原型开发：
{
  "permission": "allow"
}

场景二：谨慎模式
默认所有操作需审批，仅放行安全的只读和常用命令：
{
  "permission": {
    "*": "ask",
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "list": "allow",
    "bash": {
      "*": "ask",
      "git status *": "allow",
      "git diff *": "allow",
      "git log *": "allow",
      "bun test *": "allow",
      "bun typecheck *": "allow"
    }
  }
}

场景三：只读分析
禁止所有修改和命令执行，仅允许读取和搜索：
{
  "permission": {
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "list": "allow",
    "edit": "deny",
    "bash": "deny",
    "webfetch": "deny",
    "websearch": "deny"
  }
}

场景四：限制 bash + 保护敏感文件
{
  "permission": {
    "bash": {
      "*": "ask",
      "git *": "allow",
      "npm *": "allow",
      "rm *": "deny",
      "sudo *": "deny"
    },
    "read": {
      "*": "allow",
      "*.env": "deny",
      "*.env.*": "deny",
      "*.pem": "deny",
      "*.key": "deny",
      "*credentials*": "deny"
    },
    "edit": {
      "*": "allow",
      "*.env": "deny",
      "*.lock": "deny",
      "migration/*": "deny"
    }
  }
}

注意事项
规则按声明顺序评估，最后匹配的规则生效，不是最具体的规则生效
edit 权限同时控制 edit、write、patch、multiedit 四个工具
模式末尾的  *（空格 + 星号）是可选匹配，"git *" 能同时匹配 git 和 git status
修改权限配置后需重启 CodeMaker 生效
旧版 tools 布尔配置（"tools": { "bash": false }）已废弃，但仍兼容，建议迁移到 permission

会话管理
会话（Session）是 CodeMaker 中与 AI 对话的基本单元。每个会话包含完整的对话历史、文件变更记录和上下文状态。CodeMaker 提供会话的创建、续接、分支、压缩、分享等功能。
基本操作
创建会话
启动 CodeMaker 时默认创建新会话：
codemaker                         # 新会话
codemaker /path/to/project        # 在指定目录创建新会话

TUI 中按 Ctrl+X, N 创建新会话。
续接会话
codemaker --continue              # 续接最近的会话
codemaker -c                      # 同上（短写）
codemaker --session <id>          # 续接指定 ID 的会话
codemaker -s <id>                 # 同上（短写）

查看会话列表
codemaker session list            # 列出所有根会话
codemaker session list -n 10      # 限制显示数量
codemaker session list --format json  # JSON 格式输出

TUI 中按 Ctrl+X, L 或者输入 /sessions 打开会话列表，支持搜索过滤。
重命名会话
TUI 中按 Ctrl+R 重命名当前会话。
删除会话
在会话列表中按 Ctrl+D 删除选中的会话。删除操作会级联移除所有子会话和相关数据。
会话分支（Fork）
从会话的任意消息位置创建分支，保留分支点之前的所有对话内容：
codemaker --continue --fork       # 从最近会话创建分支
codemaker --session <id> --fork   # 从指定会话创建分支

TUI 中可在消息菜单或时间线中选择分支操作。
分支导航
在 TUI 的会话列表中，使用方向键浏览会话树：
快捷键操作Ctrl+X, Down进入第一个子会话Right下一个兄弟会话Left上一个兄弟会话Up返回父会话
上下文压缩（Compaction）
当对话上下文接近模型 token 上限时，CodeMaker 会自动执行压缩：
裁剪（Prune）：移除较早的工具输出，保留近期内容
压缩（Compact）：将历史消息摘要化，释放上下文空间
手动触发
TUI 中按 Ctrl+X, C 手动压缩当前会话。
配置
在 codemaker.json 中配置：
{
  "compaction": {
    "auto": true,
    "prune": true
  }
}

环境变量控制：
环境变量作用CODEMAKER_DISABLE_AUTOCOMPACT=1禁用自动压缩CODEMAKER_DISABLE_PRUNE=1禁用工具输出裁剪
会话分享
分享功能会生成公开链接，供他人查看对话内容。
分享模式
在 codemaker.json 中配置：
{
  "share": "manual"
}

模式说明"manual"默认值，需手动分享"auto"新会话自动生成分享链接"disabled"完全禁用分享功能
也可通过环境变量 CODEMAKER_AUTO_SHARE=1 开启自动分享。
手动分享
在 TUI 中使用 /codemaker-share 命令分享当前会话，链接将复制到剪贴板并尝试在浏览器中打开。
CLI 模式下通过 --share 参数分享：
codemaker run "你的消息" --share

会话导出
TUI 中按 Ctrl+X, X 将当前会话内容导出到外部编辑器。
消息回退（Revert）
对于 AI 产生的文件变更，可以回退到特定消息时刻的文件状态，也可以恢复被回退的变更。
时间线
TUI 中按 Ctrl+X, G 查看当前会话的时间线，展示对话节点和分支关系。
快捷键汇总
快捷键操作Ctrl+X, N新建会话Ctrl+X, L会话列表Ctrl+X, G时间线Ctrl+X, C压缩会话Ctrl+X, X导出会话Ctrl+R重命名会话Ctrl+D删除会话Escape中断当前操作
快捷键可通过 tui.json 自定义，详见 快捷键配置指南。
消息滚动
快捷键操作PageUp / Ctrl+Alt+B向上翻页PageDown / Ctrl+Alt+F向下翻页Ctrl+Alt+U向上翻半页Ctrl+Alt+D向下翻半页Ctrl+G / Home跳到第一条消息Ctrl+Alt+G / End跳到最后一条消息
