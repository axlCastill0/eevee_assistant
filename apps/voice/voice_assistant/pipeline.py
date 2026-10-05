"""Main pipeline loop.

Single-threaded with a persistent mic stream. The slow stages (STT, SLM, API,
TTS) block, and mic frames arriving during them are discarded — correct for a
push-to-talk-style interaction where the user is not expected to speak over
the assistant.

Order of operations per utterance:
    wake word -> record (VAD-gated) -> STT -> fast path or SLM -> API -> TTS
"""
from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

from . import config
from .api_client import BackendClient
from .fastpath import FastPath
from .heartbeat import Heartbeat
from .helpers import downsample_mic, preprocess_transcript
from .recorder import CommandRecorder
from .stt import load_whisper, transcribe
from .tts import Speaker
from .vad import SileroVAD
from .wake_word import WakeWordDetector

log = logging.getLogger("pipeline")


class VoiceAssistant:
    """Owns every stage. Construct once, then call run()."""

    def __init__(self):
        log.info("Loading pipeline components...")

        # The API is contacted first so the intent catalogue can shape the
        # grammar and the fast path. A failure here is survivable.
        self.api = BackendClient()
        self.catalog = self.api.fetch_intents()

        # Start beating before the slow model loads, not after. Loading the
        # 1.5B model takes long enough that the backend would otherwise report
        # voice as down for the whole startup window.
        self.heartbeat = Heartbeat(self.api)
        self.heartbeat.start()

        self.wake_word = WakeWordDetector()
        self.vad = SileroVAD()
        self.recorder = CommandRecorder(self.vad)
        self.whisper = load_whisper()
        self.fastpath = FastPath(self.catalog.names, enabled=config.FASTPATH_ENABLED)

        self.classifier = None
        if config.SLM_ENABLED:
            from .slm import IntentClassifier
            self.classifier = IntentClassifier(self.catalog)
            log.info("Warming up SLM...")
            self.classifier.warmup()
        else:
            log.warning("SLM disabled; unmatched utterances will be 'unknown'")

        self.speaker = Speaker()
        self.input_device = config.resolve_device(config.INPUT_DEVICE, "input")

        log.info("Pipeline ready.")

    # -- main loop ---------------------------------------------------------

    def run(self) -> None:
        """Enter the main loop. Blocks until KeyboardInterrupt."""
        self.speaker.say(self._greeting())

        with sd.RawInputStream(
            samplerate=config.MIC_RATE,
            channels=1,
            dtype="int16",
            blocksize=config.WW_NATIVE_FRAME,
            device=self.input_device,
        ) as stream:
            log.info("Listening for wake word...")
            count = 0

            while True:
                chunk_bytes, _ = stream.read(config.WW_NATIVE_FRAME)
                chunk_native = np.frombuffer(chunk_bytes, dtype=np.int16)
                chunk_16k = downsample_mic(chunk_native)

                self.recorder.feed_pre_roll(chunk_16k)

                triggered, score = self.wake_word.process(chunk_16k)
                if not triggered:
                    continue

                count += 1
                log.info("Wake word detected (#%d, score=%.2f)", count, score)

                try:
                    self._handle_utterance(stream)
                except Exception:
                    # One bad utterance must not end the session. Log it and
                    # go back to listening.
                    log.exception("Error handling utterance")
                    self.speaker.say("Something went wrong.")

                self.recorder.clear_pre_roll()
                self.wake_word.reset()
                sd.sleep(config.POST_TTS_GRACE_MS)
                log.info("Listening for wake word...")

    def _greeting(self) -> str:
        if not self.catalog.from_api:
            return "Voice assistant ready, but I can't reach the backend."
        return "Voice assistant ready."

    # -- one utterance -----------------------------------------------------

    def _handle_utterance(self, stream: sd.RawInputStream) -> None:
        audio, speech_seen = self.recorder.record(stream)

        if not speech_seen:
            # Skip STT entirely. Whisper invents words from silence.
            self.speaker.say("I didn't hear anything.")
            return

        raw_text = transcribe(self.whisper, audio)
        clean = preprocess_transcript(raw_text)
        log.info("Heard: %r -> cleaned: %r", raw_text, clean)

        if not clean:
            self.speaker.say("Sorry, I didn't catch that.")
            return

        intent, item = self._classify(clean)

        speech = self.api.submit_intent(intent, item, transcript=clean)
        log.info("Speaking: %r", speech)
        self.speaker.say(speech)

    def _classify(self, text: str) -> tuple[str, str | None]:
        """Fast path first, SLM as fallback."""
        hit = self.fastpath.match(text)
        if hit is not None:
            intent, item = hit
            log.info("Classified by fast path: intent=%s item=%r", intent, item)
            return intent, item

        if self.classifier is None:
            return "unknown", None

        intent, item = self.classifier.classify(text)
        log.info("Classified by SLM: intent=%s item=%r", intent, item)
        return intent, item

    def close(self) -> None:
        # Stop beating before closing the client, or the heartbeat thread can
        # fire a request into a closed transport on the way out.
        self.heartbeat.stop()
        self.api.close()


def run() -> None:
    """Entry point for run.py."""
    assistant = VoiceAssistant()
    try:
        assistant.run()
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        assistant.close()
