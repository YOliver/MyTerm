; Inno Setup 脚本：生成 MyTerm 用户级 Windows 安装包。
;
; 编译方式：
;   1. 装 Inno Setup 6（https://jrsoftware.org/isinfo.php）
;   2. 用 ISCC.exe 编译：ISCC.exe installer\myterm.iss
;   或者直接跑 scripts\release.bat 一键完成。
;
; 安装包行为：
; - 默认装到 %LOCALAPPDATA%\Programs\MyTerm（不需要管理员权限，无 UAC）
; - 创建开始菜单项「MyTerm」
; - 注册卸载入口（控制面板 → 程序与功能）
; - 卸载时只删除程序文件，不动 %APPDATA%\MyTerm 与 %LOCALAPPDATA%\MyTerm（用户数据）
;
; 版本号通过命令行 /DAppVersion=x.y.z 注入，scripts\release.bat 会自动读 version.py 传入。
; 单独编译时如未传入则用下面的默认值。

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName       "MyTerm"
#define AppPublisher  "MyTerm"
#define AppExeName    "MyTerm.exe"
; 用户级 GUID：固定不变，未来升级时 Inno 据此识别"已安装"
#define AppId         "{{B0FC3F2A-9F1B-4F3A-8A54-1C2E8C7D0A11}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

; 用户级安装：装到 %LOCALAPPDATA%\Programs\MyTerm，不需要管理员
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; 输出
OutputDir=..\dist
OutputBaseFilename=MyTerm-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes

; 视觉
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern

; 兼容性：Windows 10+
MinVersion=10.0

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english";    MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\MyTerm.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"

[Run]
; 安装结束页勾选「立即运行」
Filename: "{app}\{#AppExeName}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent
