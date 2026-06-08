# Ghost Pilot Validation

Validation is split into three layers:

1. repository guard commands,
2. generated ADB sequence quality checks,
3. emulator log scan after APK install and interaction.

A generated ADB sequence is rejected when it is empty, too short, or only navigates away from the app.
