@echo off
setlocal
set "PROXY=192.168.50.254:7895"
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "%PROXY%" /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /t REG_SZ /d "<local>" /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -Namespace WinInet -Name Native -MemberDefinition '[DllImport(\"wininet.dll\")] public static extern bool InternetSetOption(int hInternet, int dwOption, System.IntPtr lpBuffer, int dwBufferLength);'; [WinInet.Native]::InternetSetOption(0,39,[IntPtr]::Zero,0) | Out-Null; [WinInet.Native]::InternetSetOption(0,37,[IntPtr]::Zero,0) | Out-Null"
echo.
echo System proxy enabled: %PROXY%
echo Local intranet bypass: ^<local^>
echo.
pause
