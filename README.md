# film-short-drama · 电影短剧制作

用于 Codex 的短片与短剧制作技能，覆盖剧本、分镜、角色与声音连续性、原生对白视频、剪辑及 MP4 交付。可只做剧本或分镜，不会因为启用技能就自动提交付费生成任务。

## 安装

将仓库克隆到 Codex 的个人技能目录。默认位置如下；设置了 `CODEX_HOME` 时使用其 `skills` 子目录。

```sh
git clone https://github.com/flyingrtx2333/flim-short-drama.git ~/.codex/skills/film-short-drama
```

如果目录已存在，先备份原技能，再选择更新方式，避免覆盖本地修改。重新打开 Codex 会话以加载技能。

## 使用

在对话中输入 `$film-short-drama`，然后说明需求，例如：

- “把这个故事写成一部 45 秒悬疑短片，先只交付剧本。”
- “继续这个项目，读取已有计划，制作完整分镜汇总。”
- “根据已确认分镜做原生对白试片，保留角色音色与连续性。”
- “修复这段对话的空等、反应镜和字幕，然后导出新版 MP4。”

默认先审阅完整分镜，再制作 480p 试片；试片确认后按交付规格制作成片素材。用户当前明确指令和项目已有授权优先，已确认的同版本不重复询问。

## 依赖与范围

写剧本、制作计划及提示词不需要生成服务。进入媒体阶段时，需要环境中实际可用的工具与访问权限：

| 环节 | 依赖 |
| --- | --- |
| 图片生成与修改 | 当前安装的 `imagegen` 技能及对应图像工具 |
| 视频生成 | 默认 `minimax-h3-video` 技能的 AutoDL 工作流；用户可指定其他服务 |
| 剪辑与媒体检查 | FFmpeg / FFprobe，以及能实际审阅音画的环境 |
| 分镜汇总图 | Python 3.9+、Pillow、覆盖所用语言的字体 |

生成服务、凭据、模型、字体与项目素材不包含在仓库中。外部技能须单独安装，不能把仓库存在当作服务已经配置。工作流参数与费用以当前视频技能保存的定义为准；遇到缺失依赖时保留准备结果并报告。

## 分镜汇总工具

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/render_storyboard.py /path/to/storyboard.json \
  --output /path/to/storyboard.png --columns 3 \
  --font /path/to/chinese-font.ttf
```

字体可自动探测 macOS 黑体与 Linux Noto CJK，其他环境使用 `--font`。清单中的图片路径相对清单文件解析；输出完整台词、动作、声音和首尾帧标记。依赖上一镜实片末帧的段落可显示为待生成，但不能据此提交生产。

清单格式、示例和场景文字预览见 [分镜渲染说明](references/storyboard-rendering.md)。该工具只排版已有图片与文字，不生成视频。

## 仓库内容

- [SKILL.md](SKILL.md)：技能入口及制作规则。
- `references/`：表演、视觉、连续性、剪辑、声音与交付指导。
- `scripts/render_storyboard.py`：通用分镜汇总与场景文字预览工具。
- `agents/openai.yaml`：Codex 界面元数据。

本仓库由本机已使用的技能整理而来，保留其制作默认值。`references/mv-workspace.md` 是可选的 MV 工坊约定，仅在使用同类项目布局时适用；其他工作区遵循自己的项目说明。仓库不包含角色照片、音色、成片或生成任务凭据。
