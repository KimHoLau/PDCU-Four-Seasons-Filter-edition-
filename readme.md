一、镜头相关性与「正确的 KYUSHU」（2026-10-23 修正）
- 用同一张 DNG 只改镜头标识（`LensType` 0x003f），渲染逐像素一致：镜头不参与调色，只决定菜单资格。
- 同一张 IMGP1157.DNG 只改 `ImageTone`（12 / 15 / 31 / 8）会得到不同的雷达图和画面，
  说明「菜单里的 KYUSHU」与「相机记录在文件里的那一套」不是同一个参数状态。
- 维护者确认：`sample/HDFA43_KYUSHU_IMGP1157.png` 的斜四边形才是正确的 KYUSHU；
  该状态目前还没在确定性操作下复现（菜单是自绘列表，滚动位置会影响点选）。
详见 `docs/PDCU-KYUSHU-镜头无关性验证.md`。

二、供体移植工具（近似方案）
PDCU 的 KYUSHU 依赖相机写进 DNG 私有块里的那套参数；非机内 KYUSHU 的文件没有它。
可以用一张机内 KYUSHU 的 DNG 当“供体”，把私有块前 15,031 字节（`0x3AB7`）写进目标：

```powershell
python tools/kyushu_transplant.py --donor sample\IMGP1157.DNG --target sample\IMGP1194.DNG --out out.dng
```

- 输出会在 PDCU 里显示为 KYUSHU（雷达图斜四边形）；
- **供体与目标必须是同一机型**（参数是机型相关的，跨机型不做）；
- K-3 Mark III：固定复制 15,031 字节（已实测）；
- 其他机型（K-1/K-1 II/KF 等）：按 `tag 0x021f 偏移 + 0x733` 估算长度，
  需要加 `--allow-untested`，并在 PDCU 里检查结果；必要时用 `--len` 指定实测长度；
- 会自动校验 K-3 III 供体标记（`0x0014=21`、`0x0016=50`、`0x0200/0x024c=1024`）；
- **近似**：会带入供体的影调/白平衡，可能偏暖；选光线接近的供体，输出后在 PDCU 里再校正。
- 不改输入文件。

三、`pentax_seasons.exe` 是什么（2026-10-23 分析）
网上流传的 `tools/pentax_seasons.exe` 不是“让 PDCU 认出 KYUSHU”的工具，实测结论：

- 它是 PyInstaller 打包的 Python 3.11 / tkinter 小程序（源码 `\\Mac\BAK\pentax_f\pentax_seasons.py`）；
- 只往 DNG 的 Pentax 私有块写两处固定字节：tag `0x021A` 表 +26 的 1 个字节（`0x21`），
  以及表中 `1A 00 02 00` 之后 26 字节处的 156 字节硬编码表；
- 那个标记只在 **1024 字节窗口**里找：645Z 一类布局命中（+704），K-3 III 在 +1454，
  所以对 K-3 III 它**只写 1 个字节就报错**（`IMGP1194.DNG` 实测：0x2B64 `02→21`，无其它变化）；
- 它不改能力标记（`0x0014`/`0x0016`），645Z 上 patch 前后 PDCU 渲染逐像素相同。
- 完整分析见 `docs/PDCU-pentax_seasons工具分析.md`；等价的命令行复现在
  `tools/pentax_seasons.py`（`analyze` 解释判断过程，`convert` 与 exe 输出 0 字节差异）。

四、工具兼容性更新（2026-10-26）
- `tools/dng_season_params.py` 与 `dist/PDCU-Season-Params.exe` v1.3 已支持老固件 K-1
  的带填充 `0x021A`：长度不能整除时按 `recordSize = 2 × (nParams + 1)` 识别，
  尾部保留区忽略。
- `0x021B` 后没有空位时，工具会把整个矩阵表迁移到私有块内安全空闲区
  （优先紧接新 `0x021A` 表尾，避开 preview/其他 tag），并更新 offset/length。
- 实测 `sample/IMGP0344.DNG`（K-1 v1.50）：0x021A 1146→860 B、28→32 条；
  0x021B 382→454 B、21→25 个矩阵；raw 49,393,851 B 不变，文件大小不变。
- 原版 PDCU 5.10.2.2（未改 EXE）直接打开补丁后的 `IMGP0344_all.dng`
  即可列出并渲染四季；打开原始 `IMGP0344.DNG` 则不列出。
- 645Z 试验（`sample/IMGP2674.DNG`）：结构上可以打补丁，PDCU 也会列出四项，
  但 K-1 的四季记录/矩阵跨机型颜色不对（HARUBENI 几乎不变，另外三项变成高调/发白）。
  GUI 默认拒绝跨机型；勾选“允许跨机型 donor（实验性）”后可以生成近似结果。
  详见 `docs/PDCU-季节参数补齐工具.md` 第 8 节。
- K-3（初代）试验（`sample/IMGP4929.DNG`）：同样可以打补丁，PDCU 四项都能显示，
  画面也都有变化；效果比 645Z 更接近四季，但 KATEN/KYUSHU 色彩仍与 K-1 不同，
  只能算近似。GUI 勾选“允许跨机型 donor（实验性）”后可用。详见同文档第 9 节。


