; Kill running Hub CZN processes before extracting files so the installer
; does not fail with "Error opening file for writing" on hub-czn-api.exe.
!macro NSIS_HOOK_PREINSTALL
  nsExec::ExecToLog '"taskkill" /F /IM "hub-czn.exe" /T'
  nsExec::ExecToLog '"taskkill" /F /IM "hub-czn-api.exe" /T'
  Sleep 1000
!macroend

; Untrust the mitmproxy CA that Setup added, so uninstalling actually undoes it.
; Only touches the per-user store, and the private key in ~/.mitmproxy is left alone
; in case another mitmproxy tool is using it.
!macro NSIS_HOOK_POSTUNINSTALL
  nsExec::ExecToLog '"certutil" -user -delstore Root mitmproxy'
!macroend
