import SwiftUI

/// One card: the match's face as its header, then two tabs. Chat is the conversation as bubbles, with the handover
/// banner at its end and the draft docked below like a composer (`DraftComposer`). Details holds the stage, next
/// action, due date, notes, the date's rating and note, and the match read; edits save as the user makes them. The
/// card opens on Chat in Matched and Chatting and on Details from Number swapped on. Scrolled past the header, the
/// navigation bar shows the face and name instead.
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
    @State private var saveError: String?
    @State private var askForRating = false
    @State private var collapsed = false
    @State private var toast: Toast?
    @State private var needsVoice = false
    @State private var position = ScrollPosition(edge: .bottom)
    @State private var handoverFired = 0

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
        }
        .navigationDestination(isPresented: $needsVoice) { VoiceView(client: client) }
        .onChange(of: card.stage) {
            askForRating = card.needsDateRating
        }
        .sheet(isPresented: $askForRating) {
            DateRatingSheet(name: card.name) { rating, note in
                card.dateRating = rating
                card.dateNote = note
            }
        }
        // On the whole card, not the Details tab: switching to Chat keeps the debounce, leaving saves at once.
        .autosave(Edits(card), saved: Edits(saved)) { await save($0) }
        .task { await load() }
        .sensoryFeedback(.alert, trigger: handoverFired)
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
                Picker("Stage", selection: stage) {
                    ForEach(Stage.allCases) { Text($0.title).tag($0) }
                }
                .frame(minHeight: 44)
                failure(\.stage)
            }
            Section {
                GrowingField(label: "Next action", prompt: "What to do next", text: nextAction)
                failure(\.nextAction)
                Toggle("Due date", isOn: hasDueDate)
                    .frame(minHeight: 44)
                if let dueDate = card.dueDate {
                    DatePicker("Due", selection: Binding(get: { dueDate }, set: { card.dueDate = $0 }), displayedComponents: .date)
                        .frame(minHeight: 44)
                }
                failure(\.dueDate)
            } header: {
                Text("Next action").foregroundStyle(Color.primary)
            }
            Section {
                GrowingField(label: "Notes", prompt: "What to remember about them", text: $card.notes)
                failure(\.notes)
            } header: {
                Text("Notes").foregroundStyle(Color.primary)
            }
            if card.dateRating != nil || card.needsDateRating {
                RatingPicker(title: "The date", rating: $card.dateRating)
                Section {
                    failure(\.dateRating)
                    GrowingField(label: "Date note", prompt: "What stood out", text: dateNote)
                    failure(\.dateNote)
                } header: {
                    Text("Date note").foregroundStyle(Color.primary)
                }
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

    private var dateNote: Binding<String> {
        Binding(get: { card.dateNote ?? "" }, set: { card.dateNote = $0 })
    }

    /// The save error, under a field whose edit the server does not have yet.
    @ViewBuilder private func failure<Value: Equatable>(_ field: KeyPath<Edits, Value>) -> some View {
        if let saveError, Edits(card)[keyPath: field] != Edits(saved)[keyPath: field] {
            ErrorRow(text: saveError) { await save(Edits(card)) }
        }
    }

    /// The stage as the user picks it. Picking Date set plays the hour at once, before the save.
    private var stage: Binding<Stage> {
        Binding {
            card.stage
        } set: { picked in
            if picked == .dateSet && card.stage != .dateSet { HourRing.play() }
            card.stage = picked
        }
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
            take(fresh)
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

    /// Takes the server's copy of the card. Details edits it does not have yet stay; everything else is the server's.
    private func take(_ fresh: Card) {
        // What happened while the card is open; the first load only shows how it already was.
        if loaded {
            if fresh.handover == .pending && card.handover != .pending { handoverFired += 1 }
            if fresh.stage == .dateSet && card.stage != .dateSet { HourRing.play() }  // Full autopilot set the date
        }
        let edits = Edits(card)
        let unsaved = edits != Edits(saved)
        saved = fresh
        card = fresh
        if unsaved { edits.apply(to: &card) }
    }

    private func save(_ edits: Edits) async {
        var changed = saved
        edits.apply(to: &changed)
        do {
            take(try await client.update(changed))
            saveError = nil
            onSaved(saved)
        } catch {
            if !Task.isCancelled {
                saveError = "Not saved. Check your connection, then tap to try again."
            }
        }
    }
}

/// What the Details tab edits. The autosave compares these, not the whole card, whose summary only the server sets.
private struct Edits: Equatable {
    var stage: Stage
    var notes: String
    var nextAction: String?
    var dueDate: Date?
    var dateRating: Int?
    var dateNote: String?

    init(_ card: Card) {
        (stage, notes, nextAction, dueDate, dateRating, dateNote) =
            (card.stage, card.notes, card.nextAction, card.dueDate, card.dateRating, card.dateNote)
    }

    func apply(to card: inout Card) {
        (card.stage, card.notes, card.nextAction, card.dueDate, card.dateRating, card.dateNote) =
            (stage, notes, nextAction, dueDate, dateRating, dateNote)
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
