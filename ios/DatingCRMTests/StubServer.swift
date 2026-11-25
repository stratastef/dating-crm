import Foundation
@testable import DatingCRM

/// Stands in for the HTTP server: records each request and answers with the next queued response.
final class StubServer {
    private(set) var requests: [URLRequest] = []
    private var responses: [(status: Int, json: String)] = []

    func respond(_ json: String, status: Int = 200) {
        responses.append((status, json))
    }

    var transport: APIClient.Transport {
        { request in await self.handle(request) }
    }

    func client() -> APIClient {
        APIClient(baseURL: URL(string: "https://crm.test")!, token: "secret", transport: transport)
    }

    private func handle(_ request: URLRequest) -> (Data, URLResponse) {
        requests.append(request)
        let response = responses.removeFirst()
        return (
            Data(response.json.utf8),
            HTTPURLResponse(url: request.url!, statusCode: response.status, httpVersion: nil, headerFields: nil)!
        )
    }
}

func day(_ year: Int, _ month: Int, _ day: Int) -> Date {
    Calendar.current.date(from: DateComponents(year: year, month: month, day: day))!
}
