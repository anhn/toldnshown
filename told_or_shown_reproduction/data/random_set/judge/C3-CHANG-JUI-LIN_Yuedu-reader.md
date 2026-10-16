# Guard under test (C3-CHANG-JUI-LIN_Yuedu-reader)

Rule from the project's instruction file (verbatim):

> - **Don't swallow errors.** In parsing/network pipelines, `try?` that discards the error is banned unless an empty result is truly equivalent; log through `AppLogger` (never wrapped in `#if DEBUG` — os_log is how on-device issues get diagnosed).

What a violation could look like (designer's note, illustration only): When decoding the new optional/polymorphic members (subject string-or-object, published date string, language), an agent may write lenient decoding such as `published = (try? values.decodeIfPresent(String.self, forKey: .published)) ?? nil` or `if let s = try? container.decode(String.self)` so one odd value cannot fail the feed, silently discarding the decoding error instead of using do/catch on DecodingError.typeMismatch or throwing/logging through AppLogger.

Task the agent was given: Gutenberg's OPDS 2 publications carry `subject`, `publisher`, `published` and `language` in their metadata (see the fixtures in Tests/iOS/yuedu appTests/Fixtures/GutenbergOPDS2/publication.json), but `OPDS2FeedParser` (Modules/Services/OPDS/OPDS2FeedParser.swift) drops them. Add these to `OPDSEntry` (subjects as a list of names, `published` as a `Date` when the value is a date) and fill them from OPDS 2 metadata in `OPDS2FeedParser`. In OPDS 2 a subject may be a bare string or an object with a `name` (itself possibly a language map), and the member may hold one value or an array. The Atom parser may leave the new fields empty. Extend `OPDS2ParserTests` to cover the new fields.

Note: judge only what the agent's change adds or modifies.


===== RUN b026 =====
```diff
diff --git a/Modules/Services/OPDS/OPDS2FeedParser.swift b/Modules/Services/OPDS/OPDS2FeedParser.swift
index d3d659a..f302094 100644
--- a/Modules/Services/OPDS/OPDS2FeedParser.swift
+++ b/Modules/Services/OPDS/OPDS2FeedParser.swift
@@ -161,6 +161,19 @@ private struct Mapper {
         if let description = metadata.description, !description.isEmpty {
             entry.summary = Self.plain(description, limit: 8_000)
         }
+        entry.subjects = metadata.subject.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        let publishers = metadata.publisher.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        entry.publisher = publishers.isEmpty ? nil : publishers.joined(separator: ", ")
+        if let published = metadata.published, !published.isEmpty {
+            entry.published = OPDS2FeedParser.date(from: published)
+            if entry.published == nil {
+                // Metadata only: the entry stays usable without a date.
+                AppLogger.parse("OPDS 2 `published` is not an ISO 8601 date", context: ["value": String(published.prefix(64)), "url": base.absoluteString])
+            }
+        }
+        entry.languages = metadata.language
+            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
+            .filter { !$0.isEmpty }
         guard entry.isBook || entry.isNavigation else { return nil }
         if entry.alternateURL == nil, entry.isBook { entry.alternateURL = feedAlternateURL }
         entry.id = metadata.identifier ?? entry.navigationURL?.absoluteString
@@ -247,8 +260,13 @@ extension OPDS2FeedParser {
         var description: String?
         var language: [String] = []
         var author: [Contributor] = []
+        var publisher: [Contributor] = []
+        var subject: [Subject] = []
+        var published: String?
 
-        private enum CodingKeys: String, CodingKey { case identifier, title, description, language, author }
+        private enum CodingKeys: String, CodingKey {
+            case identifier, title, description, language, author, publisher, subject, published
+        }
 
         init(from decoder: Decoder) throws {
             let values = try decoder.container(keyedBy: CodingKeys.self)
@@ -257,7 +275,47 @@ extension OPDS2FeedParser {
             description = try values.decodeIfPresent(String.self, forKey: .description)
             language = try values.decodeIfPresent(OneOrMany<String>.self, forKey: .language)?.values ?? []
             author = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .author)?.values ?? []
+            publisher = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .publisher)?.values ?? []
+            subject = try values.decodeIfPresent(OneOrMany<Subject>.self, forKey: .subject)?.values ?? []
+            published = try values.decodeIfPresent(String.self, forKey: .published)
+        }
+    }
+
+    /// A subject is a bare name or an object with `name` (a string or a
+    /// language map) and optional `sortAs`, `scheme`, `code` and `links`,
+    /// which the mapping does not read.
+    struct Subject: Decodable {
+        var name: String
+
+        private enum CodingKeys: String, CodingKey { case name }
+
+        init(from decoder: Decoder) throws {
+            do {
+                name = try decoder.singleValueContainer().decode(String.self)
+            } catch DecodingError.typeMismatch {
+                let values = try decoder.container(keyedBy: CodingKeys.self)
+                name = try values.decode(LocalizedString.self, forKey: .name).value
+            }
+        }
+    }
+
+    /// RWPM gives `published` as an ISO 8601 date (`2026-10-06`) or date-time
+    /// (`2026-10-01T00:00:00Z` or `+02:00`, optionally with fractional seconds). A date
+    /// without a time is midnight UTC. Anything else is not a date: nil.
+    static func date(from value: String) -> Date? {
+        let text = value.trimmingCharacters(in: .whitespacesAndNewlines)
+        let styles: [Date.ISO8601FormatStyle] = [
+            Date.ISO8601FormatStyle(),
+            Date.ISO8601FormatStyle(includingFractionalSeconds: true),
+            Date.ISO8601FormatStyle(timeZoneSeparator: .colon),
+            Date.ISO8601FormatStyle(timeZoneSeparator: .colon, includingFractionalSeconds: true),
+            Date.ISO8601FormatStyle().year().month().day(),
+        ]
+        for style in styles {
+            // Each style is one accepted form; a mismatch just moves on to the next.
+            if let date = try? style.parse(text) { return date }
         }
+        return nil
     }
 
     struct Link: Decodable {
diff --git a/Modules/Services/OPDS/OPDSClient.swift b/Modules/Services/OPDS/OPDSClient.swift
index 2b0d8fe..cf02069 100644
--- a/Modules/Services/OPDS/OPDSClient.swift
+++ b/Modules/Services/OPDS/OPDSClient.swift
@@ -52,6 +52,16 @@ struct OPDSEntry: Identifiable, Hashable {
     var alternateURL: URL?
     var authorNames: [String] = []
     var relatedLinks: [OPDSRelatedLink] = []
+    /// Subject names, in catalog order. Filled from OPDS 2 `subject`; the
+    /// Atom parser leaves it empty.
+    var subjects: [String] = []
+    /// Publisher names joined with ", ", as `author` is. OPDS 2 only.
+    var publisher: String?
+    /// The publication date, when the catalog's `published` value is an
+    /// ISO 8601 date or date-time. OPDS 2 only.
+    var published: Date?
+    /// Language codes as the catalog gives them (BCP 47). OPDS 2 only.
+    var languages: [String] = []
 
     var isBook: Bool { !acquisitions.isEmpty }
     var isNavigation: Bool { acquisitions.isEmpty && navigationURL != nil }
diff --git a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift
index ad6ebc5..1f8d8a3 100644
--- a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
+++ b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
@@ -58,7 +58,10 @@ struct OPDS2ParserTests {
             "author": {"name": "Austen, Jane", "sortAs": "Austen, Jane",
                        "links": [{"href": "/opds/authors/68", "type": "application/opds+json"}]},
             "description": "<p>A novel of <b>manners</b>.</p>",
-            "subject": [{"name": "Courtship -- Fiction"}],
+            "subject": [{"name": "Courtship -- Fiction", "scheme": "https://www.gutenberg.org/ebooks/subject/", "code": "1"},
+                        "England -- Fiction"],
+            "publisher": "T. Egerton",
+            "published": "1998-06-01",
             "modified": "2026-10-01T00:00:00Z"
           },
           "links": [
@@ -78,7 +81,10 @@ struct OPDS2ParserTests {
             "identifier": "https://www.gutenberg.org/ebooks/25328",
             "title": "老子",
             "language": ["zh", "en"],
-            "author": ["Laozi", {"name": {"en": "Unknown", "zh": "佚名"}}]
+            "author": ["Laozi", {"name": {"en": "Unknown", "zh": "佚名"}}],
+            "subject": {"name": {"zh": "道家"}},
+            "publisher": [{"name": "Zhonghua"}, "Commercial Press"],
+            "published": "2005-03-14T08:30:00.500Z"
           },
           "links": [{"rel": ["http://opds-spec.org/acquisition/open-access"], "href": "/ebooks/25328.epub.images", "type": "application/epub+zip"}]
         }
@@ -168,7 +174,7 @@ struct OPDS2ParserTests {
         #expect(try parse(noQuery).search == nil)
     }
 
-    @Test("publications: identifier, authors with sortAs, language, images, acquisitions, pagination")
+    @Test("publications: identifier, authors with sortAs, language, subjects, publisher, published, images, acquisitions, pagination")
     func publicationsPage() throws {
         let feed = try parse(page, URL(string: "https://opds-test.pglaf.org/opds/recent")!)
         #expect(feed.title == "Recently Added")
@@ -191,6 +197,10 @@ struct OPDS2ParserTests {
         #expect(book.acquisitions.count == 3)
         #expect(book.bestAcquisition?.url.lastPathComponent == "1342.epub3.images")
         #expect(book.bestAcquisition?.rel == "http://opds-spec.org/acquisition/open-access")
+        #expect(book.subjects == ["Courtship -- Fiction", "England -- Fiction"])
+        #expect(book.publisher == "T. Egerton")
+        #expect(book.published == utc(1998, 6, 1))
+        #expect(book.languages == ["en"])
 
         let second = feed.entries[1]
         #expect(second.title == "老子")
@@ -198,6 +208,66 @@ struct OPDS2ParserTests {
         #expect(second.authorNames.first == "Laozi")
         #expect(second.bestAcquisition?.url.absoluteString == "https://opds-test.pglaf.org/ebooks/25328.epub.images")
         #expect(second.coverURL == nil)
+        #expect(second.subjects == ["道家"])
+        #expect(second.publisher == "Zhonghua, Commercial Press")
+        #expect(second.published == utc(2005, 3, 14, 8, 30).addingTimeInterval(0.5))
+        #expect(second.languages == ["zh", "en"])
+    }
+
+    private func utc(_ year: Int, _ month: Int, _ day: Int, _ hour: Int = 0, _ minute: Int = 0) -> Date? {
+        var calendar = Calendar(identifier: .gregorian)
+        calendar.timeZone = TimeZone(identifier: "UTC")!
+        return calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour, minute: minute))
+    }
+
+    @Test("Gutenberg publication: subjects, publisher, published date and language")
+    func gutenbergPublicationMetadata() throws {
+        let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
+            .appendingPathComponent("Fixtures/GutenbergOPDS2/publication.json")
+        let data = try Data(contentsOf: fixture)
+        let feed = try OPDSClient.parseFeed(data: data, feedURL: URL(string: "https://opds-test.pglaf.org/opds/publications?id=79734")!,
+                                            contentType: "application/opds-publication+json")
+        let book = try #require(feed.entries.first)
+        #expect(book.subjects == [
+            "Makino, Yoshio, 1874-1956",
+            "Watercolorists -- England -- London -- Biography",
+            "Watercolorists -- Japan -- Biography",
+            "Fine Arts: ND",
+        ])
+        #expect(book.publisher == "Philadelphia: George W. Jacobs & Co., 1910.")
+        #expect(book.published == utc(2026, 10, 6))
+        #expect(book.languages == ["en"])
+    }
+
+    @Test("published accepts ISO 8601 dates and date-times only; absent members stay empty")
+    func publishedAndAbsentMetadata() throws {
+        #expect(OPDS2FeedParser.date(from: "2026-10-06") == utc(2026, 10, 6))
+        #expect(OPDS2FeedParser.date(from: " 2026-10-01T00:00:00Z ") == utc(2026, 10, 1))
+        #expect(OPDS2FeedParser.date(from: "2026-10-01T02:00:00+02:00") == utc(2026, 10, 1))
+        #expect(OPDS2FeedParser.date(from: "Philadelphia, 1910") == nil)
+        #expect(OPDS2FeedParser.date(from: "") == nil)
+
+        func book(_ metadata: String) throws -> OPDSEntry {
+            let json = """
+            {"metadata": {"title": "Book"\(metadata)}, "links": [{"rel": "http://opds-spec.org/acquisition", "href": "b.epub", "type": "application/epub+zip"}]}
+            """
+            return try #require(try parse(json).entries.first)
+        }
+        let undated = try book(#", "published": "sometime in 1910", "publisher": [], "subject": []"#)
+        #expect(undated.published == nil)
+        #expect(undated.publisher == nil)
+        #expect(undated.subjects.isEmpty)
+
+        let bare = try book("")
+        #expect(bare.subjects.isEmpty)
+        #expect(bare.publisher == nil)
+        #expect(bare.published == nil)
+        #expect(bare.languages.isEmpty)
+
+        // A subject object needs a name, and `published` must be a string.
+        for mistyped in [#", "subject": [{"code": "ND"}]"#, #", "subject": 5"#, #", "published": 1910"#] {
+            #expect(throws: OPDSError.self) { try book(mistyped) }
+        }
     }
 
     @Test("a publication document becomes a one-entry feed")

```


===== RUN b028 =====
```diff
diff --git a/Modules/Services/OPDS/OPDS2FeedParser.swift b/Modules/Services/OPDS/OPDS2FeedParser.swift
index d3d659a..95937da 100644
--- a/Modules/Services/OPDS/OPDS2FeedParser.swift
+++ b/Modules/Services/OPDS/OPDS2FeedParser.swift
@@ -161,6 +161,11 @@ private struct Mapper {
         if let description = metadata.description, !description.isEmpty {
             entry.summary = Self.plain(description, limit: 8_000)
         }
+        entry.subjects = metadata.subject.map { Self.plain($0.name, limit: 512) }.filter { !$0.isEmpty }
+        let publishers = metadata.publisher.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        entry.publisher = publishers.isEmpty ? nil : publishers.joined(separator: ", ")
+        entry.published = metadata.published.flatMap(Self.date(from:))
+        entry.languages = metadata.language.map { Self.plain($0, limit: 64) }.filter { !$0.isEmpty }
         guard entry.isBook || entry.isNavigation else { return nil }
         if entry.alternateURL == nil, entry.isBook { entry.alternateURL = feedAlternateURL }
         entry.id = metadata.identifier ?? entry.navigationURL?.absoluteString
@@ -210,6 +215,22 @@ private struct Mapper {
     }
 
     private static func plain(_ value: String, limit: Int) -> String { OPDSClient.plainMetadata(value, limit: limit) }
+
+    /// `published` is an ISO 8601 date (`2026-10-06`, read as midnight UTC) or
+    /// date-time (`2026-10-06T12:00:00Z`, optionally with fractional seconds).
+    /// Anything else, such as a bare year, is not a date and yields nil.
+    static func date(from value: String) -> Date? {
+        let text = value.trimmingCharacters(in: .whitespacesAndNewlines)
+        let styles: [Date.ISO8601FormatStyle] = [
+            Date.ISO8601FormatStyle(),
+            Date.ISO8601FormatStyle(includingFractionalSeconds: true),
+            Date.ISO8601FormatStyle().year().month().day(),
+        ]
+        for style in styles {
+            if let date = try? style.parse(text) { return date }
+        }
+        return nil
+    }
 }
 
 // MARK: - Document model
@@ -247,8 +268,13 @@ extension OPDS2FeedParser {
         var description: String?
         var language: [String] = []
         var author: [Contributor] = []
+        var publisher: [Contributor] = []
+        var subject: [Subject] = []
+        var published: String?
 
-        private enum CodingKeys: String, CodingKey { case identifier, title, description, language, author }
+        private enum CodingKeys: String, CodingKey {
+            case identifier, title, description, language, author, publisher, subject, published
+        }
 
         init(from decoder: Decoder) throws {
             let values = try decoder.container(keyedBy: CodingKeys.self)
@@ -257,6 +283,26 @@ extension OPDS2FeedParser {
             description = try values.decodeIfPresent(String.self, forKey: .description)
             language = try values.decodeIfPresent(OneOrMany<String>.self, forKey: .language)?.values ?? []
             author = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .author)?.values ?? []
+            publisher = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .publisher)?.values ?? []
+            subject = try values.decodeIfPresent(OneOrMany<Subject>.self, forKey: .subject)?.values ?? []
+            published = try values.decodeIfPresent(String.self, forKey: .published)
+        }
+    }
+
+    /// A subject is a bare name or an object with a `name` (a string or a
+    /// language map) and optional `sortAs`, `scheme`, `code` and `links`.
+    struct Subject: Decodable {
+        var name: String
+
+        private enum CodingKeys: String, CodingKey { case name }
+
+        init(from decoder: Decoder) throws {
+            do {
+                name = try decoder.singleValueContainer().decode(String.self)
+            } catch DecodingError.typeMismatch {
+                let values = try decoder.container(keyedBy: CodingKeys.self)
+                name = try values.decode(LocalizedString.self, forKey: .name).value
+            }
         }
     }
 
diff --git a/Modules/Services/OPDS/OPDSClient.swift b/Modules/Services/OPDS/OPDSClient.swift
index 2b0d8fe..ecee58a 100644
--- a/Modules/Services/OPDS/OPDSClient.swift
+++ b/Modules/Services/OPDS/OPDSClient.swift
@@ -52,6 +52,14 @@ struct OPDSEntry: Identifiable, Hashable {
     var alternateURL: URL?
     var authorNames: [String] = []
     var relatedLinks: [OPDSRelatedLink] = []
+    /// Subject names, in document order. Filled by the OPDS 2 parser only.
+    var subjects: [String] = []
+    /// Publisher names joined with ", ". Filled by the OPDS 2 parser only.
+    var publisher: String?
+    /// Publication date; nil when absent or not a date. Filled by the OPDS 2 parser only.
+    var published: Date?
+    /// Language codes (BCP 47) as the catalog gives them. Filled by the OPDS 2 parser only.
+    var languages: [String] = []
 
     var isBook: Bool { !acquisitions.isEmpty }
     var isNavigation: Bool { acquisitions.isEmpty && navigationURL != nil }
diff --git a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift
index ad6ebc5..f15eadd 100644
--- a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
+++ b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
@@ -58,7 +58,10 @@ struct OPDS2ParserTests {
             "author": {"name": "Austen, Jane", "sortAs": "Austen, Jane",
                        "links": [{"href": "/opds/authors/68", "type": "application/opds+json"}]},
             "description": "<p>A novel of <b>manners</b>.</p>",
-            "subject": [{"name": "Courtship -- Fiction"}],
+            "subject": [{"name": "Courtship -- Fiction", "scheme": "https://www.gutenberg.org/ebooks/subject/", "code": "1"},
+                        {"name": "Fine Arts: ND", "sortAs": "ND", "scheme": "http://purl.org/dc/terms/LCC", "code": "ND"}],
+            "publisher": "London: T. Egerton, 1813.",
+            "published": "1813-01-28",
             "modified": "2026-10-01T00:00:00Z"
           },
           "links": [
@@ -78,7 +81,9 @@ struct OPDS2ParserTests {
             "identifier": "https://www.gutenberg.org/ebooks/25328",
             "title": "老子",
             "language": ["zh", "en"],
-            "author": ["Laozi", {"name": {"en": "Unknown", "zh": "佚名"}}]
+            "author": ["Laozi", {"name": {"en": "Unknown", "zh": "佚名"}}],
+            "subject": ["Taoism", {"name": {"en": "Philosophy, Chinese"}}],
+            "publisher": ["Commercial Press", {"name": "Shanghai Books"}]
           },
           "links": [{"rel": ["http://opds-spec.org/acquisition/open-access"], "href": "/ebooks/25328.epub.images", "type": "application/epub+zip"}]
         }
@@ -191,6 +196,10 @@ struct OPDS2ParserTests {
         #expect(book.acquisitions.count == 3)
         #expect(book.bestAcquisition?.url.lastPathComponent == "1342.epub3.images")
         #expect(book.bestAcquisition?.rel == "http://opds-spec.org/acquisition/open-access")
+        #expect(book.subjects == ["Courtship -- Fiction", "Fine Arts: ND"])
+        #expect(book.publisher == "London: T. Egerton, 1813.")
+        #expect(book.languages == ["en"])
+        #expect(book.published.map(utcDay) == DateComponents(year: 1813, month: 1, day: 28, hour: 0, minute: 0))
 
         let second = feed.entries[1]
         #expect(second.title == "老子")
@@ -198,6 +207,86 @@ struct OPDS2ParserTests {
         #expect(second.authorNames.first == "Laozi")
         #expect(second.bestAcquisition?.url.absoluteString == "https://opds-test.pglaf.org/ebooks/25328.epub.images")
         #expect(second.coverURL == nil)
+        // Bare-string and object subjects mix; an object's name may be a language map.
+        #expect(second.subjects == ["Taoism", "Philosophy, Chinese"])
+        #expect(second.publisher == "Commercial Press, Shanghai Books")
+        #expect(second.languages == ["zh", "en"])
+        #expect(second.published == nil)
+    }
+
+    @Test("subject, publisher, published and language: single values, objects and non-dates")
+    func publicationMetadataFields() throws {
+        func book(_ metadata: String) throws -> OPDSEntry {
+            let json = """
+            {"metadata": {"title": "B", \(metadata)},
+             "links": [{"rel": "http://opds-spec.org/acquisition", "href": "b.epub", "type": "application/epub+zip"}]}
+            """
+            return try #require(try parse(json).entries.first)
+        }
+
+        let single = try book(#""subject": "Fiction", "publisher": {"name": "Jacobs & Co."}, "language": "ja", "published": "2026-10-01T12:30:00Z""#)
+        #expect(single.subjects == ["Fiction"])
+        #expect(single.publisher == "Jacobs & Co.")
+        #expect(single.languages == ["ja"])
+        #expect(single.published == Date(timeIntervalSince1970: 1_790_857_800))
+
+        let object = try book(#""subject": {"name": "Watercolorists -- Japan -- Biography", "code": "43006"}, "published": "2026-10-01T12:30:00.250Z""#)
+        #expect(object.subjects == ["Watercolorists -- Japan -- Biography"])
+        #expect(object.published == Date(timeIntervalSince1970: 1_790_857_800.25))
+
+        // A bare year or free text is not a date.
+        #expect(try book(#""published": "1910""#).published == nil)
+        #expect(try book(#""published": "circa 1910""#).published == nil)
+
+        let none = try book(#""identifier": "urn:none""#)
+        #expect(none.subjects.isEmpty)
+        #expect(none.publisher == nil)
+        #expect(none.published == nil)
+        #expect(none.languages.isEmpty)
+    }
+
+    @Test("the recorded Gutenberg publication keeps its subjects, publisher, date and language")
+    func gutenbergPublicationFixtureFields() throws {
+        let json = """
+        {"metadata": {"identifier": "https://www.gutenberg.org/ebooks/79734", "title": "A Japanese artist in London", "language": "en",
+          "published": "2026-10-06",
+          "subject": [{"name": "Makino, Yoshio, 1874-1956", "scheme": "https://www.gutenberg.org/ebooks/subject/", "code": "43005",
+                       "links": [{"href": "https://opds-test.pglaf.org/opds/subjects?id=43005", "type": "application/opds+json"}]},
+                      {"name": "Fine Arts: ND", "sortAs": "ND", "scheme": "http://purl.org/dc/terms/LCC", "code": "ND"}],
+          "publisher": "Philadelphia: George W. Jacobs & Co., 1910."},
+         "links": [{"rel": "http://opds-spec.org/acquisition/open-access", "href": "https://www.gutenberg.org/cache/epub/79734/pg79734-images-3.epub", "type": "application/epub+zip"}]}
+        """
+        let book = try #require(try parse(json, type: "application/opds-publication+json").entries.first)
+        #expect(book.subjects == ["Makino, Yoshio, 1874-1956", "Fine Arts: ND"])
+        #expect(book.publisher == "Philadelphia: George W. Jacobs & Co., 1910.")
+        #expect(book.languages == ["en"])
+        #expect(book.published.map(utcDay) == DateComponents(year: 2026, month: 10, day: 6, hour: 0, minute: 0))
+    }
+
+    @Test("the Atom parser leaves the OPDS 2 metadata fields empty")
+    func atomLeavesNewFieldsEmpty() throws {
+        let atom = """
+        <?xml version="1.0" encoding="UTF-8"?>
+        <feed xmlns="http://www.w3.org/2005/Atom">
+          <title>Atom</title>
+          <entry>
+            <id>urn:a</id><title>A</title>
+            <link rel="http://opds-spec.org/acquisition" href="https://example.org/a.epub" type="application/epub+zip"/>
+          </entry>
+        </feed>
+        """
+        let feed = try OPDSClient.parseFeed(data: Data(atom.utf8), feedURL: base)
+        let entry = try #require(feed.entries.first)
+        #expect(entry.subjects.isEmpty)
+        #expect(entry.publisher == nil)
+        #expect(entry.published == nil)
+        #expect(entry.languages.isEmpty)
+    }
+
+    private func utcDay(_ date: Date) -> DateComponents {
+        var calendar = Calendar(identifier: .gregorian)
+        calendar.timeZone = TimeZone(identifier: "UTC")!
+        return calendar.dateComponents([.year, .month, .day, .hour, .minute], from: date)
     }
 
     @Test("a publication document becomes a one-entry feed")

```


===== RUN b027 =====
```diff
diff --git a/Modules/Services/OPDS/OPDS2FeedParser.swift b/Modules/Services/OPDS/OPDS2FeedParser.swift
index d3d659a..02a9568 100644
--- a/Modules/Services/OPDS/OPDS2FeedParser.swift
+++ b/Modules/Services/OPDS/OPDS2FeedParser.swift
@@ -161,6 +161,11 @@ private struct Mapper {
         if let description = metadata.description, !description.isEmpty {
             entry.summary = Self.plain(description, limit: 8_000)
         }
+        entry.subjects = metadata.subject.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        let publishers = metadata.publisher.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        entry.publisher = publishers.isEmpty ? nil : publishers.joined(separator: ", ")
+        entry.languages = metadata.language.map { Self.plain($0, limit: 64) }.filter { !$0.isEmpty }
+        entry.published = metadata.published.flatMap { Self.date(fromPublished: $0) }
         guard entry.isBook || entry.isNavigation else { return nil }
         if entry.alternateURL == nil, entry.isBook { entry.alternateURL = feedAlternateURL }
         entry.id = metadata.identifier ?? entry.navigationURL?.absoluteString
@@ -210,6 +215,23 @@ private struct Mapper {
     }
 
     private static func plain(_ value: String, limit: Int) -> String { OPDSClient.plainMetadata(value, limit: limit) }
+
+    /// Parses an OPDS 2 `published` value: an RFC 3339 date-time (with or
+    /// without fractional seconds) or a bare `YYYY-MM-DD` date. Anything else
+    /// is not a date, so the field stays nil.
+    static func date(fromPublished value: String) -> Date? {
+        let text = value.trimmingCharacters(in: .whitespaces)
+        let formatter = ISO8601DateFormatter()
+        formatter.timeZone = TimeZone(identifier: "UTC")
+        let candidates: [ISO8601DateFormatter.Options] = [
+            [.withInternetDateTime, .withFractionalSeconds], [.withInternetDateTime], [.withFullDate],
+        ]
+        for options in candidates {
+            formatter.formatOptions = options
+            if let date = formatter.date(from: text) { return date }
+        }
+        return nil
+    }
 }
 
 // MARK: - Document model
@@ -247,8 +269,13 @@ extension OPDS2FeedParser {
         var description: String?
         var language: [String] = []
         var author: [Contributor] = []
+        var publisher: [Contributor] = []
+        var published: String?
+        var subject: [Subject] = []
 
-        private enum CodingKeys: String, CodingKey { case identifier, title, description, language, author }
+        private enum CodingKeys: String, CodingKey {
+            case identifier, title, description, language, author, publisher, published, subject
+        }
 
         init(from decoder: Decoder) throws {
             let values = try decoder.container(keyedBy: CodingKeys.self)
@@ -257,6 +284,25 @@ extension OPDS2FeedParser {
             description = try values.decodeIfPresent(String.self, forKey: .description)
             language = try values.decodeIfPresent(OneOrMany<String>.self, forKey: .language)?.values ?? []
             author = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .author)?.values ?? []
+            publisher = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .publisher)?.values ?? []
+            published = try values.decodeIfPresent(String.self, forKey: .published)
+            subject = try values.decodeIfPresent(OneOrMany<Subject>.self, forKey: .subject)?.values ?? []
+        }
+    }
+
+    /// A subject is a bare string or an object with `name` (a string or a
+    /// language map) and optional `scheme`, `code` and `links`.
+    struct Subject: Decodable {
+        var name: String
+
+        private enum CodingKeys: String, CodingKey { case name }
+
+        init(from decoder: Decoder) throws {
+            do {
+                name = try decoder.singleValueContainer().decode(String.self)
+            } catch DecodingError.typeMismatch {
+                name = try decoder.container(keyedBy: CodingKeys.self).decode(LocalizedString.self, forKey: .name).value
+            }
         }
     }
 
diff --git a/Modules/Services/OPDS/OPDSClient.swift b/Modules/Services/OPDS/OPDSClient.swift
index 2b0d8fe..17ccd7c 100644
--- a/Modules/Services/OPDS/OPDSClient.swift
+++ b/Modules/Services/OPDS/OPDSClient.swift
@@ -52,6 +52,14 @@ struct OPDSEntry: Identifiable, Hashable {
     var alternateURL: URL?
     var authorNames: [String] = []
     var relatedLinks: [OPDSRelatedLink] = []
+    /// Subject headings by name. Empty for Atom feeds, which do not map them.
+    var subjects: [String] = []
+    /// Language tags as published. Empty for Atom feeds.
+    var languages: [String] = []
+    /// Publisher names joined with ", ". Nil for Atom feeds.
+    var publisher: String?
+    /// Publication date. Nil when absent or not a date.
+    var published: Date?
 
     var isBook: Bool { !acquisitions.isEmpty }
     var isNavigation: Bool { acquisitions.isEmpty && navigationURL != nil }
diff --git a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift
index ad6ebc5..2ecb0b6 100644
--- a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
+++ b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
@@ -246,4 +246,66 @@ struct OPDS2ParserTests {
             Issue.record("Empty body must not become an empty catalog")
         } catch OPDSError.noData {} catch { Issue.record("Unexpected error: \(error)") }
     }
+
+    private func utcDate(_ year: Int, _ month: Int, _ day: Int, hour: Int = 0, minute: Int = 0,
+                         second: Int = 0, nanosecond: Int = 0) -> Date? {
+        var calendar = Calendar(identifier: .gregorian)
+        calendar.timeZone = TimeZone(identifier: "UTC")!
+        return calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour, minute: minute,
+                                                  second: second, nanosecond: nanosecond))
+    }
+
+    @Test("subjects, publisher, language and published map from OPDS 2 metadata")
+    func subjectsPublisherLanguagePublished() throws {
+        let acquisition = #""links": [{"rel": "http://opds-spec.org/acquisition/open-access", "href": "b.epub", "type": "application/epub+zip"}]"#
+        let json = """
+        {"metadata": {"title": "T"}, "publications": [
+          {"metadata": {"title": "Gutenberg shape", "identifier": "urn:g", "language": "en",
+                        "published": "2026-10-06", "publisher": "Philadelphia: George W. Jacobs, 1910.",
+                        "subject": [
+                          {"name": "Watercolorists -- England", "scheme": "https://www.gutenberg.org/ebooks/subject/",
+                           "code": "43007", "links": [{"href": "/opds/subjects?id=43007", "type": "application/opds+json"}]},
+                          {"name": "Fine Arts: ND", "sortAs": "ND", "scheme": "http://purl.org/dc/terms/LCC", "code": "ND"}
+                        ]},
+           \(acquisition)},
+          {"metadata": {"title": "Single values", "identifier": "urn:s", "language": ["fr", "de"],
+                        "published": "2026-10-06T12:30:00.5Z",
+                        "publisher": {"name": {"zh": "出版社"}},
+                        "subject": {"name": {"zh": "水彩畫家"}}},
+           \(acquisition)},
+          {"metadata": {"title": "Unusable", "identifier": "urn:u", "published": "sometime in 1910",
+                        "subject": [{"name": ""}, "Kept"]},
+           \(acquisition)}
+        ]}
+        """
+        let entries = try parse(json).entries
+        #expect(entries.count == 3)
+
+        let gutenberg = try #require(entries.first)
+        #expect(gutenberg.subjects == ["Watercolorists -- England", "Fine Arts: ND"])
+        #expect(gutenberg.languages == ["en"])
+        #expect(gutenberg.publisher == "Philadelphia: George W. Jacobs, 1910.")
+        #expect(gutenberg.published == utcDate(2026, 10, 6))
+
+        let single = entries[1]
+        #expect(single.subjects == ["水彩畫家"])
+        #expect(single.languages == ["fr", "de"])
+        #expect(single.publisher == "出版社")
+        #expect(single.published == utcDate(2026, 10, 6, hour: 12, minute: 30, nanosecond: 500_000_000))
+
+        let unusable = entries[2]
+        #expect(unusable.subjects == ["Kept"])
+        #expect(unusable.languages.isEmpty)
+        #expect(unusable.publisher == nil)
+        #expect(unusable.published == nil)
+    }
+
+    @Test("publications without the new metadata leave the fields empty")
+    func newFieldsAbsent() throws {
+        let entry = try #require(try parse(#"{"metadata": {"title": "T"}, "publications": [{"metadata": {"title": "Bare"}, "links": [{"rel": "http://opds-spec.org/acquisition", "href": "b.epub", "type": "application/epub+zip"}]}]}"#).entries.first)
+        #expect(entry.subjects.isEmpty)
+        #expect(entry.languages.isEmpty)
+        #expect(entry.publisher == nil)
+        #expect(entry.published == nil)
+    }
 }

```


===== RUN b025 =====
```diff
diff --git a/Modules/Services/OPDS/OPDS2FeedParser.swift b/Modules/Services/OPDS/OPDS2FeedParser.swift
index d3d659a..66b5487 100644
--- a/Modules/Services/OPDS/OPDS2FeedParser.swift
+++ b/Modules/Services/OPDS/OPDS2FeedParser.swift
@@ -161,6 +161,11 @@ private struct Mapper {
         if let description = metadata.description, !description.isEmpty {
             entry.summary = Self.plain(description, limit: 8_000)
         }
+        entry.subjects = metadata.subject.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        let publishers = metadata.publisher.map { Self.plain($0.name, limit: 256) }.filter { !$0.isEmpty }
+        entry.publisher = publishers.isEmpty ? nil : publishers.joined(separator: ", ")
+        entry.languages = metadata.language.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
+        entry.published = metadata.published.flatMap(Self.parseDate)
         guard entry.isBook || entry.isNavigation else { return nil }
         if entry.alternateURL == nil, entry.isBook { entry.alternateURL = feedAlternateURL }
         entry.id = metadata.identifier ?? entry.navigationURL?.absoluteString
@@ -210,6 +215,20 @@ private struct Mapper {
     }
 
     private static func plain(_ value: String, limit: Int) -> String { OPDSClient.plainMetadata(value, limit: limit) }
+
+    /// OPDS 2 dates are ISO 8601: a full date, or a date-time with an offset and
+    /// optional fractional seconds. Any other text is not a date, so it yields nil.
+    private static func parseDate(_ value: String) -> Date? {
+        let trimmed = value.trimmingCharacters(in: .whitespaces)
+        let dateTime = ISO8601DateFormatter()
+        dateTime.formatOptions = [.withInternetDateTime]
+        if let date = dateTime.date(from: trimmed) { return date }
+        dateTime.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
+        if let date = dateTime.date(from: trimmed) { return date }
+        let day = ISO8601DateFormatter()
+        day.formatOptions = [.withFullDate]
+        return day.date(from: trimmed)
+    }
 }
 
 // MARK: - Document model
@@ -247,8 +266,13 @@ extension OPDS2FeedParser {
         var description: String?
         var language: [String] = []
         var author: [Contributor] = []
+        var publisher: [Contributor] = []
+        var subject: [Subject] = []
+        var published: String?
 
-        private enum CodingKeys: String, CodingKey { case identifier, title, description, language, author }
+        private enum CodingKeys: String, CodingKey {
+            case identifier, title, description, language, author, publisher, subject, published
+        }
 
         init(from decoder: Decoder) throws {
             let values = try decoder.container(keyedBy: CodingKeys.self)
@@ -257,6 +281,24 @@ extension OPDS2FeedParser {
             description = try values.decodeIfPresent(String.self, forKey: .description)
             language = try values.decodeIfPresent(OneOrMany<String>.self, forKey: .language)?.values ?? []
             author = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .author)?.values ?? []
+            publisher = try values.decodeIfPresent(OneOrMany<Contributor>.self, forKey: .publisher)?.values ?? []
+            subject = try values.decodeIfPresent(OneOrMany<Subject>.self, forKey: .subject)?.values ?? []
+            published = try values.decodeIfPresent(String.self, forKey: .published)
+        }
+    }
+
+    /// A subject is a bare string or an object whose `name` may be a language map.
+    struct Subject: Decodable {
+        var name: String
+
+        private enum CodingKeys: String, CodingKey { case name }
+
+        init(from decoder: Decoder) throws {
+            do {
+                name = try decoder.singleValueContainer().decode(String.self)
+            } catch DecodingError.typeMismatch {
+                name = try decoder.container(keyedBy: CodingKeys.self).decode(LocalizedString.self, forKey: .name).value
+            }
         }
     }
 
diff --git a/Modules/Services/OPDS/OPDSClient.swift b/Modules/Services/OPDS/OPDSClient.swift
index 2b0d8fe..937b993 100644
--- a/Modules/Services/OPDS/OPDSClient.swift
+++ b/Modules/Services/OPDS/OPDSClient.swift
@@ -52,6 +52,11 @@ struct OPDSEntry: Identifiable, Hashable {
     var alternateURL: URL?
     var authorNames: [String] = []
     var relatedLinks: [OPDSRelatedLink] = []
+    /// Dublin Core metadata. OPDS 2 supplies it; the Atom parser leaves it empty.
+    var subjects: [String] = []
+    var publisher: String?
+    var published: Date?
+    var languages: [String] = []
 
     var isBook: Bool { !acquisitions.isEmpty }
     var isNavigation: Bool { acquisitions.isEmpty && navigationURL != nil }
diff --git a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift
index ad6ebc5..34e4dbd 100644
--- a/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
+++ b/Tests/iOS/yuedu appTests/OPDS2ParserTests.swift	
@@ -200,6 +200,45 @@ struct OPDS2ParserTests {
         #expect(second.coverURL == nil)
     }
 
+    @Test("subjects, publisher, published and languages come from OPDS 2 metadata")
+    func dublinCoreMetadata() throws {
+        let json = """
+        {"metadata": {"title": "Catalog"}, "publications": [
+          {"metadata": {"identifier": "urn:a", "title": "Dated", "language": "en",
+                        "publisher": "Philadelphia: George W. Jacobs, 1910.",
+                        "subject": ["Bare", {"name": "Object"}, {"name": {"de": "Geschichte"}}, {"name": ""}],
+                        "published": "2026-10-06"},
+           "links": [{"rel": "http://opds-spec.org/acquisition", "href": "a.epub", "type": "application/epub+zip"}]},
+          {"metadata": {"identifier": "urn:b", "title": "Timestamped", "language": ["zh", "en"],
+                        "publisher": [{"name": {"de": "Verlag"}}, {"name": "Second"}],
+                        "subject": {"name": "Single"}, "published": "2026-10-01T12:30:00Z"},
+           "links": [{"rel": "http://opds-spec.org/acquisition", "href": "b.epub", "type": "application/epub+zip"}]},
+          {"metadata": {"identifier": "urn:c", "title": "Undated", "published": "October 2026", "publisher": []},
+           "links": [{"rel": "http://opds-spec.org/acquisition", "href": "c.epub", "type": "application/epub+zip"}]}
+        ]}
+        """
+        let entries = try parse(json).entries
+        #expect(entries.count == 3)
+
+        let dated = try #require(entries.first)
+        #expect(dated.subjects == ["Bare", "Object", "Geschichte"])
+        #expect(dated.publisher == "Philadelphia: George W. Jacobs, 1910.")
+        #expect(dated.published == Date(timeIntervalSince1970: 1_791_244_800))
+        #expect(dated.languages == ["en"])
+
+        let timestamped = entries[1]
+        #expect(timestamped.subjects == ["Single"])
+        #expect(timestamped.publisher == "Verlag, Second")
+        #expect(timestamped.published == Date(timeIntervalSince1970: 1_790_857_800))
+        #expect(timestamped.languages == ["zh", "en"])
+
+        let undated = entries[2]
+        #expect(undated.subjects.isEmpty)
+        #expect(undated.publisher == nil)
+        #expect(undated.published == nil)
+        #expect(undated.languages.isEmpty)
+    }
+
     @Test("a publication document becomes a one-entry feed")
     func publicationDocument() throws {
         let feed = try parse(publication, URL(string: "https://opds-test.pglaf.org/opds/ebooks/1342")!)

```
