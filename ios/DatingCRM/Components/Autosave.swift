import SwiftUI

extension View {
    /// Saves `value` a second after the last change, and at once when the view goes away, so leaving a screen never
    /// loses an edit. `saved` is what the server holds: nothing is sent while the two are equal, so pass `value`
    /// itself as `saved` until the screen has loaded. `save` sets the screen's error; a cancelled save sets none.
    func autosave<Value: Equatable>(_ value: Value, saved: Value, save: @escaping (Value) async -> Void) -> some View {
        task(id: value) {
            // A change within the second cancels this task and starts a new one: the debounce.
            guard value != saved, (try? await Task.sleep(for: .seconds(1))) != nil else { return }
            await save(value)
        }
        .onDisappear {
            if value != saved { Task { await save(value) } }
        }
    }
}
