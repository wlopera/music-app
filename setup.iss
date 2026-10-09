; Script de instalación para Inno Setup (Music-App)
; Genera el instalador profesional MusicApp-Setup.exe

#define MyAppName "Music-App"
#define MyAppPublisher "Music-App"
#define MyAppExeName "Music-App.exe"

[Setup]
; Identificador único de la aplicación (GUID)
AppId={{9B7E34A1-3F7A-4D2A-98C1-82F3A8C7A0E1}
AppName={#MyAppName}
AppVersion=1.0
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Carpeta de salida y nombre del instalador resultante
OutputDir=dist\installer
OutputBaseFilename=MusicApp-Setup
Compression=lzma2/ultra64
SolidCompression=yes

; Privilegios de administrador requeridos para instalar en Program Files
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

; Iconos y presentación
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Copiar todo el contenido de la carpeta compilada dist\Music-App
Source: "dist\Music-App\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\musicapp.log"

[Code]
// Al desinstalar, preguntar amablemente si desea borrar las configuraciones de AppData
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\Music-App');
    if DirExists(AppDataDir) then
    begin
      if MsgBox('¿Deseas eliminar también tus datos de configuración y carpetas guardadas en ' + AppDataDir + '?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(AppDataDir, True, True, True);
      end;
    end;
  end;
end;
