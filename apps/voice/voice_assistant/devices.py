"""List audio devices as seen from inside the container.

    docker compose exec voice python -m voice_assistant.devices

Prints both halves of the mapping, because they are not the same thing and
confusing them is the usual cause of "no device matching ...":

- ALSA cards, with their **id** in brackets. A udev ATTR{id} rule sets this.
  Read through libasound, because /proc/asound is masked inside a container.
- PortAudio devices, whose **names** come from the card's name field (the USB
  descriptor), which udev does not touch. The `(hw:N,M)` suffix is the only
  link back to the card number.

So for a card pinned as `eeveemic`, set VOICE_INPUT_DEVICE=CARD=eeveemic --
not `eeveemic`, which matches no device name.
"""
import sounddevice as sd

from . import alsa


def main() -> None:
    # Queried through libasound, NOT /proc/asound: the container runtime masks
    # /proc/asound to an empty directory, so reading it here would print
    # nothing while the host shows every card.
    print("ALSA cards -- id is in brackets, and is what CARD= matches:")
    print(alsa.describe_cards())
    print()

    print("PortAudio devices -- match these by name substring, or by card id:")
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
