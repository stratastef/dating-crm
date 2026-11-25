import PhotosUI
import SwiftUI

/// The user's own photos: upload, rank, and accept or reject the light edit offered for a photo.
/// Nothing here is sent to a dating app: the user changes their profile themselves.
struct PhotosView: View {
    let client: APIClient

    @State private var photos: [ProfilePhoto] = []
    @State private var picked: [PhotosPickerItem] = []
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            if photos.isEmpty && !busy {
                Text("Add your photos, then rank them.").foregroundStyle(.secondary)
            }
            ForEach(photos) { photo in
                PhotoRow(client: client, photo: photo) { decided in
                    if let index = photos.firstIndex(where: { $0.id == decided.id }) {
                        photos[index] = decided
                    }
                }
            }
        }
        .navigationTitle("Photos")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if busy {
                ProgressView()
            }
            PhotosPicker("Add", selection: $picked, matching: .images)
            Button("Rank") {
                Task { await run { photos = try await client.rankPhotos() } }
            }
            .disabled(photos.isEmpty || busy)
        }
        .onChange(of: picked) {
            guard !picked.isEmpty else { return }
            let items = picked
            picked = []
            Task { await upload(items) }
        }
        .task { await run { photos = try await client.photos() } }
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        await run {
            for item in items {
                // Re-encoded as JPEG: the library may hold HEIC, which the server does not take.
                guard let data = try await item.loadTransferable(type: Data.self),
                      let jpeg = UIImage(data: data)?.jpegData(compressionQuality: 0.9)
                else { continue }
                photos.append(try await client.uploadPhoto(jpeg: jpeg))
            }
        }
    }

    private func run(_ work: () async throws -> Void) async {
        busy = true
        defer { busy = false }
        do {
            try await work()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// One photo with its rank and reason, and the edit on offer as a preview with Accept and Reject.
private struct PhotoRow: View {
    let client: APIClient
    let photo: ProfilePhoto
    let onDecision: (ProfilePhoto) -> Void

    @State private var image: UIImage?
    @State private var preview: UIImage?
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                picture(image, label: "Photo")
                VStack(alignment: .leading) {
                    Text(photo.rank.map { "#\($0)" } ?? "Not ranked").font(.headline)
                    if let reason = photo.reason {
                        Text(reason).font(.subheadline)
                    }
                }
            }
            if let edit = photo.suggestedEdit {
                Text("Suggested edit: \(edit.summary)").font(.caption).foregroundStyle(.secondary)
                picture(preview, label: "Preview of the suggested edit")
                HStack {
                    Button("Accept") { decide(accept: true) }
                    Button("Reject", role: .destructive) { decide(accept: false) }
                }
                // Without this a tap anywhere in the row would trigger both buttons.
                .buttonStyle(.borderless)
            }
            if let error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
        }
        // Reloads when an edit is accepted, since the image then changes; the preview when a new one is offered.
        .task(id: photo) {
            do {
                image = UIImage(data: try await client.photoImage(id: photo.id))
                preview = photo.suggestedEdit == nil ? nil : UIImage(data: try await client.photoPreview(id: photo.id))
                error = nil
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    @ViewBuilder
    private func picture(_ image: UIImage?, label: String) -> some View {
        if let image {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .frame(maxWidth: 140, maxHeight: 140)
                .accessibilityLabel(label)
        } else {
            ProgressView().frame(width: 140, height: 140)
        }
    }

    private func decide(accept: Bool) {
        Task {
            do {
                onDecision(try await client.decideEdit(photoID: photo.id, accept: accept))
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
