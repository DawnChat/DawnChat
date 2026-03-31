// swift-tools-version: 5.9
import PackageDescription

// DO NOT MODIFY THIS FILE - managed by Capacitor CLI commands
let package = Package(
    name: "CapApp-SPM",
    platforms: [.iOS(.v15)],
    products: [
        .library(
            name: "CapApp-SPM",
            targets: ["CapApp-SPM"])
    ],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", exact: "8.2.0"),
        .package(name: "CapacitorBarcodeScanner", path: "../../../node_modules/@capacitor/barcode-scanner"),
        .package(name: "CapacitorCamera", path: "../../../node_modules/@capacitor/camera"),
        .package(name: "CapacitorClipboard", path: "../../../node_modules/@capacitor/clipboard"),
        .package(name: "CapacitorDialog", path: "../../../node_modules/@capacitor/dialog"),
        .package(name: "CapacitorFilesystem", path: "../../../node_modules/@capacitor/filesystem"),
        .package(name: "CapacitorGeolocation", path: "../../../node_modules/@capacitor/geolocation"),
        .package(name: "CapacitorHaptics", path: "../../../node_modules/@capacitor/haptics"),
        .package(name: "CapacitorInappbrowser", path: "../../../node_modules/@capacitor/inappbrowser"),
        .package(name: "CapacitorKeyboard", path: "../../../node_modules/@capacitor/keyboard"),
        .package(name: "CapacitorLocalNotifications", path: "../../../node_modules/@capacitor/local-notifications"),
        .package(name: "CapacitorNetwork", path: "../../../node_modules/@capacitor/network"),
        .package(name: "CapacitorPreferences", path: "../../../node_modules/@capacitor/preferences"),
        .package(name: "CapacitorScreenOrientation", path: "../../../node_modules/@capacitor/screen-orientation"),
        .package(name: "CapacitorShare", path: "../../../node_modules/@capacitor/share"),
        .package(name: "CapacitorStatusBar", path: "../../../node_modules/@capacitor/status-bar"),
        .package(name: "CapacitorToast", path: "../../../node_modules/@capacitor/toast"),
        .package(name: "CapgoCapacitorAudioRecorder", path: "../../../node_modules/@capgo/capacitor-audio-recorder"),
        .package(name: "CapgoCapacitorContacts", path: "../../../node_modules/@capgo/capacitor-contacts"),
        .package(name: "CapgoCapacitorFlash", path: "../../../node_modules/@capgo/capacitor-flash"),
        .package(name: "CapgoCapacitorKeepAwake", path: "../../../node_modules/@capgo/capacitor-keep-awake"),
        .package(name: "CapgoCapacitorNativeBiometric", path: "../../../node_modules/@capgo/capacitor-native-biometric"),
        .package(name: "CapgoCapacitorShake", path: "../../../node_modules/@capgo/capacitor-shake"),
        .package(name: "CapgoCapacitorVideoPlayer", path: "../../../node_modules/@capgo/capacitor-video-player"),
        .package(name: "CapgoNativeAudio", path: "../../../node_modules/@capgo/native-audio")
    ],
    targets: [
        .target(
            name: "CapApp-SPM",
            dependencies: [
                .product(name: "Capacitor", package: "capacitor-swift-pm"),
                .product(name: "Cordova", package: "capacitor-swift-pm"),
                .product(name: "CapacitorBarcodeScanner", package: "CapacitorBarcodeScanner"),
                .product(name: "CapacitorCamera", package: "CapacitorCamera"),
                .product(name: "CapacitorClipboard", package: "CapacitorClipboard"),
                .product(name: "CapacitorDialog", package: "CapacitorDialog"),
                .product(name: "CapacitorFilesystem", package: "CapacitorFilesystem"),
                .product(name: "CapacitorGeolocation", package: "CapacitorGeolocation"),
                .product(name: "CapacitorHaptics", package: "CapacitorHaptics"),
                .product(name: "CapacitorInappbrowser", package: "CapacitorInappbrowser"),
                .product(name: "CapacitorKeyboard", package: "CapacitorKeyboard"),
                .product(name: "CapacitorLocalNotifications", package: "CapacitorLocalNotifications"),
                .product(name: "CapacitorNetwork", package: "CapacitorNetwork"),
                .product(name: "CapacitorPreferences", package: "CapacitorPreferences"),
                .product(name: "CapacitorScreenOrientation", package: "CapacitorScreenOrientation"),
                .product(name: "CapacitorShare", package: "CapacitorShare"),
                .product(name: "CapacitorStatusBar", package: "CapacitorStatusBar"),
                .product(name: "CapacitorToast", package: "CapacitorToast"),
                .product(name: "CapgoCapacitorAudioRecorder", package: "CapgoCapacitorAudioRecorder"),
                .product(name: "CapgoCapacitorContacts", package: "CapgoCapacitorContacts"),
                .product(name: "CapgoCapacitorFlash", package: "CapgoCapacitorFlash"),
                .product(name: "CapgoCapacitorKeepAwake", package: "CapgoCapacitorKeepAwake"),
                .product(name: "CapgoCapacitorNativeBiometric", package: "CapgoCapacitorNativeBiometric"),
                .product(name: "CapgoCapacitorShake", package: "CapgoCapacitorShake"),
                .product(name: "CapgoCapacitorVideoPlayer", package: "CapgoCapacitorVideoPlayer"),
                .product(name: "CapgoNativeAudio", package: "CapgoNativeAudio")
            ]
        )
    ]
)
