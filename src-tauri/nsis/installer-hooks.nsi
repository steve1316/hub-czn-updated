; Kill running Hub CZN processes before extracting files so the installer
; does not fail with "Error opening file for writing" on hub-czn-api.exe.
!macro NSIS_HOOK_PREINSTALL
  nsExec::ExecToLog '"taskkill" /F /IM "hub-czn.exe" /T'
  nsExec::ExecToLog '"taskkill" /F /IM "hub-czn-api.exe" /T'
  Sleep 1000
!macroend

; Undo a capture that is still in place before the files go, using the same cleanup the app runs
; on shutdown. Without this, uninstalling mid-capture leaves the game pointed at 127.0.0.1 for good
; and the app that could fix it is gone.
!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog '"$INSTDIR\hub-czn-api.exe" --cleanup'
!macroend

; Untrust the mitmproxy CA that Setup added, so uninstalling actually undoes it.
; Only touches the per-user store, and the private key in ~/.mitmproxy is left alone
; in case another mitmproxy tool is using it.
!macro NSIS_HOOK_POSTUNINSTALL
  nsExec::ExecToLog '"certutil" -user -delstore Root mitmproxy'
!macroend
