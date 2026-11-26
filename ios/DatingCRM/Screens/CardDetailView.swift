import SwiftUI

/// One card: the match's face as its header, then two tabs. Chat is the conversation as bubbles, with the handover
/// banner at its end and the draft docked below like a composer (`DraftComposer`). Details holds the stage, next
/// action, due date, notes and match read. The card opens on Chat in Matched and Chatting and on Details from
/// Number swapped on. Scrolled past the header, the navigation bar shows the face and name instead.
struct CardDetailView: View {
    enum Tab: String, CaseIterable, Identifiable {
        case chat = "Chat", details = "Details"

        var id: Self { self }
    }

    let client: APIClient
    let onSaved: (Card) -> Void

    @State private var saved: Card
    @State private var card: Card
    @State private var tab: Tab
    @State private var messages: [Message] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var askForRating = false
    @State private var collapsed = false
    @State private var toast: Toast?
    @State private var needsVoice = false
    @State private var position = ScrollPosition(edge: .bottom)

    init(client: APIClient, card: Card, onSaved: @escaping (Card) -> Void) {
        self.client = client
        self.onSaved = onSaved
        _saved = State(initialValue: card)
        _card = State(initialValue: card)
        _tab = State(initialValue: card.stage.chatsInApp ? .chat : .details)
    }

    var body: some View {
        Group {
            switch tab {
            case .chat: chat
            case .details: details
            }
        }
        .safeAreaBar(edge: .top) {
            Picker("Show", selection: $tab) {
                ForEach(Tab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .controlSize(.large)
            .padding(.horizontal, 14)
            .padding(.bottom, 6)
        }
        .navigationTitle(card.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                // The header's face and name, once it scrolled away.
                if collapsed {
                    HStack(spacing: 8) {
                        Avatar(name: card.name, photo: card.leadPhotoUrl, size: 32)
                        Text(card.name).font(.headline)
                    }
                }
            }
            if tab == .details {
                ToolbarItem(placement: .primaryAction) {
                    Button("Save") {
                        Task { await save() }
                    }
                    .disabled(card == saved)
                }
            }
        }
        .navigationDestination(isPresented: $needsVoice) { VoiceView(client: client) }
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
        .task { await load() }
    }

    private static let headerHeight: CGFloat = 340

    /// The match's face filling the header, with name, stage, dating app and how long since they matched on glass.
    private var header: some View {
        FacePhoto(name: card.name, photo: card.leadPhotoUrl)
            .frame(height: Self.headerHeight)
            .frame(maxWidth: .infinity)
            .overlay(alignment: .bottomLeading) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(card.name).font(.title.bold())
                    Text(caption).font(.subheadline)
                }
                .foregroundStyle(Color.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background {
                    // As on Review's plates: the fill keeps `.primary` text at 4.5:1 over any photo.
                    RoundedRectangle(cornerRadius: 20)
                        .fill(Color(uiColor: .systemBackground).opacity(0.72))
                        .glassEffect(.regular, in: .rect(cornerRadius: 20))
                }
                .padding(14)
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(.isHeader)
            }
    }

    /// "Chatting on Tinder, matched 3d ago".
    private var caption: String {
        "\(card.stage.title) on \(card.app.capitalized)" + (card.createdAt.map { ", matched \(RelativeTime.ago($0))" } ?? "")
    }

    private var chat: some View {
        ScrollView {
            VStack(spacing: 0) {
                header
                LazyVStack(spacing: 6) {
                    if let error {
                        ErrorRow(text: error) { await load() }
                    }
                    if loaded && messages.isEmpty {
                        Text("No messages yet")
                            .fontDesign(.serif)
                            .foregroundStyle(.secondaryText)
                            .padding(.vertical, 20)
                    }
                    ForEach(Array(messages.enumerated()), id: \.element.id) { index, message in
                        // A time over the first message, and over each that came an hour or more after the last.
                        if index == 0 || message.sentAt.timeIntervalSince(messages[index - 1].sentAt) >= 3600 {
                            Text("\(RelativeTime.day(message.sentAt)) \(message.sentAt.formatted(date: .omitted, time: .shortened))")
                                .font(.caption)
                                .foregroundStyle(.secondaryText)
                                .padding(.top, 8)
                        }
                        Bubble(message: message, name: card.name, last: index == messages.count - 1)
                    }
                    if let planned = card.plannedSend {
                        PlannedBubble(draft: planned).padding(.top, 8)
                    }
                    if let handover = card.handover {
                        HandoverBanner(
                            client: client, card: card, handover: handover,
                            message: messages.last { $0.sender == .them && $0.handover?.isEmpty == false },
                            copied: { toast = Toast(text: "Copied") }, changed: reload
                        )
                        .padding(.top, 8)
                    }
                }
                .padding(14)
            }
        }
        // Opens on the newest message (`load()` scrolls there), and stays there when the composer changes size.
        .scrollPosition($position)
        .defaultScrollAnchor(.bottom, for: .sizeChanges)
        .scrollDismissesKeyboard(.interactively)
        .onScrollGeometryChange(for: Bool.self, of: pastHeader) { collapsed = $1 }
        .toast($toast)
        .safeAreaBar(edge: .bottom) {
            DraftComposer(
                client: client, card: card, toast: $toast, needsVoice: $needsVoice, reload: reload, sent: loadAfterSend
            )
        }
    }

    private var details: some View {
        List {
            header
                .listRowInsets(EdgeInsets())
                .listRowSeparator(.hidden)
            if let error {
                ErrorRow(text: error) { await load() }
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
            Section {
                TextField("Notes", text: $card.notes, axis: .vertical)
                    .lineLimit(3...)
            } header: {
                Text("Notes").foregroundStyle(Color.primary)
            }
            ReadSection(client: client, cardID: card.id)
        }
        .scrollDismissesKeyboard(.immediately)
        .onScrollGeometryChange(for: Bool.self, of: pastHeader) { collapsed = $1 }
    }

    /// The header has scrolled out of sight, so the navigation bar takes over the face and name.
    private func pastHeader(_ geometry: ScrollGeometry) -> Bool {
        geometry.contentOffset.y + geometry.contentInsets.top > Self.headerHeight - 40
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

    private func load() async {
        do {
            let fresh = try await client.card(id: card.id)
            messages = try await client.messages(cardID: card.id)
            // Unsaved Details edits stay; everything else is the server's.
            let edited = card != saved ? card : nil
            saved = fresh
            card = fresh
            if let edited {
                card.stage = edited.stage
                card.notes = edited.notes
                card.nextAction = edited.nextAction
                card.dueDate = edited.dueDate
            }
            error = nil
        } catch {
            self.error = "The card did not load. Check your connection, then tap to try again."
        }
        loaded = true
        position.scrollTo(edge: .bottom)
    }

    /// After the server changed the card: a list behind it may need to move it.
    private func reload() async {
        await load()
        onSaved(saved)
    }

    /// After a Send. The worker sends once Undo's 5 seconds are over, so the card reloads until the message is in
    /// the chat.
    private func loadAfterSend() async {
        let before = messages.count
        await reload()  // the draft leaves the composer
        // shortcut: gives up after 12 seconds; a slower send shows on the next visit. Refresh on a push if it lags.
        for _ in 0..<4 {
            try? await Task.sleep(for: .seconds(3))
            await load()
            if messages.count > before { break }
        }
        onSaved(saved)
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

/// One message: the match's on the left on the fill, the user's on the right in the label color. Under a message
/// autopilot sent alone, the Autopilot marker; under the last one, how long ago it was sent.
private struct Bubble: View {
    let message: Message
    let name: String
    let last: Bool

    var body: some View {
        let mine = message.sender == .me
        VStack(alignment: mine ? .trailing : .leading, spacing: 3) {
            Text(message.body)
                .foregroundStyle(mine ? Color(uiColor: .systemBackground) : Color.primary)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(mine ? Color.primary : Color(uiColor: .secondarySystemBackground), in: .rect(cornerRadius: 20))
            if message.sentByAutopilot || last {
                AdaptiveStack(spacing: 6) {
                    if message.sentByAutopilot {
                        AIMarker(.autopilot)
                    }
                    if last {
                        Text(RelativeTime.ago(message.sentAt))
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
        .padding(mine ? .leading : .trailing, 48)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(mine ? "You" : name): \(message.body)")
        .accessibilityValue(
            [message.sentByAutopilot ? AIMarker.Kind.autopilot.spokenLabel : nil, last ? RelativeTime.ago(message.sentAt) : nil]
                .compactMap(\.self).joined(separator: ", "))
    }
}

/// Autopilot's planned send, after the last message: the user's bubble, outlined because it is not sent yet, then
/// when it goes out and why ("Goes out around 20:15 · they take their time"). Send now and Hold come next (#72).
private struct PlannedBubble: View {
    let draft: Draft

    var body: some View {
        VStack(alignment: .trailing, spacing: 3) {
            Text(draft.text)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Color.primary, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
            AdaptiveStack(spacing: 6) {
                AIMarker(.autopilot)
                Text(when).font(.footnote).foregroundStyle(.secondaryText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.leading, 48)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Planned by autopilot: \(draft.text)")
        .accessibilityValue(when)
    }

    private var when: String {
        let time = draft.sendAt.map { "Goes out \(RelativeTime.around($0))" } ?? "Goes out soon"
        guard let reason = draft.timingReason, !reason.isEmpty else { return time }
        return "\(time) · \(reason)"
    }
}
