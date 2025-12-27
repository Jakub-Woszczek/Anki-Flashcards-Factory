import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", action="store_true", help="Run the main app")
    args = parser.parse_args()

    if args.app:
        pass
