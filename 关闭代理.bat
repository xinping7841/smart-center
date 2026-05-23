@echo off
setlocal
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /f >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /f >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -Namespace WinInet -Name Native -MemberDefinition '[DllImport(\"wininet.dll\")] public static extern bool InternetSetOption(int hInternet, int dwOption, System.IntPtr lpBuffer, int dwBufferLength);'; [WinInet.Native]::InternetSetOption(0,39,[IntPtr]::Zero,0) | Out-Null; [WinInet.Native]::InternetSetOption(0,37,[IntPtr]::Zero,0) | Out-Null"
echo.
echo System proxy disabled.
echo.
pause
