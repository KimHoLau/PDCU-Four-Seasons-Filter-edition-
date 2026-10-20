一、Ghidra 分析结果
“自定义影像”列表的构建函数是 FUN_1401faed0。它对每个模式做条件判断：
if (imageTone == 0x1D) {            // HARUBENI
  if (obj != NULL && obj[0x15] != 0 && FUN_140eda6a0(obj)) addMenuItem(...);
}
else if (imageTone == 0x1E) { ... FUN_140eda790(obj) ... }  // KATEN
else if (imageTone == 0x1F) { ... FUN_140eda880(obj) ... }  // KYUSHU
else if (imageTone == 0x20) { ... FUN_140eda970(obj) ... }  // FUYUNO
else addMenuItem(...);                                       // 其它模式无条件加入

而四个资格函数最终只是返回对象里的四个字节：
return *(char *)(obj + 0x4600);  // HARUBENI
return *(char *)(obj + 0x4601);  // KATEN
return *(char *)(obj + 0x4602);  // KYUSHU
return *(char *)(obj + 0x4603);  // FUYUNO

这四个字节由 FUN_140ed9610 根据机身/镜头/固件计算——这就是我们改元数据始终绕不过去的原因：它不是读 Model 字符串，而是解析 PEF 参数集后算出的能力位。

二、补丁内容
在调用点后面是标准的：
E8 xx xx xx xx     call  FUN_140eda6xx
84 C0              test  al, al
0F 84 xx xx xx xx  jz    skip_add

我把 4 处 jz（每个 6 字节）全部改成 90 90 90 90 90 90，于是不管能力位真假，都会继续执行“添加菜单项”。
已生成补丁副本（原 exe 未动）：

三、已完成的改动
项	内容
目标文件	Digital Camera Utility 5.exe
备份	Digital Camera Utility 5.exe.bak（原版，SHA-256 D55EC396…75D387）
修改点	4 处 jz（每个 6 字节）→ 90 90 90 90 90 90
地址	0x1FAC52、0x1FACAF、0x1FAD0C、0x1FAD69
新 SHA-256	71697A61F2A18FCD414688A0CDB4EB48394FFF1EDA078D36B5AD215C2285B2DF
签名状态	HashMismatch（符合预期，见下方风险）

四、风险提示
数字签名已失效，Windows SmartScreen/杀软可能提示“未知发布者”或拦截；这是修改官方二进制的必然结果。
不要在校验签名的环境（如某些企业策略）里使用。
功能层面已验证正常；但这是绕过相机端“机身+镜头+SE 固件”授权逻辑，仅建议个人研究/兼容用途。
