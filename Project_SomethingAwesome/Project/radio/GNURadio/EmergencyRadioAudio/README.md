# Civilian emergency transmission resources

This directory backs the three Moderate civilian emergency-radio tasks.

- `Required_Weekly_Test_NOAA.ogg` is the reference public-warning audio used to
  recognise cadence and message structure. It is supplied as an offline audio
  artifact and is never transmitted over real RF.
- `emergency_receiver.c` is a recovered, simplified receiver fragment for the
  active reverse-engineering task.

The browser generates a session-specific synthetic call on 169.650 MHz. The
first two tasks cover burst recovery and weak hopping. The final task requires a
complete normalized message containing the observed callsign, zone, alert,
action, and current AUTH code. A successful submission activates the on-page
warning light, plays the accepted message through browser speech synthesis, and
reveals the flag for `civilian-emergency-active-re`.

All transmit behaviour is local simulation only.
