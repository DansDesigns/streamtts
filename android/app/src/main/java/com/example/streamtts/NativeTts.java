package com.example.streamtts;

/** JNI wrapper around the shared native StreamingTts core. */
public final class NativeTts {
    static {
        System.loadLibrary("streamtts_jni");
    }

    private NativeTts() {}

    /** Paths must refer to readable local files (normally app filesDir/models). */
    public static native boolean nativeInit(String modelPath, String tokensPath, String dataDir);
    public static native void nativePushText(String fragment);
    public static native void nativeFlush();
    public static native void nativeWaitUntilIdle();
    public static native void nativeShutdown();

    public static void init(String modelPath, String tokensPath, String dataDir) {
        nativeInit(modelPath, tokensPath, dataDir);
    }

    public static void pushText(String fragment) { nativePushText(fragment); }
    public static void flush() { nativeFlush(); }
    public static void waitUntilIdle() { nativeWaitUntilIdle(); }
    public static void shutdown() { nativeShutdown(); }
}
