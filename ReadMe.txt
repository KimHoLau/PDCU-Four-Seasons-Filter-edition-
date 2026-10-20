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
 
                                                                     2026-10-21 by KimHoLau
