已经定位到根本原因并做出补丁。

一、Ghidra 分析结果
“自定义影像”列表的构建函数是 FUN_1401faed0。它对每个模式做条件判断：

c


if (imageTone == 0x1D) {            // HARUBENI
  if (obj != NULL && obj[0x15] != 0 && FUN_140eda6a0(obj)) addMenuItem(...);
}
else if (imageTone == 0x1E) { ... FUN_140eda790(obj) ... }  // KATEN
else if (imageTone == 0x1F) { ... FUN_140eda880(obj) ... }  // KYUSHU
else if (imageTone == 0x20) { ... FUN_140eda970(obj) ... }  // FUYUNO
else addMenuItem(...);                                       // 其它模式无条件加入
而四个资格函数最终只是返回对象里的四个字节：

c


return *(char *)(obj + 0x4600);  // HARUBENI
return *(char *)(obj + 0x4601);  // KATEN
return *(char *)(obj + 0x4602);  // KYUSHU
return *(char *)(obj + 0x4603);  // FUYUNO
这四个字节由 FUN_140ed9610 根据机身/镜头/固件计算——这就是我们改元数据始终绕不过去的原因：它不是读 Model 字符串，而是解析 PEF 参数集后算出的能力位。

二、补丁内容
在调用点后面是标准的：

代码块


E8 xx xx xx xx     call  FUN_140eda6xx
84 C0              test  al, al
0F 84 xx xx xx xx  jz    skip_add
我把 4 处 jz（每个 6 字节）全部改成 90 90 90 90 90 90，于是不管能力位真假，都会继续执行“添加菜单项”。

已生成补丁副本（原 exe 未动）：

代码块


D:\Program Files\PENTAX\Digital Camera Utility 5\Digital Camera Utility 5_patched.exe
SHA-256：71697A61F2A18FCD414688A0CDB4EB48394FFF1EDA078D36B5AD215C2285B2DF

三、请测试
双击运行 Digital Camera Utility 5_patched.exe（和原版共用配置，界面一样）；
打开任意一张 K-30 的 DNG（比如 E:\IMGP3603.DNG，或之前的 testG）；
进入 Laboratory，展开「自定义影像」列表 / 工具栏下拉 / 右键菜单，看是否出现： HARUBENI / KATEN / KYUSHU / FUYUNO（可能还带 SATOBI、Gold）。
请告诉我：

列表里出现了哪些；
选中后是否能正常应用、图像是否正常；
有没有报错或崩溃。
四、如果生效
我会：

备份原 exe（例如 Digital Camera Utility 5.exe.bak）；
把补丁应用到原 exe，之后正常启动即可；
说明代价：数字签名失效（Windows 可能提示未知发布者）、官方升级会覆盖补丁、建议保留补丁脚本以便重打。
如果列表仍是空的，说明你看到的那个控件不是这个菜单构建函数，我再用同样方法找组合框（ComboBox）的填充函数——现在 Ghidra 工程和分析结果都已就绪，后续会快很多。






用量 48.7M tok
00:26
经过测试，功能一切正常
00:32

已完成
已完成，用时 32秒
补丁已应用到正式安装的 exe，测试通过，备份与回滚脚本都已就位。

已完成的改动
项	内容
目标文件	Digital Camera Utility 5.exe
备份	Digital Camera Utility 5.exe.bak（原版，SHA-256 D55EC396…75D387）
修改点	4 处 jz（每个 6 字节）→ 90 90 90 90 90 90
地址	0x1FAC52、0x1FACAF、0x1FAD0C、0x1FAD69
新 SHA-256	71697A61F2A18FCD414688A0CDB4EB48394FFF1EDA078D36B5AD215C2285B2DF
签名状态	HashMismatch（符合预期，见下方风险）
这 4 个跳转原本会在 FUN_140eda6a0/790/880/970（HARUBENI/KATEN/KYUSHU/FUYUNO 的资格检查）返回假时跳过菜单项；NOP 之后，只要图像对象存在，四个模式就会无条件加入列表。SATOBI、Gold 等本来就不受这四个检查约束，行为不变。

维护方式
我放了可重复执行的补丁脚本：

dcu5_enable_special_editions.ps1

带版本守卫：只对 5.10.2.2 的原始哈希生效，其它版本会拒绝执行（更新后代码偏移会变，需要重新分析）；
已打过补丁则直接退出；
首次运行自动生成 .bak 备份。
官方更新会覆盖 exe，更新后重新跑一次脚本即可（若版本变了，告诉我，我用现成的 Ghidra 工程重新定位）。

回滚：把 .bak 覆盖回 Digital Camera Utility 5.exe 即可。

风险提示
数字签名已失效，Windows SmartScreen/杀软可能提示“未知发布者”或拦截；这是修改官方二进制的必然结果。
不要在校验签名的环境（如某些企业策略）里使用。
功能层面已验证正常；但这是绕过相机端“机身+镜头+SE 固件”授权逻辑，仅建议个人研究/兼容用途。
