# Weather Broadcast challenge resources

The assessed site uses three receive-only GNU Radio training chains. Keep each
flowgraph, its generated Python file, embedded Python companions, and paired WAV
sources together in this directory.

## Intercepting Receiver

- `InterceptingReceiver.grc`
- `InterceptingReceiver.py`
- `WeatherRadio_Broadcast_Re.wav`
- `WeatherRadio_2_IM.wav`

## Obscured Receiver

- `IThinkItsSecure.grc`
- `InterceptingReceiver_Task2.py`
- `InterceptingReceiver_Task2_epy_block_0.py`
- `WeatherRadio_T2_RE.wav`
- `WeatherRadio_T2_IM.wav`

## Emergency Warning Light

- `EmergencyWarningLight.grc`
- `EmergencyWarningLight.py`
- `EmergencyWarningLight_epy_block_0.py`
- `EmergencyWarningLight_epy_block_1.py`
- `EmergencyWarningLight_epy_block_1_0.py`
- `MyEmbeddedAlarmSystem.c`
- `MyEmbeddedAlarmSystem.h`
- `WeatherRadio_T3_RE.wav`
- `WeatherRadio_T3_IM.wav`

Run GNU Radio generated Python files from any working directory; they resolve
their WAV inputs beside the script. When regenerating Python in GNU Radio
Companion, open or execute the `.grc` file from this resource directory so its
relative WAV paths resolve correctly.

The browser challenge uses bounded generated `cf32_le` downloads for offline
analysis. The original paired WAV files remain available as download-only
resources and are not loaded into the browser artifact inspector.
