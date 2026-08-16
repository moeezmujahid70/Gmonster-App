#ifndef MyAppVersion
  #define MyAppVersion "2.2r"
#endif

[Setup]
AppId={{DC768B32-3261-48A6-B34A-C5D27C6A5C18}
AppName=GMonster
AppVersion={#MyAppVersion}
AppPublisher=GMonster
DefaultDirName={autopf}\GMonster
DefaultGroupName=GMonster
OutputDir=..\release
OutputBaseFilename=GMonster-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\GMonster.exe
SetupIconFile=..\icons\icon.ico

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\release\stage\GMonster.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release\stage\WUM.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GMonster"; Filename: "{app}\GMonster.exe"
Name: "{autodesktop}\GMonster"; Filename: "{app}\GMonster.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GMonster.exe"; Description: "Launch GMonster"; Flags: postinstall nowait skipifsilent

[Code]
var
  RemoveUserData: Boolean;

function InitializeUninstall(): Boolean;
begin
  RemoveUserData := MsgBox(
    'Remove user data? This deletes local GMonster configuration, logs, and campaign files.',
    mbConfirmation,
    MB_YESNO
  ) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and RemoveUserData then
    DelTree(ExpandConstant('{localappdata}\GMonster\data'), True, True, True);
end;
