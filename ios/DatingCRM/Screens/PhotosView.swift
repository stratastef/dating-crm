import PhotosUI
import SwiftUI

/// The user's own photos, lead photo first: add, rank, reorder and delete them, and compare the light edit on offer
/// with the original before accepting it. Nothing here is sent to a dating app: the user changes their profile themselves.
struct PhotosView: View {
    let client: APIClient

    @State private var photos: [ProfilePhoto] = []
    @State private var picked: [PhotosPickerItem] = []
    @State private var busy = false
    @State private var error: String?
    @State private var deleting: ProfilePhoto?

    var body: some View {
        List {
            if let error {
                ErrorRow(text: error) { await run("Your photos did not load.") { photos = try await client.photos() } }
            }
            if photos.isEmpty && !busy {
                Text("Add your photos, then rank them. The first one is your lead photo.")
                    .fontDesign(.serif)
                    .foregroundStyle(.secondaryText)
            }
            ForEach(photos) { photo in
                PhotoRow(client: client, photo: photo, isLead: photo.id == photos.first?.id) { decided in
                    if let index = photos.firstIndex(where: { $0.id == decided.id }) {
                        photos[index] = decided
                    }
                }
            }
            .onMove(perform: move)
            .onDelete { deleting = $0.first.map { photos[$0] } }
        }
        .navigationTitle("Photos")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if busy {
                ProgressView()
            }
            PhotosPicker("Add", selection: $picked, matching: .images)
            Button("Rank") {
                Task { await run("The photos were not ranked.") { photos = try await client.rankPhotos() } }
            }
            .disabled(photos.isEmpty || busy)
            EditButton().disabled(photos.isEmpty)
        }
        .confirmationDialog(
            "Delete this photo?",
            isPresented: Binding { deleting != nil } set: { if !$0 { deleting = nil } },
            titleVisibility: .visible,
            presenting: deleting
        ) { photo in
            Button("Delete photo", role: .destructive) {
                Task {
                    await run("The photo was not deleted.") {
                        try await client.deletePhoto(id: photo.id)
                        photos.removeAll { $0.id == photo.id }
                    }
                }
            }
        } message: { _ in
            Text("It is deleted from the server too. This cannot be undone.")
        }
        .onChange(of: picked) {
            guard !picked.isEmpty else { return }
            let items = picked
            picked = []
            Task { await upload(items) }
        }
        .task { await run("Your photos did not load.") { photos = try await client.photos() } }
    }

    private func move(from source: IndexSet, to destination: Int) {
        let before = photos
        photos.move(fromOffsets: source, toOffset: destination)
        let ids = photos.map(\.id)
        Task {
            await run("The new order was not saved.") {
                do {
                    photos = try await client.orderPhotos(ids: ids)
                } catch {
                    photos = before
                    throw error
                }
            }
        }
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        await run("A photo was not added.") {
            for item in items {
                // Re-encoded as JPEG: the library may hold HEIC, which the server does not take.
                guard let data = try await item.loadTransferable(type: Data.self),
                      let jpeg = UIImage(data: data)?.jpegData(compressionQuality: 0.9)
                else { continue }
                photos.append(try await client.uploadPhoto(jpeg: jpeg))
            }
        }
    }

    /// Runs `work`; on failure shows `failed` with what to do. Tapping the error reloads the photos.
    private func run(_ failed: String, _ work: () async throws -> Void) async {
        busy = true
        defer { busy = false }
        do {
            try await work()
            error = nil
        } catch {
            self.error = "\(failed) Check your connection, then tap to try again."
        }
    }
}

/// One photo: "Lead photo" on the first, Claude's reason, and the edit on offer next to the original, with Accept
/// and Keep original.
private struct PhotoRow: View {
    let client: APIClient
    let photo: ProfilePhoto
    let isLead: Bool
    let onDecision: (ProfilePhoto) -> Void

    @State private var image: UIImage?
    @State private var preview: UIImage?
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let edit = photo.suggestedEdit {
                caption
                VStack(alignment: .leading, spacing: 4) {
                    AIMarker(.suggests)
                    Text("Edit: \(edit.summary)").font(.subheadline)
                }
                // Side by side at every text size: the point is to compare them.
                HStack(alignment: .top, spacing: 10) {
                    picture(image, caption: "Original", label: "Original photo")
                    picture(preview, caption: "Edited", label: "Photo with the suggested edit")
                }
                AdaptiveStack(spacing: 10) {
                    Button("Accept edit") { decide(accept: true) }.buttonStyle(.primaryCapsule)
                    Button("Keep original") { decide(accept: false) }.buttonStyle(.secondaryCapsule)
                }
            } else {
                AdaptiveStack(spacing: 14) {
                    thumbnail
                    caption
                }
            }
            if let error {
                ErrorRow(text: error) { await load() }
            }
        }
        .padding(.vertical, 4)
        // Reloads when an edit is accepted, since the image then changes; the preview when a new one is offered.
        .task(id: photo) { await load() }
    }

    @ViewBuilder private var caption: some View {
        if isLead || photo.reason != nil {
            VStack(alignment: .leading, spacing: 4) {
                if isLead {
                    Text("Lead photo").font(.headline)
                }
                if let reason = photo.reason {
                    Text(reason).font(.subheadline)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private var thumbnail: some View {
        if let image {
            Image(uiImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: 88, height: 88)
                .clipShape(.rect(cornerRadius: 12))
                .accessibilityLabel("Photo")
        } else {
            ProgressView().frame(width: 88, height: 88)
        }
    }

    private func picture(_ image: UIImage?, caption: String, label: String) -> some View {
        VStack(spacing: 6) {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .clipShape(.rect(cornerRadius: 12))
                    .frame(maxHeight: 240)
                    .accessibilityLabel(label)
            } else {
                ProgressView().frame(height: 160)
            }
            Text(caption).font(.footnote).foregroundStyle(.secondaryText).accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
    }

    private func load() async {
        do {
            image = UIImage(data: try await client.photoImage(id: photo.id))
            preview = photo.suggestedEdit == nil ? nil : UIImage(data: try await client.photoPreview(id: photo.id))
            error = nil
        } catch {
            if !Task.isCancelled {
                self.error = "This photo did not load. Check your connection, then tap to try again."
            }
        }
    }

    private func decide(accept: Bool) {
        Task {
            do {
                onDecision(try await client.decideEdit(photoID: photo.id, accept: accept))
            } catch {
                self.error = "Not saved. Check your connection, then tap Accept edit or Keep original again."
            }
        }
    }
}
