# Civilian Emergency Receiver

`CivilianEmergencyReceiver.py` is the only runtime signal source for the three
civilian emergency challenges. It follows the live weather-station channel
pattern, but generates its alert audio and metadata in memory.

Each metadata frame is:

```text
Barker-13 | payload bytes | CRC-16/CCITT-FALSE
```

The receiver block verifies the CRC trailer when it constructs the frame. The
post-channel-model CF32 stream is sent directly to Signal Forge. No OGG, WAV,
SigMF, raw IQ, or capture JSON is read or written.
