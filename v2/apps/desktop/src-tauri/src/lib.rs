#[tauri::command]
fn integration_catalog() -> serde_json::Value {
    serde_json::to_value(rust_companion_v2_integrations::provider_catalog()).unwrap_or_default()
}

#[tauri::command]
fn architecture_version() -> &'static str {
    "2.0-foundation"
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            integration_catalog,
            architecture_version
        ])
        .run(tauri::generate_context!())
        .expect("error while running Rust Companion+ 2.0");
}
