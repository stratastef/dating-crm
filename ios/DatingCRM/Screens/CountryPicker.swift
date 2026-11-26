import SwiftUI

/// Every region with its flag, name and dialing code, searchable by name or code. Choosing one dismisses the sheet.
struct CountryPicker: View {
    @Binding var region: String
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""

    private var regions: [String] {
        let all = PhoneNumber.codes.keys.sorted { PhoneNumber.name($0) < PhoneNumber.name($1) }
        let query = search.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "+"))
        guard !query.isEmpty else { return all }
        return all.filter {
            PhoneNumber.name($0).localizedCaseInsensitiveContains(query) || PhoneNumber.codes[$0]!.hasPrefix(query)
        }
    }

    var body: some View {
        NavigationStack {
            List(regions, id: \.self) { candidate in
                Button {
                    region = candidate
                    dismiss()
                } label: {
                    HStack {
                        Text(PhoneNumber.flag(candidate)).accessibilityHidden(true)
                        Text(PhoneNumber.name(candidate))
                        Spacer()
                        Text("+\(PhoneNumber.codes[candidate]!)").foregroundStyle(.secondaryText)
                        if candidate == region { Image(systemName: "checkmark").accessibilityLabel("Selected") }
                    }
                    .frame(minHeight: 44)
                }
            }
            .listStyle(.plain)
            .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "Country or code")
            .navigationTitle("Country")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
    }
}
