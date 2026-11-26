import Foundation
import Testing
@testable import DatingCRM

struct PhoneNumberTests {
    @Test func joinsTheCountrysCodeAndTheNumberWithoutAPlusToType() {
        #expect(PhoneNumber.e164(region: "CA", national: "403 333 3333") == "+14033333333")
        #expect(PhoneNumber.e164(region: "DE", national: "0170 1234567") == "+491701234567")  // trunk 0 not dialled
        #expect(PhoneNumber.e164(region: "IT", national: "06 1234 5678") == "+390612345678")  // Italy keeps its 0
    }

    @Test func aPastedFullNumberPicksItsCountry() {
        #expect(PhoneNumber.split("+44 7700 900123", near: "US")! == ("GB", "7700900123"))
        #expect(PhoneNumber.split("+1 (403) 333-3333", near: "CA")! == ("CA", "4033333333"))  // +1: the phone's own
        #expect(PhoneNumber.split("+1 415 555 0100", near: "DE")! == ("US", "4155550100"))
        #expect(PhoneNumber.split("+1 876 555 0100", near: "US")! == ("JM", "5550100"))  // Jamaica's +1 876
        #expect(PhoneNumber.split("0049 170 1234567", near: "US")! == ("DE", "1701234567"))
        #expect(PhoneNumber.split("403 333 3333", near: "CA") == nil)
    }

    @Test func groupsANorthAmericanNumberAsItIsTyped() {
        #expect(PhoneNumber.formatted("4033333333", region: "CA") == "403 333 3333")
        #expect(PhoneNumber.formatted("40333", region: "US") == "403 33")
        #expect(PhoneNumber.formatted("403", region: "US") == "403")
        #expect(PhoneNumber.formatted("0170 123", region: "DE") == "0170123")
    }

    @Test func startsOnThePhonesOwnCountry() {
        #expect(PhoneNumber.defaultRegion(Locale(identifier: "en_CA")) == "CA")
        #expect(PhoneNumber.defaultRegion(Locale(identifier: "de_DE")) == "DE")
        #expect(PhoneNumber.defaultRegion(Locale(identifier: "en")) == "US")  // no region: the United States
    }
}
