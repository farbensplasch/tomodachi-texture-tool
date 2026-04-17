import sys

def check_deps():
    missing = []
    try:
        # DDS DXT1 write requires Pillow >= 10.1
        from PIL import __version__ as pv
        major, minor = int(pv.split(".")[0]), int(pv.split(".")[1])
        if (major, minor) < (10, 1):
            missing.append(f"Pillow >= 10.1.0 (found {pv})")
    except ImportError:
        missing.append("Pillow >= 10.1.0")

    for pkg, name in [("customtkinter", "customtkinter"), ("numpy", "numpy"), ("zstandard", "zstandard")]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(name)

    return missing


def main():
    missing = check_deps()
    if missing:
        print("Missing dependencies:")
        for m in missing:
            print(f"  • {m}")
        print("\nRun:  pip install -r requirements.txt")
        sys.exit(1)

    from app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
