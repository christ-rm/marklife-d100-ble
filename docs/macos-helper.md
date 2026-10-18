# macOS: sending Bluetooth from a background app

A script launched from an app without `NSBluetoothAlwaysUsageDescription` crashes ("Python quit unexpectedly").
Terminal.app works. To run silently (no Terminal window) wrap the script in a tiny app bundle:

1. `Info.plist` with `LSUIElement` = true (no Dock icon) and `NSBluetoothAlwaysUsageDescription`.
2. A **Mach-O** executable as `CFBundleExecutable` (a shell script does NOT work as the main executable): a 10-line C launcher that `execv`s your Python.
3. Ad-hoc sign it: `codesign --force --deep -s - Printer.app`.
4. Launch it with `open -n -g -a Printer.app --args file.pdf status.json` and read the result from `status.json`.

```c
#include <unistd.h>
int main(int argc, char **argv) {
    char *args[argc + 2];
    args[0] = "/path/to/venv/bin/python"; args[1] = "/path/to/d100_print.py";
    for (int i = 1; i < argc; i++) args[i + 1] = argv[i];
    args[argc + 1] = 0;
    execv(args[0], args);
    return 127;
}
```
