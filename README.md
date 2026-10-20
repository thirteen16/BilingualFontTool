# BilingualFontTool · 中英文字体合成工具

为中文和英文分别选择字体与字号比例，合成为一款可安装的 TTF 字体。

## 下载使用

在 [Releases](https://github.com/thirteen16/BilingualFontTool/releases/latest) 下载 `BilingualFontTool.exe`，双击运行，无需另装 Python。

1. 导入两款字体，或从系统字体中选择。支持 TTF、OTF、TTC。
2. 分别设置中文、英文字号，填写新的字体名称。
3. 点击 **生成字体**，保存 TTF 并查看实际预览。
4. 点击 **安装字体**，在 Windows 字体查看器中安装。
5. 在 [noMeiryoUI](https://github.com/Tatsu-syo/noMeiryoUI) 中选择新字体，系统字号设为中文基准字号。

例如中文 12、英文 11，输出字体的英文按 11/12 缩放。在 noMeiryoUI 中选择 12 pt 即对应这个比例。不同字体的字面大小不同，视觉效果以实际显示为准。

工具不会自动修改系统字体或注册表。noMeiryoUI 只能影响遵循相关系统字体设置的界面。

## 合并方式

- **TrueType 轮廓优先原生合并**：FontTools 分配中英文字符、归一化尺度并合并，尽可能保留中文微调指令与受支持的 GSUB/GPOS 排版表。英文缩放后移除微调指令。
- **CFF / CFF2 轮廓兼容模式**：转换为 TrueType 轮廓，支持常见 OTF，但不保留源微调指令、字偶距和高级排版。
- 中文及全角标点优先用中文字体；英文、数字、半角标点和拉丁扩展字符优先用英文字体。缺失字符从另一款字体补齐。
- TTC 可选择内部字体。可变字体固定为默认轴值，输出为静态 Regular 字体；其他字重请选对应静态字体文件。
- 输出面向横排系统界面；原生合并移除竖排表和旧签名。不是彩色字体或复杂文字整套排版字体的通用合并器。

建议优先选择 TTF。修改配方时使用新的字体名称及文件名，以避免 Windows 字体缓存。已有输出和源字体不会被覆盖。

## 从源码运行

需要 Windows 10/11、Python 3.13（包含 Tkinter）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 构建 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

也可在已允许脚本运行的 PowerShell 中执行 `./build.ps1`。产物为 `dist/BilingualFontTool.exe`。

- `app.py`：桌面界面、字体选择与预览。
- `font_engine.py`：字符分配、缩放、合并与 TTF 导出。
- `BilingualFontTool.spec`、`build.ps1`：可复现的打包入口。
- `requirements.txt`：依赖版本。
- `licenses/`：第三方依赖许可说明。

仓库不包含源字体、生成字体、个人设置、测试文件或构建产物。EXE 通过 Releases 发布。

源字体的许可仍适用于合成结果，请使用允许相应用途的字体；本项目不授予任何第三方字体的修改或分发权限。
