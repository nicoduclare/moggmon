#!/usr/bin/env swift

import AppKit
import CoreImage
import Foundation
import Vision

struct Config {
    var sourceDir: URL
    var dexes: Set<Int>
    var overwrite: Bool
    var artName: String
}

enum MaskError: Error, CustomStringConvertible {
    case invalidArgs(String)
    case imageLoadFailed(URL)
    case cgImageFailed(URL)
    case noForeground(URL)
    case pngEncodeFailed(URL)

    var description: String {
        switch self {
        case .invalidArgs(let message):
            return message
        case .imageLoadFailed(let url):
            return "Failed to load image: \(url.path)"
        case .cgImageFailed(let url):
            return "Failed to create CGImage for: \(url.path)"
        case .noForeground(let url):
            return "Vision returned no foreground mask for: \(url.path)"
        case .pngEncodeFailed(let url):
            return "Failed to encode PNG for: \(url.path)"
        }
    }
}

func fallbackMaskURL(for folder: URL, artName: String) -> URL? {
    guard artName != "full-art" else {
        return nil
    }
    let url = sidecarURL(in: folder, baseName: "holo-mask", extension: "png", artName: "full-art")
    return FileManager.default.fileExists(atPath: url.path) ? url : nil
}

func parseArgs() throws -> Config {
    let args = Array(CommandLine.arguments.dropFirst())
    var sourceDir = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        .appendingPathComponent("output/private-generation-prompts/mogger-mon-tcg", isDirectory: true)
    var dexes = Set<Int>()
    var overwrite = false
    var artName = "full-art"
    var index = 0

    while index < args.count {
        let arg = args[index]
        switch arg {
        case "--source-dir":
            index += 1
            guard index < args.count else {
                throw MaskError.invalidArgs("Missing value for --source-dir")
            }
            sourceDir = URL(fileURLWithPath: args[index], isDirectory: true)
        case "--dex":
            index += 1
            guard index < args.count, let dex = Int(args[index]) else {
                throw MaskError.invalidArgs("Missing numeric value for --dex")
            }
            dexes.insert(dex)
        case "--overwrite":
            overwrite = true
        case "--art-name":
            index += 1
            guard index < args.count else {
                throw MaskError.invalidArgs("Missing value for --art-name")
            }
            artName = args[index]
        default:
            throw MaskError.invalidArgs("Unknown argument: \(arg)")
        }
        index += 1
    }

    return Config(sourceDir: sourceDir, dexes: dexes, overwrite: overwrite, artName: artName)
}

func artVariantSuffix(for artName: String) -> String {
    if artName == "full-art" {
        return ""
    }
    if artName.hasPrefix("full-art") {
        return String(artName.dropFirst("full-art".count))
    }
    return "-\(artName)"
}

func sidecarURL(in folder: URL, baseName: String, extension ext: String, artName: String) -> URL {
    let suffix = artVariantSuffix(for: artName)
    let fileName = suffix.isEmpty ? "\(baseName).\(ext)" : "\(baseName)\(suffix).\(ext)"
    return folder.appendingPathComponent(fileName)
}

func artURL(for folder: URL, artName: String) -> URL? {
    let exts = ["jpg", "png", "webp", "jpeg"]
    for ext in exts {
        let candidate = sidecarURL(in: folder, baseName: artName, extension: ext, artName: "full-art")
        if FileManager.default.fileExists(atPath: candidate.path) {
            return candidate
        }
    }
    return nil
}

func loadCGImage(from url: URL) throws -> CGImage {
    guard let image = NSImage(contentsOf: url) else {
        throw MaskError.imageLoadFailed(url)
    }
    var rect = CGRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
        throw MaskError.cgImageFailed(url)
    }
    return cgImage
}

func buildBinaryInvertedMask(from cgImage: CGImage, sourceURL: URL) throws -> CGImage {
    let request = VNGenerateForegroundInstanceMaskRequest()
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])

    guard let observation = request.results?.first else {
        throw MaskError.noForeground(sourceURL)
    }

    let pixelBuffer = try observation.generateScaledMaskForImage(forInstances: observation.allInstances, from: handler)
    let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
    let ciContext = CIContext(options: nil)
    guard let rawMaskCG = ciContext.createCGImage(ciImage, from: ciImage.extent) else {
        throw MaskError.noForeground(sourceURL)
    }

    let width = rawMaskCG.width
    let height = rawMaskCG.height
    let bytesPerRow = width
    let colorSpace = CGColorSpaceCreateDeviceGray()
    var pixels = [UInt8](repeating: 0, count: width * height)

    guard let drawContext = CGContext(
        data: &pixels,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: bytesPerRow,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.none.rawValue
    ) else {
        throw MaskError.noForeground(sourceURL)
    }

    drawContext.draw(rawMaskCG, in: CGRect(x: 0, y: 0, width: width, height: height))

    for idx in pixels.indices {
        pixels[idx] = pixels[idx] >= 128 ? 0 : 255
    }

    guard
        let provider = CGDataProvider(data: Data(pixels) as CFData),
        let output = CGImage(
            width: width,
            height: height,
            bitsPerComponent: 8,
            bitsPerPixel: 8,
            bytesPerRow: bytesPerRow,
            space: colorSpace,
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: false,
            intent: .defaultIntent
        )
    else {
        throw MaskError.noForeground(sourceURL)
    }

    return output
}

func writeMask(_ maskImage: CGImage, to url: URL) throws {
    let rep = NSBitmapImageRep(cgImage: maskImage)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        throw MaskError.pngEncodeFailed(url)
    }
    try data.write(to: url)
}

func updateMeta(in folder: URL, maskURL: URL, artName: String) {
    let metaURL = sidecarURL(in: folder, baseName: "meta", extension: "json", artName: artName)
    guard let data = try? Data(contentsOf: metaURL) else {
        return
    }
    guard var object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        return
    }
    object["holoMaskImage"] = maskURL.path
    object["holoMaskMode"] = "black-subject-white-background"
    object["holoMaskDescription"] = "Binary mask for holo work: character in black, background in white."
    guard
        let encoded = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted]),
        var text = String(data: encoded, encoding: .utf8)
    else {
        return
    }
    text.append("\n")
    try? text.write(to: metaURL, atomically: true, encoding: .utf8)
}

func candidateFolders(in sourceDir: URL, dexes: Set<Int>) -> [URL] {
    guard let entries = try? FileManager.default.contentsOfDirectory(
        at: sourceDir,
        includingPropertiesForKeys: [.isDirectoryKey],
        options: [.skipsHiddenFiles]
    ) else {
        return []
    }

    return entries
        .filter { url in
            guard let value = try? url.resourceValues(forKeys: [.isDirectoryKey]), value.isDirectory == true else {
                return false
            }
            guard let dex = Int(url.lastPathComponent) else {
                return false
            }
            return dexes.isEmpty || dexes.contains(dex)
        }
        .sorted { lhs, rhs in lhs.lastPathComponent < rhs.lastPathComponent }
}

do {
    let config = try parseArgs()
    let folders = candidateFolders(in: config.sourceDir, dexes: config.dexes)
    var failures: [String] = []

    for folder in folders {
        do {
            guard let art = artURL(for: folder, artName: config.artName) else {
                continue
            }
            let maskURL = sidecarURL(in: folder, baseName: "holo-mask", extension: "png", artName: config.artName)
            if FileManager.default.fileExists(atPath: maskURL.path), !config.overwrite {
                print("Skipping \(folder.lastPathComponent): \(maskURL.lastPathComponent) already exists")
                continue
            }

            let cgImage = try loadCGImage(from: art)
            let mask = try buildBinaryInvertedMask(from: cgImage, sourceURL: art)
            try writeMask(mask, to: maskURL)
            updateMeta(in: folder, maskURL: maskURL, artName: config.artName)
            print("Saved \(maskURL.path)")
        } catch MaskError.noForeground {
            let maskURL = sidecarURL(in: folder, baseName: "holo-mask", extension: "png", artName: config.artName)
            if let fallbackURL = fallbackMaskURL(for: folder, artName: config.artName) {
                if FileManager.default.fileExists(atPath: maskURL.path) {
                    try? FileManager.default.removeItem(at: maskURL)
                }
                try FileManager.default.copyItem(at: fallbackURL, to: maskURL)
                updateMeta(in: folder, maskURL: maskURL, artName: config.artName)
                print("Copied fallback \(fallbackURL.lastPathComponent) -> \(maskURL.lastPathComponent)")
                continue
            }
            failures.append("Vision returned no foreground mask for: \(folder.path)")
            continue
        }
        catch {
            failures.append("\(error)")
        }
    }

    if !failures.isEmpty {
        for failure in failures {
            fputs("\(failure)\n", stderr)
        }
        exit(1)
    }
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
