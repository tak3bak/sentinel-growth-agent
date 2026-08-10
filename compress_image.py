import os
import sys
from PIL import Image

filename = "120.png"
found_path = None

print("Searching system for 120.png...")

# Check current directory
if os.path.exists(filename):
    found_path = filename

# Search /sdcard and home directory tree if not in current directory
if not found_path:
    search_roots = [os.path.expanduser("~"), "/sdcard"]
    for root_dir in search_roots:
        if found_path:
            break
        if os.path.exists(root_dir):
            for dirpath, _, filenames in os.walk(root_dir):
                if filename in filenames:
                    found_path = os.path.join(dirpath, filename)
                    break

if not found_path:
    print(f"Error: Could not find '{filename}' anywhere in storage.")
    sys.exit(1)

print(f"Found image at: {found_path}")

output_path = "120_compressed.jpg"

img = Image.open(found_path)

if img.mode in ("RGBA", "P"):
    img = img.convert("RGB")

img.save(output_path, "JPEG", quality=85, optimize=True)

size_kb = os.path.getsize(output_path) / 1024
print(f"Successfully saved {output_path} ({size_kb:.2f} KB)")
