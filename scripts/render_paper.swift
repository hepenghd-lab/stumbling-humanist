// Render the Markdown report as a searchable A4 PDF using macOS system fonts.
// Usage: swift scripts/render_paper.swift paper/PAPER.zh-CN.md paper/PAPER.zh-CN.pdf
import Foundation
import AppKit
import CoreText
import CoreGraphics

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: swift render_paper.swift input.md output.pdf\n", stderr)
    exit(2)
}
let source = try String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)
let document = NSMutableAttributedString()
var fenced = false
for original in source.components(separatedBy: "\n") {
    if original.hasPrefix("```") { fenced.toggle(); continue }
    if original.range(of: #"^\|[\s:|\-]+\|$"#, options: .regularExpression) != nil { continue }
    let level = original.prefix(while: { $0 == "#" }).count
    var line = original
    if level > 0 { line = String(original.dropFirst(level)).trimmingCharacters(in: .whitespaces) }
    line = line.replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "`", with: "")
    let table = line.hasPrefix("|")
    if table { line = line.trimmingCharacters(in: CharacterSet(charactersIn: "| ")).replacingOccurrences(of: "|", with: "  ·  ") }
    let size: CGFloat = level == 1 ? 18 : level == 2 ? 14 : level == 3 ? 12 : table ? 9 : 11
    let font = NSFont(name: level > 0 ? "PingFangSC-Semibold" : "SongtiSC-Regular", size: size)
        ?? NSFont.systemFont(ofSize: size)
    let style = NSMutableParagraphStyle()
    style.lineSpacing = 4
    style.paragraphSpacing = line.isEmpty ? 2 : 7
    style.paragraphSpacingBefore = level > 0 ? 8 : 0
    style.lineBreakMode = .byWordWrapping
    if level == 1 { style.alignment = .center }
    document.append(NSAttributedString(string: line + "\n", attributes: [
        .font: fenced ? NSFont.monospacedSystemFont(ofSize: 10, weight: .regular) : font,
        .paragraphStyle: style, .foregroundColor: NSColor.black
    ]))
}
let destination = URL(fileURLWithPath: CommandLine.arguments[2])
var media = CGRect(x: 0, y: 0, width: 595.28, height: 841.89)
guard let consumer = CGDataConsumer(url: destination as CFURL),
      let context = CGContext(consumer: consumer, mediaBox: &media, [
        kCGPDFContextTitle: "面向 Codex CLI 的白名单中文提示包装器：终端兼容设计与隔离验证",
        kCGPDFContextAuthor: "hepenghd-lab",
        kCGPDFContextSubject: "Engineering technical report; not peer reviewed"
      ] as CFDictionary) else { fatalError("Unable to create PDF") }
let framesetter = CTFramesetterCreateWithAttributedString(document as CFAttributedString)
var offset = 0
var page = 0
while offset < document.length {
    page += 1
    context.beginPDFPage(nil)
    context.textMatrix = .identity
    let bounds = CGRect(x: 52, y: 56, width: media.width - 104, height: media.height - 110)
    let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: offset, length: 0),
                                        CGPath(rect: bounds, transform: nil), nil)
    CTFrameDraw(frame, context)
    let range = CTFrameGetVisibleStringRange(frame)
    guard range.length > 0 else { fatalError("Text pagination stalled") }
    offset += range.length
    let footer = NSAttributedString(string: "codex-zh-local  ·  2026-10-11  ·  \(page)", attributes: [
        .font: NSFont.systemFont(ofSize: 9), .foregroundColor: NSColor.gray
    ])
    let footerLine = CTLineCreateWithAttributedString(footer as CFAttributedString)
    let width = CTLineGetTypographicBounds(footerLine, nil, nil, nil)
    context.textPosition = CGPoint(x: (Double(media.width) - width) / 2, y: 27)
    CTLineDraw(footerLine, context)
    context.endPDFPage()
}
context.closePDF()
print("Rendered searchable A4 PDF: \(page) pages")
