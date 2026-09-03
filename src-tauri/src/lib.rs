use std::collections::HashMap;
use std::net::TcpListener;
use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;

/// Ports to try for the sidecar, matching the range it would have picked from on its own.
const PORT_RANGE: std::ops::Range<u16> = 7842..7852;

// ── App state ────────────────────────────────────────────────────────────────

struct ApiPort(Mutex<u16>);

/// Token the sidecar prints at startup. Every API call has to send it back.
struct ApiToken(Mutex<String>);


struct SidecarState {
    child: CommandChild,
    pid:   u32,
    /// Job Object handle (Windows only).
    /// Kept alive so that when this struct — or the entire process — is
    /// dropped/killed for ANY reason, the OS closes this handle and
    /// immediately terminates every process in the job (sidecar + mitmdump
    /// + any other children).  No cleanup code needs to run.
    #[cfg(target_os = "windows")]
    _job: Option<WinJob>,
}

struct SidecarChild(Mutex<Option<SidecarState>>);

impl Drop for SidecarChild {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(state) = guard.take() {
                // Belt-and-suspenders: explicit kill + taskkill tree before
                // the Job Object handle is released by dropping `state`.
                let _ = state.child.kill();
                kill_tree(state.pid);
                // `state` is dropped here → _job is dropped → OS kills job.
            }
        }
    }
}

fn kill_tree(pid: u32) {
    #[cfg(target_os = "windows")]
    let _ = std::process::Command::new("taskkill")
        .args(["/F", "/T", "/PID", &pid.to_string()])
        .output();
    #[cfg(not(target_os = "windows"))]
    let _ = pid;
}

// ── Windows Job Object ────────────────────────────────────────────────────────
//
// Strategy: assign the sidecar to a Job Object with KILL_ON_JOB_CLOSE.
// When hub-czn.exe exits for ANY reason (graceful close, installer kill,
// crash, Task Manager), Windows automatically closes all process handles,
// including the Job Object handle.  That triggers the OS to kill every
// process in the job — sidecar, mitmdump, and any grandchildren — with no
// Rust cleanup code required.  This is fundamentally more reliable than
// taskkill, which only runs when our code runs.
//
// Raw extern declarations avoid adding a new crate dependency.

#[cfg(target_os = "windows")]
mod win {
    use std::ffi::c_void;

    pub const PROCESS_TERMINATE:  u32 = 0x0001;
    pub const PROCESS_SET_QUOTA:  u32 = 0x0100;
    pub const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;
    pub const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: i32 = 9;

    #[repr(C)]
    pub struct BasicLimitInfo {
        pub per_process_time: i64,
        pub per_job_time:     i64,
        pub limit_flags:      u32,
        pub min_ws:           usize,
        pub max_ws:           usize,
        pub active_proc:      u32,
        pub affinity:         usize,
        pub priority:         u32,
        pub scheduling:       u32,
    }

    #[repr(C)]
    pub struct IoCounters {
        pub read_ops:   u64, pub write_ops:  u64, pub other_ops:   u64,
        pub read_xfer:  u64, pub write_xfer: u64, pub other_xfer:  u64,
    }

    #[repr(C)]
    pub struct ExtLimitInfo {
        pub basic:          BasicLimitInfo,
        pub io:             IoCounters,
        pub proc_mem_limit: usize,
        pub job_mem_limit:  usize,
        pub peak_proc_mem:  usize,
        pub peak_job_mem:   usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        pub fn CreateJobObjectW(attrs: *mut c_void, name: *const u16) -> isize;
        pub fn OpenProcess(access: u32, inherit: i32, pid: u32) -> isize;
        pub fn AssignProcessToJobObject(job: isize, process: isize) -> i32;
        pub fn SetInformationJobObject(
            job: isize, class: i32, info: *mut c_void, len: u32,
        ) -> i32;
        pub fn CloseHandle(handle: isize) -> i32;
    }
}

#[cfg(target_os = "windows")]
struct WinJob(isize);

#[cfg(target_os = "windows")]
unsafe impl Send for WinJob {}
#[cfg(target_os = "windows")]
unsafe impl Sync for WinJob {}

#[cfg(target_os = "windows")]
impl Drop for WinJob {
    fn drop(&mut self) {
        if self.0 != 0 {
            unsafe { win::CloseHandle(self.0); }
        }
    }
}

#[cfg(target_os = "windows")]
fn create_job_for(pid: u32) -> Option<WinJob> {
    unsafe {
        let job = win::CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
        if job == 0 { return None; }

        let mut info = std::mem::zeroed::<win::ExtLimitInfo>();
        info.basic.limit_flags = win::JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        win::SetInformationJobObject(
            job,
            win::JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            &mut info as *mut _ as *mut _,
            std::mem::size_of::<win::ExtLimitInfo>() as u32,
        );

        let proc_handle = win::OpenProcess(
            win::PROCESS_TERMINATE | win::PROCESS_SET_QUOTA,
            0,
            pid,
        );
        if proc_handle != 0 {
            win::AssignProcessToJobObject(job, proc_handle);
            win::CloseHandle(proc_handle);
        }

        Some(WinJob(job))
    }
}

// ── Tauri entry point ─────────────────────────────────────────────────────────

#[tauri::command]
fn get_api_port(state: tauri::State<'_, ApiPort>) -> u16 {
    *state.0.lock().unwrap()
}

#[tauri::command]
fn get_api_token(state: tauri::State<'_, ApiToken>) -> String {
    state.0.lock().unwrap().clone()
}

/// First port in PORT_RANGE we can bind. The sidecar binds it for real a moment later, so this is
/// just a reservation - the same small window the sidecar had when it picked its own port.
fn pick_port() -> u16 {
    for port in PORT_RANGE {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
    }
    PORT_RANGE.start
}

/// 32 random bytes as hex, for the token the sidecar will expect on every request.
fn make_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("OS randomness unavailable");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(ApiPort(Mutex::new(PORT_RANGE.start)))
        .manage(ApiToken(Mutex::new(String::new())))
        .manage(SidecarChild(Mutex::new(None)))
        .setup(|app| {
            #[cfg(not(debug_assertions))]
            {
                use tauri_plugin_shell::ShellExt;

                // Hand the sidecar its port and token instead of reading them back off its
                // stdout. The webview can ask for them the moment it loads, and nothing depends on
                // us being able to capture output from an elevated child process.
                let port = pick_port();
                let token = make_token();
                *app.state::<ApiPort>().0.lock().unwrap() = port;
                *app.state::<ApiToken>().0.lock().unwrap() = token.clone();

                let shell = app.shell();
                let sidecar = shell.sidecar("hub-czn-api")
                    .expect("hub-czn-api sidecar not found in binaries/")
                    .envs(HashMap::from([
                        ("HUB_CZN_PORT".to_string(), port.to_string()),
                        ("HUB_CZN_API_TOKEN".to_string(), token),
                    ]));

                let (mut rx, child) = sidecar.spawn()
                    .expect("Failed to spawn hub-czn-api sidecar");

                let pid = child.pid();

                *app.state::<SidecarChild>().0.lock().unwrap() = Some(SidecarState {
                    child,
                    pid,
                    #[cfg(target_os = "windows")]
                    _job: create_job_for(pid),
                });

                // Nothing is parsed out of this any more, but the pipe still has to be drained or
                // the sidecar blocks once it fills up.
                tauri::async_runtime::spawn(async move {
                    while rx.recv().await.is_some() {}
                });
            }
            #[cfg(debug_assertions)]
            let _ = app;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Explicit cleanup on graceful close — belt-and-suspenders
                // alongside the Job Object (which handles forced kills).
                if let Some(state) = window
                    .app_handle()
                    .state::<SidecarChild>()
                    .0.lock().unwrap().take()
                {
                    let _ = state.child.kill();
                    kill_tree(state.pid);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_api_port, get_api_token])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
