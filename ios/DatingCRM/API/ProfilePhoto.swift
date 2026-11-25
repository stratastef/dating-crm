import Foundation

/// One of the user's own photos on the server.
struct ProfilePhoto: Codable, Identifiable, Equatable {
    let id: Int
    /// 1 is the best photo. nil, like `reason`, until the photos are ranked.
    var rank: Int?
    var reason: String?
    /// The light edit on offer, to accept or reject. nil when there is none.
    var suggestedEdit: PhotoEdit?
    /// The edit the user accepted. nil while the photo is as uploaded.
    var edit: PhotoEdit?
}

/// A light edit the server applies to the uploaded pixels with ordinary image code. Nothing is generated.
struct PhotoEdit: Codable, Equatable {
    /// Left, top, right, bottom as fractions of the width and height. nil keeps the whole photo.
    var crop: [Double]?
    /// 1 changes nothing; below is darker, above brighter.
    var exposure: Double
    /// 1 changes nothing; below is less saturated, above more.
    var colour: Double

    /// The changes in words, for the offer: "crop, brighter".
    var summary: String {
        var parts: [String] = []
        if crop != nil { parts.append("crop") }
        if exposure != 1 { parts.append(exposure > 1 ? "brighter" : "darker") }
        if colour != 1 { parts.append(colour > 1 ? "more colour" : "less colour") }
        return parts.joined(separator: ", ")
    }
}
