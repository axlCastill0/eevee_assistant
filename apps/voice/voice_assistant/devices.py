"""List audio devices as seen from inside the container.

    docker compose exec voice python -m voice_assistant.devices

Indexes differ between the host and the container, and change across replugs.
Prefer setting VOICE_INPUT_DEVICE / VOICE_OUTPUT_DEVICE to a name substring
shown here rather than an index.
"""
import sounddevice as sd


def main() -> None:
    print(sd.query_devices())
    print()
    try:
        din, dout = sd.default.device
        print(f"default input index : {din}")
        print(f"default output index: {dout}")
    except Exception as exc:
        print(f"could not read defaults: {exc}")


if __name__ == "__main__":
    main()
