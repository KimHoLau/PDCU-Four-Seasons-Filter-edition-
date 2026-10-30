# `pentax_seasons.exe` 分析：它到底改了什么，为什么 K-3 III 用不了

> 本文只描述**实测与反编译看到的事实**；末尾有“结论边界”，说明哪些还没验证。

## 0. 结论摘要

- `tools/pentax_seasons.exe` 是 **PyInstaller 单文件打包的 Python 3.11 / tkinter 小程序**
  （源码路径 `\\Mac\BAK\pentax_f\pentax_seasons.py`，构建时间 2023-12-02 08:42:39Z）。
  它不做任何色彩计算，全部逻辑就是往 DNG 的 Pentax 私有块里**写固定的字节**。
- 它只写两处（外加一个老机型补丁）：
  1. 私有块里 tag `0x021A` 表起点 **+26** 的那 1 个字节 → `0x21`；
  2. 在 tag `0x021A` 表里找 `1A 00 02 00`（记录 id `0x001A`），在命中点 **+26** 处覆盖写入
     一张 **156 字节固定表**（6 条 × 26 字节，记录 id `0x1C..0x21`）；
  3. 若 tag `0x021A` 条目的“计数”低 16 位 < 912，就把它的低字节改成 `0x90`（本机样本都没触发）。
- 那个 `1A 00 02 00` 只在 **1024 字节窗口**内查找，于是：
  - **645Z 一类布局**（记录在 tag `0x021A` 表 +704）：搜索命中 → 写满 157 字节 → 弹“完成”；
  - **K-3 Mark III**（记录在 +1454）：窗口只覆盖 +27..+1050 → **只写 1 个字节**，然后弹
    “莫名其妙的错误，该文件无法转换！”。
- 它**不改**“四季可用”标记（tag `0x0014` / `0x0016`）。在 645Z 上实测：patch 前后 PDCU
  渲染结果**逐像素相同**（图像区 mean diff = 0.000），也没有多出任何菜单项。
- 因此：**这个工具无法把 K-3 III 的 DNG 变成 PDCU 能识别的 KYUSHU**。要让 PDCU 按 KYUSHU
  渲染，需要完整移植私有 IFD 与 tag `0x021f` 数据；本仓库已不再附带这类实验辅助工具。

## 1. 工具身份

| 项目 | 值 |
| --- | --- |
| 文件 | `tools/pentax_seasons.exe` |
| 大小 | 9,971,519 B |
| SHA-256 | `00286E1D0C1BE1DBCF88243916B836755050E7DD31E481A6CA7797B00DA3DC95` |
| MD5 | `642BEE8A65CAA7282DDD8269A987B340` |
| PE | PE32+ (x64)，Subsystem = 2 (GUI) |
| 打包 | PyInstaller onefile，Python **3.11**（`python311.dll`），含 tkinter/Tcl |
| 链接时间戳 | 2023-12-02 08:42:39Z（0x656AEDFF） |
| 源文件 | `\\Mac\BAK\pentax_f\pentax_seasons.py`（Mac 上开发、Windows 上打包） |

CArchive 里只有 4 个脚本条目：`pyiboot01_bootstrap`、`pyi_rth_inspect`、`pyi_rth__tkinter`、
**`pentax_seasons`（4,600 B → 9,488 B）**；另有 `PYZ-00.pyz`（1,420,058 B，106 个纯 Python
模块，全是标准库：`email`/`http`/`json`/`urllib`/`_pydecimal` 等）。整个程序只有 8 个 code
object：

```
<module>                             146 B
  Application_UI                      20 B
    __init__                        1082 B   ← 界面
  Application                         38 B
    __init__                          58 B
    open_file                        356 B   ← 选文件
    save_file                       2130 B   ← 核心：改字节
    complate                         298 B
```

## 2. 怎么还原出来的

1. 按 PyInstaller CArchive 格式（文件尾 88 字节 cookie：`MEI\014\013\012\013\016` +
   `!8siiii64s`）取出 TOC 与各条目；`pentax_seasons` 条目是 zlib 流。
2. `PYZ-00.pyz` 的 TOC 是带 `FLAG_REF` 的 marshal 数据，用 `xdis` 的
   `VersionIndependentUnmarshaller(magic_int=3495)` 解出 code object。
3. 用 `xdis` 的 `opcode_311` 表手工反汇编（本仓库不依赖任何 3.11 解释器）。
4. 关键结论用**真跑 exe + 逐字节 diff** 验证（见 §4），并用
   `tools/pentax_seasons.py` 复现到 **0 字节差异**。

复现脚本（`.tmp/` 里，未入库）：`pyi_extract.py` → `pyz2.py` → `rawdis.py`。

## 3. 完整逻辑（`Application.save_file` 的等价源码）

```python
def save_file(self):
    path = filedialog.askdirectory()                # 选输出目录
    if path == '':
        return
    fc = fe = 0
    pdata = SEASON_TABLE                            # 156 字节固定表（见 §5）
    self.state_var.set('保存路径：' + path + '  转换中...')
    for fn in self.filename:
        ftype = False
        with open(fn, 'rb') as fs:
            fdata = fs.read(1280)                   # 只看文件头 1280 字节
            serch = fdata.find(b'PENTAX \x00II')    # 私有块起点
            if serch == -1:
                messagebox.showinfo('错误', fn + ' 可能不是宾得RAW文件，无法转换！')
                fe += 1
                continue
            fs.seek(serch + 10)
            mk_l = int.from_bytes(fs.read(2), 'little')   # IFD 条目数
            for l in range(mk_l):
                fs.seek(serch + 12 * l)                   # ← 注意：少了 +12
                ra = fs.read(12)
                if int.from_bytes(ra[0:2], 'little') == 538:   # tag 0x021A
                    ln = l
                    ftype = True
                    break
        if ftype:
            fp, fm = os.path.split(fn)
            fname, ex = os.path.splitext(fm)
            ft = path + '/' + fname + '_4' + ex           # 输出名 <名>_4.<扩展名>
            shutil.copy(fn, ft)
            with open(ft, 'rb+') as f:
                f.seek(ln * 12 + serch + 4)               # = 第 ln-1 条记录 +4
                if int.from_bytes(f.read(2), 'little') < 912:
                    f.seek(ln * 12 + serch + 4)
                    f.write(b'\x90')
                f.seek(ln * 12 + serch + 8)
                tmp = int.from_bytes(f.read(2), 'little') # tag 0x021A 的表内偏移
                f.seek(tmp + serch + 26)
                f.write(b'!')                             # 0x21
                fdata = f.read(1024)                      # 只有 1024 字节窗口
                sf = fdata.find(b'\x1a\x00\x02\x00')
                if sf == -1:
                    messagebox.showinfo('错误', fn + ' 莫名其妙的错误，该文件无法转换！')
                    fe += 1
                else:
                    f.seek(tmp + serch + 53 + sf)
                    f.write(pdata)                        # 156 字节
                    fc += 1
        else:
            messagebox.showinfo('警告', fn + ' 格式不对，无法转换！')
            fe += 1
    self.state_var.set('保存路径：' + path + '  转换完成！')
    messagebox.showinfo('完成', str(fc) + '个文件转换成功。' + str(fe) + '个文件转换失败。')
    self.button_ok.pack()
```

两个细节值得注意：

- **扫描少了一个 `+12`**：`seek(serch + 12*l)` 实际读到的是第 `l-1` 条记录，于是命中
  tag `0x021A` 时 `ln = 真实下标 + 1`；而写点用的是 `serch + ln*12 + X`，正好又落回
  第 `ln-1` 条 = 真正的 tag `0x021A` 记录。两处偏移互相抵消，结果是对的（属于“写歪了但
  刚好对上”的写法）。
- **窗口只有 1024 字节**：`read(1024)` 是硬编码的，所以 `1A 00 02 00` 必须落在
  tag `0x021A` 表起点 +27..+1050 之间，否则直接失败——这正是 K-3 III 的死因。

界面只有三个控件：标题 `ASAHI SEASONS`、`选择文件`（`open_file`）、`转换文件`（`save_file`，
选文件前置灰）、成功后出现的 `!` 按钮；另有一段“非商业软件……只支持宾得部分机型（具体机型不详）”
的免责声明。

## 4. 实测：它对文件到底做了什么

用 UI 自动化真跑 exe（截图见 `.tmp/seasons_k3_after.png`、`.tmp/seasons_z_after.png`），
再逐字节比较输入/输出：

| 输入 | 弹窗 | 差异字节 | 位置 |
| --- | --- | --- | --- |
| K-3 III `IMGP1194.DNG` | **错误**（莫名其妙的错误…） | **1** | `0x2B64`: `02 → 21` |
| 645Z `IMGP0306.DNG` | **完成**（1 个成功） | **157** | `0x24A8`: `1B → 21`；`0x2768..0x2803`: 156 字节表 |

（`0x2B64` = 私有块 `0x3FE` + tag `0x021A` 表偏移 `10060` + 26；
`0x2768` = 私有块 `0x39E` + 表偏移 `8432` + 53 + 命中 677。）

`tools/pentax_seasons.py` 复现同样的判断与写点，与 exe 输出 **0 字节差异**：

```
python tools/pentax_seasons.py analyze sample/IMGP1157.DNG \
        "C:\Users\HP\Desktop\新建文件夹\IMGP0306.DNG"
python tools/pentax_seasons.py convert --out out .tmp/src/Z_0306.DNG
```

### 4.1 为什么 K-3 III 必失败

| 机型 | 私有块 | IFD 条目 | tag `0x021A` 偏移 | `1A 00 02 00` 在表里的位置 |
| --- | --- | --- | --- | --- |
| K-3 Mark III | 0x3FE，195,676 B | 100 | 10,060 | **+1454**（窗口只到 +1050） |
| 645Z | 0x39E，151,552 B | 113 | 8,432 | **+704**（窗口内） |

这个 +1454 是 K-3 III 那张表的**结构位置**，与拍摄模式无关：KYUSHU（1157/0110）、普通
（1194）、以及另外两张 K-3 III 样本（1146/1190）全部是 +1454。所以**任何** K-3 III 文件
都不可能让这个 exe 走完流程。

### 4.2 patch 之后 PDCU 的反应

- 645Z：patch 前 / patch 后各开一次 PDCU，主图像区逐像素比较 **mean diff = 0.000**，
  雷达图区也是 0.000 —— 渲染完全没变。
- 原因是它**没动能力标记**：645Z 的 `0x0014 = 9`、`0x0016 = 43`；K-3 III 机内 KYUSHU 是
  `0x0014 = 21`、`0x0016 = 50`，普通是 `12 / 40`。PDCU 的四季菜单/渲染看的是这些标记与
  tag `0x021f` 里的数据，而工具两者都不碰。
- 我们也按它的写法做了一次“类比移植”：把同一张 156 字节表写到 K-3 III 的
  `payload + 1480`（= 命中点 +1454 再 +26），另加那个 `0x21`。结果 PDCU 里雷达图仍然是
  六边形（`.tmp/radar_analog2.png`），不是 KYUSHU 的斜四边形。说明这张表**不足以**定义
  KYUSHU 的影调。

## 5. 那 156 字节到底是什么

按 26 字节一条切成 6 条，每条 13 个 u16：

| # | 记录 id | 13 个 u16（`0xFFFF` 即 −1） | 末段指向 |
| --- | --- | --- | --- |
| 0 | `0x001C` | `001C 0001 0002 0001 0001 FFFF FFFF 0000 0000 0000 FFFF 0015 0000` | `0x15` |
| 1 | `0x001D` | `001D 0001 0002 0003 FFFF FFFF FFFF 0000 0000 FFFE 0004 0016 0000` | `0x16` |
| 2 | `0x001E` | `001E 0001 0008 0004 0001 FFFF FFFF 0000 0003 FFFD FFFF 0017 0000` | `0x17` |
| 3 | `0x001F` | `001F 0001 0004 0001 0001 FFFF FFFF FFFF 0000 FFFF FFFF 0018 0000` | `0x18` |
| 4 | `0x0020` | `0020 0001 0008 0004 0001 FFFF FFFF 0003 FFFC 0004 FFFF 0019 0000` | `0x19` |
| 5 | `0x0021` | `0021 0001 0001 0005 0001 FFFF FFFF 0000 0000 0000 FFFF 001A 0000` | `0x1A` |

可以确定的只有形状：**6 条 26 字节记录，记录 id `0x1C..0x21`，第 12 个字段依次指向
`0x15..0x1A`**。它和相机里已有的表同构（645Z 表里也能看到 id `0x15`、`0x16`、`0x1A`
同形状的记录，例如命中点那条就是 `001A 0002 ... 0004`，末字段为 4）。

不能确定的是语义：这些 u16 是影调曲线控制点、还是“模式→参数组”的跳转表，需要 PDCU 端
的解析代码才能定论。可以确定的是**它不是 KYUSHU 的完整参数**——否则 §4.2 的类比移植就该出
斜四边形。所以这里只把它记作“作者硬编码的季节参数片段”，不做过度解读。

此外，`0x2B64` 那 1 个字节（把表里某个 u16 改成 `0x..21`）在所有样本上都只是把
`0x0202→0x0221`（K-3 III）或 `0x001B→0x0021`（645Z），也没有可观察的渲染效果。

## 6. 与完整 KYUSHU 数据移植的边界

`pentax_seasons.exe` 只改季节参数表的一小段；PDCU 认 KYUSHU 还需要“能力标记 +
tag `0x021f` 的完整数据”，exe 缺的正是后者。早期版本曾附带一个同机型供体私有块
移植的实验辅助工具，该工具已从本仓库移除，不再提供命令或源码。

## 7. 复现与自查

```powershell
# 看任意 DNG 在这个工具里会走到哪一步（不写文件）
python tools\pentax_seasons.py analyze sample\IMGP1157.DNG

# 等价转换（写 <目录>\<名>_4.DNG；--force 允许“只写 1 字节”的不完整结果）
python tools\pentax_seasons.py convert --out out sample\IMGP1157.DNG

# 验证等价性：对 645Z 样本，本脚本与 exe 输出逐字节相同
python tools\pentax_seasons.py convert --out out .tmp\src\Z_0306.DNG
#   → 与 exe 的 Z_0306_4.DNG 差异 0 字节
```

`analyze` 对三个典型文件的输出：

```
IMGP1157.DNG  PENTAX K-3 Mark III  IFD 100  tag 0x021A: ln=62 表 +10060 → file 0x2B4A
  mode byte 0x2B64 02 -> 21 ; marker not in window (actually payload +1454)  => 只写 1 B
IMGP1194.DNG  PENTAX K-3 Mark III  同上                                      => 只写 1 B
IMGP0306.DNG  PENTAX 645Z          IFD 113 表 +8432 → file 0x248E
  mode byte 0x24A8 1B -> 21 ; marker hit +704 ; table at 0x2768 (payload +730) => 157 B
```

## 8. 结论边界

- 已实测：K-3 III（100 条目布局）必然失败；645Z（113 条目布局）能写满但渲染无变化。
- 未实测：K-1 / K-1 II / K-70 / KP / KF 等其它机型。它们的私有 IFD 条目数与表布局可能
  与 645Z 相同（都走 +704 那条路），也可能不同——想知道就对该机型的 DNG 跑一次
  `analyze`，看 `marker hit` 是否为正值即可。
- 未验证：那张 156 字节表在**支持四季的机型**上是否有实际效果。本机的 K-3 III 走不到写入
  那一步，645Z 又不支持四季，所以没有样本能证明它的作用；作者的原意（README/发布帖）不在
  这个 exe 里。要验证得找一台“能进四季菜单、且私有表是 113 条目布局”的机型。
- 因此不要把“这个工具能让 PDCU 认出 KYUSHU”当作结论；本机可复现的事实是相反的。
