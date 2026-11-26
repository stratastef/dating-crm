import SwiftUI

/// The voice questionnaire: the server's questions, answered in the user's own words. Answers save as the user
/// types; the server then rewrites the style profile every draft is written from. Push it onto a navigation stack.
struct VoiceView: View {
    let client: APIClient

    @State private var saved: Voice?
    @State private var answers: [String: String] = [:]
    @State private var error: String?

    /// The answers to send: a question left blank has no answer.
    private var answered: [String: String] {
        answers.filter { !$0.value.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    var body: some View {
        List {
            if let saved {
                Text("Answer in your own words. Drafts are written in your style, learned from these answers and your chats.")
                    .fontDesign(.serif)
                    .listRowSeparator(.hidden)
                ForEach(saved.questions, id: \.self) { question in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(question).font(.headline)
                        GrowingField(
                            label: question, prompt: "Your answer",
                            text: Binding(get: { answers[question] ?? "" }, set: { answers[question] = $0 }))
                        if let error, answered[question] != saved.answers[question] {
                            ErrorRow(text: error) { await save(answered) }
                        }
                    }
                }
            } else if let error {
                ErrorRow(text: error) { await load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Voice")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.immediately)
        .autosave(answered, saved: saved?.answers ?? answered) { await save($0) }
        // Once only: a reload on return could land before the save made on leaving, and undo it.
        .task { if saved == nil { await load() } }
    }

    private func load() async {
        do {
            let voice = try await client.voice()
            answers = voice.answers
            saved = voice
            error = nil
        } catch {
            self.error = "Your questions did not load. Check your connection, then tap to try again."
        }
    }

    private func save(_ answers: [String: String]) async {
        do {
            saved = try await client.saveAnswers(answers)
            error = nil
        } catch {
            if !Task.isCancelled {
                self.error = "Not saved. Check your connection, then tap to try again."
            }
        }
    }
}
