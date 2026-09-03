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
    #[allow(dead_code)]
    child: CommandChild,
    #[allow(dead_code)]
    pid:   u32,
}

struct SidecarChild(Mutex<Option<SidecarState>>);

// ── Sidecar shutdown ───────────────────────────────────────────────────────
//
// This used to be a Job Object with KILL_ON_JOB_CLOSE, so the OS killed the sidecar whenever
// hub-czn.exe went away, with no cleanup code required. That guarantee was the problem: a capture
// leaves a redirect in the hosts file and the CA in the machine trust store, and being killed
// outright meant neither came back out. The game was then unable to connect until the app was
// launched again.
//
// So the sidecar now watches us instead. We pass it our PID, it waits for us to exit, undoes both,
// and exits on its own. We do not kill it at all - killing it is what broke this.
//
// The trade: an orphaned sidecar used to be impossible and is now merely unlikely, since it needs
// both the watcher and its deadline to fail. See api/shutdown.py.

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
                        // Our PID, so it knows what to watch for and when to clean up.
                        ("HUB_CZN_PARENT_PID".to_string(), std::process::id().to_string()),
                    ]));

                let (mut rx, child) = sidecar.spawn()
                    .expect("Failed to spawn hub-czn-api sidecar");

                let pid = child.pid();

                *app.state::<SidecarChild>().0.lock().unwrap() = Some(SidecarState { child, pid });

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
                // Deliberately does not kill the sidecar. It is watching our PID and will undo the
                // hosts redirect and the certificate trust once we are gone, which a kill prevents.
                let _ = window;
            }
        })
        .invoke_handler(tauri::generate_handler![get_api_port, get_api_token])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
