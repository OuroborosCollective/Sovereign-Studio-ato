# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.

# Preserve debugging information
-keepattributes SourceFile,LineNumberTable,Signature,InnerClasses,EnclosingMethod,*Annotation*,JavascriptInterface

# Sovereign Engine Core Logic
-keep class com.sovereign.engine.** { *; }
-keep interface com.sovereign.engine.** { *; }
-keep enum com.sovereign.engine.** { *; }

# Redux State Models and No-Code Logic Objects
# Ensures that property names are not obfuscated, preserving JS-to-Native mapping
-keep class com.sovereign.models.** { *; }
-keep class **.state.** { *; }
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}

# Capacitor Bridge & Plugin Architecture
-keep class com.getcapacitor.** { *; }
-keep @interface com.getcapacitor.NativePlugin
-keep @interface com.getcapacitor.PluginMethod
-keep class * extends com.getcapacitor.Plugin { *; }
-keepclassmembers class * {
    @com.getcapacitor.PluginMethod public void *(com.getcapacitor.PluginCall);
}

# WebKit / JavaScript Interface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# JSON Serialization preservation (Commonly used by Sovereign Engine for state sync)
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}
-keep class com.google.gson.** { *; }

# Prevent shrinking of reflective calls used in dynamic logic injection
-keep class * {
    @androidx.annotation.Keep <fields>;
    @androidx.annotation.Keep <methods>;
    @androidx.annotation.Keep <init>(...);
}

# Ensure native methods remain linkable
-keepclasseswithmembernames class * {
    native <methods>;
}