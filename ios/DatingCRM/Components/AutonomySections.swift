import SwiftUI

/// One list section per job with its four autonomy levels, each with what it lets the app do. For the Autopilot
/// screen and the setup step, which own the levels and save the choice.
struct AutonomySections: View {
    let levels: [String: AutonomyLevel]
    let choose: (_ job: String, _ level: AutonomyLevel) -> Void

    /// The server's job keys, in screen order, with the glossary's names.
    static let jobs = [(key: "chat", title: "Chat"), (key: "profile", title: "Optimize profiles"), (key: "swipe", title: "Swipe")]

    var body: some View {
        ForEach(Self.jobs, id: \.key) { job in
            Section {
                Picker(job.title, selection: Binding { levels[job.key] ?? .off } set: { choose(job.key, $0) }) {
                    ForEach(AutonomyLevel.allCases) { level in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(level.title)
                            Text(level.summary)
                                .font(.subheadline)
                                .foregroundStyle(.secondaryText)
                        }
                        .tag(level)
                    }
                }
                .pickerStyle(.inline)
                .labelsHidden()
            } header: {
                Text(job.title).foregroundStyle(Color.primary)
            }
        }
    }
}
