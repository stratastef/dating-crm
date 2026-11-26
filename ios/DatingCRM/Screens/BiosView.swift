import SwiftUI

/// Bio and prompt answers per dating app: the version the user accepted, Claude's rewrite of it in the user's voice,
/// and Accept. Nothing is written to a dating app: the user copies the accepted text into it. Push it onto a
/// navigation stack.
struct BiosView: View {
    let client: APIClient

    /// The server's `DATING_APPS`.
    private static let apps = ["tinder", "hinge", "bumble"]

    private struct PromptAnswer {
        var prompt: String
        var answer: String
    }

    private enum Step { case load, rewrite, accept }

    @State private var app = BiosView.apps[0]
    @State private var loadedApp: String?
    @State private var bio = ""
    @State private var prompts: [PromptAnswer] = []
    @State private var rewrite: Bio?
    @State private var busy = false
    @State private var failed: Step?
    @State private var needsVoice = false
    @State private var toast: Toast?

    /// What the user typed, as the server takes it: a prompt without its text is left out.
    private var current: Bio {
        Bio(
            bio: bio,
            prompts: Dictionary(
                prompts.filter { !$0.prompt.trimmingCharacters(in: .whitespaces).isEmpty }.map { ($0.prompt, $0.answer) },
                uniquingKeysWith: { first, _ in first }))
    }

    var body: some View {
        List {
            Picker("Dating app", selection: $app) {
                ForEach(Self.apps, id: \.self) { Text($0.capitalized) }
            }
            .pickerStyle(.segmented)
            .controlSize(.extraLarge)  // 44 pt segments
            .disabled(busy)
            .listRowSeparator(.hidden)
            if loadedApp == app {
                Text("Type your bio and prompt answers as they are on \(app.capitalized). Claude rewrites them in your voice. Nothing changes there until you copy it in.")
                    .fontDesign(.serif)
                    .listRowSeparator(.hidden)
                Section {
                    GrowingField(label: "Bio", prompt: "Your bio", text: $bio)
                } header: {
                    Text("Bio").foregroundStyle(Color.primary)
                }
                Section {
                    ForEach(prompts.indices, id: \.self) { index in
                        VStack(alignment: .leading, spacing: 0) {
                            GrowingField(label: "Prompt", prompt: "Prompt", text: field(index, \.prompt)).font(.headline)
                            GrowingField(label: "Answer", prompt: "Your answer", text: field(index, \.answer))
                        }
                    }
                    .onDelete { prompts.remove(atOffsets: $0) }
                    Button("Add prompt") { prompts.append(PromptAnswer(prompt: "", answer: "")) }
                        .frame(minHeight: 44)
                } header: {
                    Text("Prompts").foregroundStyle(Color.primary)
                }
                Section {
                    Button("Rewrite in my voice") { Task { await rewriteCurrent() } }
                        .buttonStyle(.primaryCapsule)
                        .disabled(busy || current == Bio())
                    if needsVoice {
                        NavigationLink("Answer the voice questions first, so Claude knows your style") {
                            VoiceView(client: client)
                        }
                        .frame(minHeight: 44)
                    }
                    if failed == .rewrite {
                        ErrorRow(text: "No rewrite came back. Check your connection, then tap to try again.") {
                            await rewriteCurrent()
                        }
                    }
                }
                if let rewrite {
                    rewriteSection(rewrite)
                }
            } else if failed == .load {
                ErrorRow(text: "Your bio did not load. Check your connection, then tap to try again.") { await load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Bios and prompts")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if busy {
                ProgressView()
            }
        }
        .scrollDismissesKeyboard(.immediately)
        // Not again on return from Voice: that would drop what the user typed.
        .task(id: app) { if loadedApp != app { await load() } }
        .toast($toast)
    }

    private func rewriteSection(_ rewrite: Bio) -> some View {
        Section {
            AIMarker(.suggests)
            if !rewrite.bio.isEmpty {
                Text(rewrite.bio)
            }
            ForEach(ordered(rewrite.prompts), id: \.prompt) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.prompt).font(.headline)
                    Text(item.answer)
                }
            }
            AdaptiveStack(spacing: 10) {
                Button("Accept") { Task { await accept(rewrite) } }.buttonStyle(.primaryCapsule)
                Button("Rewrite again") { Task { await rewriteCurrent() } }.buttonStyle(.secondaryCapsule)
            }
            .disabled(busy)
            if failed == .accept {
                ErrorRow(text: "Not saved. Check your connection, then tap to try again.") { await accept(rewrite) }
            }
        } header: {
            Text("Rewrite for \(app.capitalized)").foregroundStyle(Color.primary)
        }
        .textSelection(.enabled)
    }

    /// Bounds-checked: a deleted row's field can still read its index once after the removal.
    private func field(_ index: Int, _ part: WritableKeyPath<PromptAnswer, String>) -> Binding<String> {
        Binding(
            get: { prompts.indices.contains(index) ? prompts[index][keyPath: part] : "" },
            set: { if prompts.indices.contains(index) { prompts[index][keyPath: part] = $0 } })
    }

    /// The prompts in the order the user typed them, then any others by their text.
    private func ordered(_ answers: [String: String]) -> [PromptAnswer] {
        let place = { (prompt: String) in prompts.firstIndex { $0.prompt == prompt } ?? prompts.count }
        return answers
            .sorted { (place($0.key), $0.key) < (place($1.key), $1.key) }
            .map { PromptAnswer(prompt: $0.key, answer: $0.value) }
    }

    private func load() async {
        rewrite = nil
        needsVoice = false
        failed = nil
        do {
            let accepted = try await client.bio(app: app)
            bio = accepted.bio
            prompts = accepted.prompts.sorted { $0.key < $1.key }.map { PromptAnswer(prompt: $0.key, answer: $0.value) }
            loadedApp = app
        } catch {
            if !Task.isCancelled { failed = .load }
        }
    }

    private func rewriteCurrent() async {
        busy = true
        defer { busy = false }
        do {
            rewrite = try await client.rewriteBio(app: app, current)
            needsVoice = false
            failed = nil
        } catch let error as APIError where error.status == 409 {
            needsVoice = true
            failed = nil
        } catch {
            failed = .rewrite
        }
    }

    private func accept(_ accepted: Bio) async {
        busy = true
        defer { busy = false }
        do {
            let saved = try await client.acceptBio(app: app, accepted)
            bio = saved.bio
            prompts = ordered(saved.prompts)
            rewrite = nil
            failed = nil
            toast = Toast(text: "Saved. Copy it into \(app.capitalized).")
        } catch {
            failed = .accept
        }
    }
}
