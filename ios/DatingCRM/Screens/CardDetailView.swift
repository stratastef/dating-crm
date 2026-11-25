import SwiftUI

/// One card: move it to another stage, edit notes, next action and due date, and read its messages.
struct CardDetailView: View {
    let client: APIClient
    let onSaved: (Card) -> Void

    @State private var saved: Card
    @State private var card: Card
    @State private var messages: [Message] = []
    @State private var error: String?
    @State private var askForRating = false

    init(client: APIClient, card: Card, onSaved: @escaping (Card) -> Void) {
        self.client = client
        self.onSaved = onSaved
        _saved = State(initialValue: card)
        _card = State(initialValue: card)
    }

    var body: some View {
        Form {
            if let error {
                Text(error).foregroundStyle(.red)
            }

            Section {
                Picker("Stage", selection: $card.stage) {
                    ForEach(Stage.allCases) { Text($0.title).tag($0) }
                }
                TextField("Next action", text: nextAction)
                Toggle("Due date", isOn: hasDueDate)
                if let dueDate = card.dueDate {
                    DatePicker("Due", selection: Binding(get: { dueDate }, set: { card.dueDate = $0 }), displayedComponents: .date)
                }
            }

            Section("Notes") {
                TextField("Notes", text: $card.notes, axis: .vertical)
                    .lineLimit(3...)
            }

            Section("Messages") {
                if messages.isEmpty {
                    Text("No messages yet").foregroundStyle(.secondary)
                }
                ForEach(messages) { message in
                    VStack(alignment: .leading) {
                        Text(message.sender == .me ? "You" : card.name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(message.body)
                    }
                }
            }

            ReadSection(client: client, cardID: card.id)

            DraftSection(client: client, cardID: card.id)
        }
        .navigationTitle(card.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            Button("Save") {
                Task { await save() }
            }
            .disabled(card == saved)
        }
        .onChange(of: card.stage) {
            askForRating = card.needsDateRating
        }
        .sheet(isPresented: $askForRating) {
            DateRatingSheet(name: card.name) { rating, note in
                card.dateRating = rating
                card.dateNote = note
                Task { await save() }
            }
        }
        .task {
            do {
                messages = try await client.messages(cardID: card.id)
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    // An empty field means "no next action", which the server stores as null.
    private var nextAction: Binding<String> {
        Binding(get: { card.nextAction ?? "" }, set: { card.nextAction = $0.isEmpty ? nil : $0 })
    }

    private var hasDueDate: Binding<Bool> {
        Binding(
            get: { card.dueDate != nil },
            set: { card.dueDate = $0 ? Calendar.current.startOfDay(for: .now) : nil }
        )
    }

    private func save() async {
        do {
            saved = try await client.update(card)
            card = saved
            error = nil
            onSaved(saved)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
