# AS11 RPC Spool Reference

This document lists every known `StartSpool` spool type, its payload
family, and the inner record shapes for each family. Protocol
mechanics, request fields, status codes, and the cursor-advance
caveat are described in
[AS11 RPC Protocol](rpc_protocol.md#spool-rpc).

## Contents

- [Spool registry](#spool-registry)
  - [Families](#families)
  - [Full enumeration](#full-enumeration)
- [Inner record shapes](#inner-record-shapes)
  - [Profile collection records](#profile-collection-records)
  - [Event records](#event-records)
  - [TherapyOneMinutePeriodic records](#therapyoneminuteperiodic-records)
  - [Metric snapshot records](#metric-snapshot-records)
  - [DiagnosticTenMinutePeriodic records](#diagnostictenminuteperiodic-records)
  - [RC03 archived-signal records](#rc03-archived-signal-records)
  - [SoundcheckVector records](#soundcheckvector-records)
  - [Blob and audio records](#blob-and-audio-records)

## Spool registry

<!-- spool-registry: begin -->

### Families

| Family | Spool types | Notes |
|--------|-------------|-------|
| `summary` | `Summary` | Per-day/per-session summary records. |
| `profile` | `SettingProfilesCollection` | Profile snapshot stream (repeated records). |
| `config` | `ConfigurationProfilesCollection` | Configuration snapshot (single record). |
| `event` | `UsageEvents-TherapyStatusEvents`, `TherapyEvents-RespiratoryEvents`, `SystemActivityEvents-FrequentActivityEvents`, `SystemActivityEvents-SporadicActivityEvents`, `SystemExceptionEvents-SystemErrors`, `SystemExceptionEvents-RecoverableErrors`, `SystemExceptionEvents-HumidifierErrors`, `SystemExceptionEvents-HeatedTubeErrors`, `DiagnosticExceptionEvents-AppErrors`, `DiagnosticExceptionEvents-FatalErrors`, `DiagnosticExceptionEvents-ResettableErrors`, `DiagnosticExceptionEvents-AlarmAppErrors`, `GUIActivityEvents`, `SurveyEvents`, `alarmEvents`, `alarmDiagnosticEvents`, `CellularActivityEvents` | Repeated event records: (type, start_ms, end_ms, duration_ms). |
| `periodic` | `TherapyOneMinutePeriodic` | Periodic measurement protobuf. |
| `periodic_compressed` | `DiagnosticTenMinutePeriodic`, `atmosphericPressure10min` | Two interleaved signal streams per record, each with its own compressed sample blob (not RC03). |
| `metric` | `MachineMetrics`, `MemoryMetrics`, `CellularDataUsage` | Single-record metric snapshot. |
| `rc03` | `RespiratoryFlow6p25Hz`, `MaskPressure6p25Hz`, `InspiratoryPressure0p5Hz`, `Leak0p5Hz` | Archived signal: protobuf wrapper around an RC03 compressed sample block. |
| `diag_vector` | `SoundcheckVector` | Multi-record diagnostic vector. |
| `diag_blob` | `AcousticSignatureV2` | Diagnostic blob; `AcousticSignatureV2` needs `maxFragmentSize >= 4096`. |
| `audio` | `RecordedSound` | Audio recording, gated by `SoundDownloadAllowed`. |

### Full enumeration

Known spool types accepted by `StartSpool`

| Spool type | Family | Gate | Group |
|------------|--------|------|-------|
| `Summary` | `summary` | -- | session/profile data |
| `SettingProfilesCollection` | `profile` | -- | session/profile data |
| `ConfigurationProfilesCollection` | `config` | -- | session/profile data |
| `UsageEvents-TherapyStatusEvents` | `event` | -- | therapy data |
| `TherapyEvents-RespiratoryEvents` | `event` | -- | therapy data |
| `TherapyOneMinutePeriodic` | `periodic` | -- | therapy data |
| `SystemActivityEvents-FrequentActivityEvents` | `event` | -- | system and diagnostic events |
| `SystemActivityEvents-SporadicActivityEvents` | `event` | -- | system and diagnostic events |
| `SystemExceptionEvents-SystemErrors` | `event` | -- | system and diagnostic events |
| `SystemExceptionEvents-RecoverableErrors` | `event` | -- | system and diagnostic events |
| `SystemExceptionEvents-HumidifierErrors` | `event` | -- | system and diagnostic events |
| `SystemExceptionEvents-HeatedTubeErrors` | `event` | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-AppErrors` | `event` | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-FatalErrors` | `event` | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-ResettableErrors` | `event` | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-AlarmAppErrors` | `event` | -- | system and diagnostic events |
| `GUIActivityEvents` | `event` | -- | system and diagnostic events |
| `SurveyEvents` | `event` | -- | system and diagnostic events |
| `alarmEvents` | `event` | -- | system and diagnostic events |
| `alarmDiagnosticEvents` | `event` | -- | system and diagnostic events |
| `DiagnosticTenMinutePeriodic` | `periodic_compressed` | -- | periodic metrics |
| `MachineMetrics` | `metric` | -- | periodic metrics |
| `MemoryMetrics` | `metric` | -- | periodic metrics |
| `CellularActivityEvents` | `event` | -- | periodic metrics |
| `CellularDataUsage` | `metric` | -- | periodic metrics |
| `atmosphericPressure10min` | `periodic_compressed` | -- | archived signals |
| `RespiratoryFlow6p25Hz` | `rc03` | -- | archived signals |
| `MaskPressure6p25Hz` | `rc03` | -- | archived signals |
| `InspiratoryPressure0p5Hz` | `rc03` | -- | archived signals |
| `Leak0p5Hz` | `rc03` | -- | archived signals |
| `SoundcheckVector` | `diag_vector` | -- | diagnostic blobs |
| `AcousticSignatureV2` | `diag_blob` | -- | diagnostic blobs |
| `RecordedSound` | `audio` | `SoundDownloadAllowed` | diagnostic blobs |

<!-- spool-registry: end -->

## Inner record shapes

### Profile collection records

`SettingProfilesCollection` contains:

| Field | Meaning |
|-------|---------|
| `1` | attributes: applied timestamp, source, transaction id |
| `2` | stored-data-delivery selector list |
| `3` | therapy profile snapshots |
| `4` | feature profile snapshots |

The host decoder names the known therapy profile subrecords
(`CpapProfile`, `AutoSetProfile`, `VAutoProfile`, `ASVProfile`, etc.) and
feature profile subrecords (`EprFeature`, `AutoRampFeature`, `ClimateFeature`,
`DisplayFeature`, etc.). Numeric pressure and time fields are scaled to human
units. Enum-like fields are printed with `Raw` suffix until all option labels
are verified.

`ConfigurationProfilesCollection` contains attributes plus
`DataDeliveryControlV2`, whose fields map to spool families such as
`Summary`, `TherapyOneMinutePeriodic`, `RespiratoryFlow6p25Hz`, and
`CellularDataUsage`.

### Event records

Most event spool records use the same inner record shape:

| Field | Meaning |
|-------|---------|
| `1` | event type/code |
| `2` | start timestamp, UTC milliseconds |
| `3` | end timestamp, UTC milliseconds |
| `4` | duration in milliseconds, when present |

The wrapper depth varies by spool family, so the host tool unwraps event
records conservatively and keeps unknown event codes numeric unless a label
table has been verified.

### TherapyOneMinutePeriodic records

`TherapyOneMinutePeriodic` records contain one or more per-signal messages,
plus field `15`, which has been observed as the sample interval in minutes.

Each per-signal message has this shape:

| Field | Meaning |
|-------|---------|
| `1` | status/kind marker, observed as `1` |
| `2` | start timestamp, UTC milliseconds |
| `3` | sample block |

The sample block is an int16 series. Fields `1..7` and `21` are headerless
second-difference/Rice streams using the same reconstruction formula as RC03.
Fields `8` and `9`, when present, are raw little-endian int16 arrays.

Decoded fields:

| Field | Name | CSV column | Scale |
|-------|------|------------|-------|
| `1` | Leak | `leak_l_min` | `raw * 1.2` L/min |
| `2` | InspiratoryPressure | `insp_pressure_cmH2O` | `raw / 5` cmH2O |
| `3` | ExpiratoryPressure | `exp_pressure_cmH2O` | `raw / 5` cmH2O |
| `4` | MinuteVentilation | `minute_vent_l_min` | `raw / 8` L/min |
| `5` | InspiratoryDuration | `insp_duration_s` | `raw / 50` seconds |
| `6` | RespiratoryRate | `resp_rate_bpm` | `raw` bpm |
| `7` | IeRatio | `ie_ratio_pct` | `raw * 4` percent |
| `8` | SpO2 | `spo2_pct` | `raw` percent |
| `9` | HeartRate | `heart_rate_bpm` | `raw` bpm |
| `21` | MIS | `mis` | `raw / 50`; exact meaning unresolved |

The field mapping and scales are verified against `Summary` percentile
records and observed oximetry samples.

### Metric snapshot records

`MachineMetrics` contains one current snapshot:

| Field | Meaning |
|-------|---------|
| `1` | origin enum, observed `1` |
| `2` | attributes; subfield `1` is report timestamp |
| `3` | `LastTherapyUseDateTime` |
| `4` | `LastEraseDataDateTime` |
| `5` | `TherapyRunMeter`, milliseconds |
| `6` | `MotorRunMeter`, milliseconds |
| `7` | `MotorRunSinceLastServiceMeter`, milliseconds |
| `8` | `MachineRunMeter`, milliseconds |
| `9` | `LastMachineServiceDateTime` |

`CellularDataUsage` contains one current snapshot:

| Field | Meaning |
|-------|---------|
| `1` | origin enum, observed `1` |
| `2` | attributes; subfield `1` is report timestamp |
| `3` | `ApplicationTotalUpload`, bytes |
| `4` | `ApplicationTotalDownload`, bytes |

`MemoryMetrics` field `1` is attributes with report timestamp. Field `2`
repeats one memory metric record. The subrecord fields are fully decoded
structurally, but only the first field is named semantically:

| Subfield | Meaning |
|----------|---------|
| `1` | memory pool/type enum |
| `2` | metric value A |
| `3` | metric value B |
| `4` | metric value C |

### DiagnosticTenMinutePeriodic records

`DiagnosticTenMinutePeriodic` records have field `1` origin/kind and one or
more signal subrecords. Each signal subrecord contains:

| Field | Meaning |
|-------|---------|
| `1` | sample interval, minutes |
| `2` | start timestamp, UTC milliseconds |
| `3` | headerless signed int16 second-difference/Rice sample block |

Observed signal fields:

| Field | Name |
|-------|------|
| `2` | `CellularSignalStrength` |
| `3` | `CellularSignalQuality2G` |
| `4` | `CellularSignalQuality3G` |
| `5` | `CellularSignalQualityLTE` |

The archived data captured so far contains signal fields `2` and `5`.
`atmosphericPressure10min` is accepted by the device but has not produced a
populated payload on the test device yet.

### RC03 archived-signal records

The RC03 signal records are protobuf wrappers around a compressed sample
block. The inner record fields observed so far are:

| Field | Meaning |
|-------|---------|
| `1` | sample interval in milliseconds |
| `2` | start timestamp, UTC milliseconds |
| `3` | end timestamp, UTC milliseconds |
| `4` | RC03 compressed sample block |

The first byte of field `4` is the RC03 header length, followed by ASCII
`RC03`, six zigzag-varint format parameters, and compressed sample data. The
body starts with one or two signed little-endian 16-bit sample seeds. Remaining
samples are Rice-coded zigzag second differences:

```
delta2[n] = sample[n] - 2 * sample[n - 1] + sample[n - 2]
sample[n] = 2 * sample[n - 1] - sample[n - 2] + delta2[n]
```

On currently decoded archived signal blocks, parameter 4 is the Rice modulus
and parameter 1 gives the scale exponent. The host tool uses
`value = raw * (2 * 10 ** param1)`.

### SoundcheckVector records

`SoundcheckVector` records contain:

| Field | Meaning |
|-------|---------|
| `1` | report timestamp, UTC milliseconds |
| `2` | sample rate, observed `18750` Hz |
| `3` | repeated vector/bin value |
| `4` | repeated peak-pair wrapper |

Each field-4 peak wrapper repeats field `1` messages. The inner peak
message has subfield `1` and subfield `2`; observed values look like
frequency/bin and amplitude/score pairs, but the exact units are not yet
proven.

### Blob and audio records

`AcousticSignatureV2` and `RecordedSound` have conservative decoders. Empty
payloads are reported as empty. Populated payloads are summarized by byte
length and leading hex bytes, with `--details` enabling a generic protobuf
walk where the payload is protobuf-like. `RecordedSound` also reports
`RIFF/WAVE` if that header is present.
