#ifndef MyAppVersion
  #define MyAppVersion "3.0.0"
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
UninstallDisplayIcon={sys}\shell32.dll,31
SetupIconFile=..\icons\icon.ico

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\release\stage\GMonster.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release\stage\WUM.exe"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{app}\uninstall.ico"

[Icons]
Name: "{autoprograms}\GMonster"; Filename: "{app}\GMonster.exe"
Name: "{autoprograms}\WUM"; Filename: "{app}\WUM.exe"
Name: "{autoprograms}\Uninstall GMonster"; Filename: "{uninstallexe}"; IconFilename: "{sys}\shell32.dll"; IconIndex: 31
Name: "{autodesktop}\GMonster"; Filename: "{app}\GMonster.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GMonster.exe"; Description: "Launch GMonster"; Flags: postinstall nowait skipifsilent

[Code]
var
  RemoveUserData: Boolean;

procedure HideFile(const FileName: String);
var
  ResultCode: Integer;
begin
  ResultCode := -1;
  if not Exec(
    ExpandConstant('{sys}\attrib.exe'),
    '+h ' + AddQuotes(FileName),
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
    Log('Could not hide installer support file: ' + FileName)
  else if ResultCode <> 0 then
    Log('Could not hide installer support file: ' + FileName);
end;

procedure HideUninstallerFiles;
var
  UninstallerExe: String;
begin
  UninstallerExe := ExpandConstant('{uninstallexe}');
  HideFile(UninstallerExe);
  HideFile(ChangeFileExt(UninstallerExe, '.dat'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    HideUninstallerFiles;
end;

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
