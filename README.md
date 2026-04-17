# AutoClick

A powerful, template-based screen auto-clicker with image recognition. Define a template image of what you want to click, and AutoClick will automatically find and click it repeatedly on your screen.

## Features

- 🎯 **Image Recognition**: Uses OpenCV to find and match template images on screen
- 🖼️ **Flexible Input**: Load templates from file, snip from screen, or paste from clipboard
- 📍 **Custom Regions**: Define search areas or use specific monitors
- ⚙️ **Configurable**: Adjustable confidence threshold, click timing, and click types
- 🛡️ **Fail-Safe**: Built-in mouse corner failsafe to prevent runaway clicking
- 🎨 **Dark UI**: Modern, dark-themed interface with intuitive controls
- 🔍 **Real-time Logging**: See every action and confidence scores in the activity log

## Installation

### Windows (Recommended)

Download the latest `.exe` from [Releases](https://github.com/maxecution/AutoClick/releases) and run it directly. No Python or dependencies required.

### Running from Source (Windows)

1. Clone the repository:

```bash
git clone https://github.com/maxecution/AutoClick.git
cd AutoClick
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python AutoClick.py
```

## Requirements

- **Windows 7 or higher** (primary platform, fully tested)
- Python 3.8+ (for running from source)
- Display hardware with at least one monitor

## Building the Executable (Windows)

To build a standalone `.exe`:

1. Install PyInstaller:

```bash
pip install pyinstaller
```

2. Build using the provided spec file:

```bash
pyinstaller AutoClick.spec
```

### Platform Support

⭐ **Windows**: Fully supported and tested

⚠️ **macOS/Linux**: Not tested - may have issues with screen capture, mouse control, or UI

### Dependencies

- **pyautogui** - Mouse and keyboard automation
- **mss** - Fast multi-monitor screenshot capture
- **Pillow** - Image processing
- **numpy** - Numerical array handling
- **opencv-python** - Template matching and image recognition

## Usage Guide

### Step 1: Capture a Template

1. Click **✂ Snip Screen** to start the screen snipping tool
2. Drag to select the image you want to click on
3. Release to capture the template
4. The template preview will appear in the "Template Image" section

**Alternative methods:**

- Click **Add File...** to load an image from disk
- Click **Paste Clipboard** to use an image already copied to your clipboard

### Step 2: Configure Search Region (Optional)

By default, AutoClick searches all monitors. You can narrow the search area for better performance:

- Click **+ Draw Region** to snip a custom search area
- Click **Monitor...** to select a specific monitor
- Click **Reset** to search all monitors again

### Step 3: Adjust Settings

Configure in the "Timing & Click" section:

| Setting           | Default | Description                            |
| ----------------- | ------- | -------------------------------------- |
| Check interval    | 10s     | How often to scan for the template     |
| Click offset X    | 0px     | Horizontal offset from template center |
| Click offset Y    | 0px     | Vertical offset from template center   |
| Pause after click | 1s      | Delay before resuming scans            |
| Click type        | left    | Type: `left`, `right`, or `double`     |

### Step 4: Adjust Confidence Threshold

The **Match confidence** slider (0.5–1.0) controls how strict template matching is:

- **0.5–0.7**: Very lenient, may click wrong targets
- **0.8** (default): Good balance for most cases
- **0.9–1.0**: Very strict, may miss legitimate matches

### Step 5: Start Clicking

1. Click **▶ Start** to begin
2. The status indicator will show **RUNNING** with a blinking dot
3. AutoClick will search and click repeatedly until you click **■ Stop**
4. Monitor the Activity Log for each click with confidence scores

## Tips & Tricks

### Template Capture Best Practices

- **Unique regions**: Capture distinctive button or UI elements
- **Sufficient size**: Templates smaller than 10×10 pixels may not match reliably
- **Color stability**: Avoid capturing dynamic content (videos, animations)
- **Contrast**: Capture areas with good contrast for better matching

### Performance Optimization

- Use **Draw Region** to limit search area instead of scanning all monitors
- Increase **Check interval** if you don't need real-time clicking
- Use a **higher confidence threshold** to speed up processing
- Keep template image reasonably small

### Troubleshooting

**Template not found:**

- Lower the confidence threshold
- Check that the template image is still visible on screen
- Ensure the template region hasn't changed appearance

**Clicking wrong location:**

- Increase confidence threshold
- Use a more distinctive template
- Try adjusting click offsets

**Application crashed:**

- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Try running from terminal to see error messages
- On macOS/Linux, you may need additional accessibility permissions

## Fail-Safe

AutoClick includes a **mouse corner fail-safe**: if you move your mouse to any corner of the screen while it's running, it will immediately stop. This prevents runaway clicking in case of template match errors.

## Configuration

Settings are not persistent between sessions.

## Security & Safety

- AutoClick executes clicks only when templates match
- Mouse fail-safe prevents uncontrolled automation
- No automatic start, you must explicitly click **▶ Start**
- All settings are local; no data collection or internet connection

## Known Limitations

- Template images must remain visible on screen to be found
- Moving windows or changing resolution mid-run may affect matching
- Very small templates (<10px) may match unreliably
- OpenCV color format conversion assumes RGB images

## Troubleshooting

### Missing Dependencies Error

```
Required packages are not installed.
Error: No module named 'pyautogui'
```

**Solution:** Install all dependencies:

```bash
pip install -r requirements.txt
```

### Icon File Not Found

The application will run but without the window icon if `AutoClick.ico` is missing.

**Solution:** Ensure `AutoClick.ico` is in the same directory as `AutoClick.py`.

### Screen Capture Failed

**Causes:** Invalid monitor configuration or graphics driver issues

**Solution:**

- Restart the application
- Check your monitor is detected: click **Monitor...** and verify
- Update graphics drivers

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License—see the [LICENSE](LICENSE) file for details.

## Disclaimer

**Platform Note:** AutoClick is developed and tested exclusively on Windows. Use on other operating systems (macOS, Linux) is unsupported and untested.

This tool is intended for automation of legitimate, repetitive tasks on Windows systems. Users are responsible for ensuring their use complies with applicable laws and terms of service of any platforms or applications being automated. The author is not responsible for misuse, unintended consequences, or issues arising from use on unsupported platforms.

## Changelog

### Version 1.0.0 (2026-04-17)

- Initial public release
- Template-based clicking with image recognition
- Multi-monitor and custom region support
- Configurable timing and click types
- Real-time activity logging

## Support

For issues, feature requests, or questions:

- Open an [issue on GitHub](https://github.com/maxecution/AutoClick/issues)
- Check existing issues for solutions
- Include your Python version, OS, and detailed error messages
